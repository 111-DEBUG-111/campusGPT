"""
Chat Router — POST /api/chat, GET/DELETE /api/conversations
All conversation endpoints are scoped to the caller's session token.
"""
import json
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.database import get_db, AsyncSessionLocal
from app.dependencies import get_session_token
from app.limiter import limiter, is_duplicate_query
from app.models import Conversation, Message
from app.schemas import (
    ChatRequest, ChatResponse, ConversationOut,
    ConversationListItem, MessageOut, SourceCitation
)
from app.rag.pipeline import run_rag_pipeline
from app.rag.errors import RagPipelineError
from app.services.progress_service import (
    update_progress,
    get_session_progress,
    STAGE_COMPLETE,
    STATUS_COMPLETED,
)
from app.rag.outcome_classifier import classify_query_outcome
from app.services.analytics_service import log_event
from app.services.knowledge_gap_service import record_knowledge_gap
from app.cache.response_cache import get_cached_response, set_cached_response, is_cacheable
from app.cache.kb_version import get_kb_version

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api", tags=["chat"])

_VALID_MODES = {"hybrid", "official", "experience"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_owned_conversation(
    conversation_id: int,
    session_token: str,
    db: AsyncSession,
) -> Conversation:
    """
    Fetch a conversation that belongs to the given session token.
    Returns 404 in both the "not found" and "wrong owner" cases
    to avoid leaking whether a conversation ID exists.
    """
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv or conv.session_id != session_token:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def _cache_key_with_mode(query: str, knowledge_mode: str) -> str:
    """
    Produce a cache-lookup key that includes the knowledge mode so that
    'hybrid', 'official', and 'experience' results are never mixed.
    We prefix the query with the mode separated by a null byte (unlikely
    to appear in real queries) before hashing.
    """
    return f"{knowledge_mode}\x00{query}"


def _schedule_outcome_classification(
    background_tasks: BackgroundTasks,
    query: str,
    answer: str,
    retrieved_chunks: int,
    knowledge_mode: str,
) -> None:
    """Classify chat outcome in the background; record knowledge gaps only."""

    async def _classify_and_record() -> None:
        try:
            outcome = await run_in_threadpool(
                classify_query_outcome, query, answer, retrieved_chunks
            )
            if outcome != "knowledge_gap":
                logger.debug(
                    "Outcome '%s' for query — not recording knowledge gap: %s...",
                    outcome,
                    query[:60],
                )
                return
            async with AsyncSessionLocal() as bg_db:
                await record_knowledge_gap(bg_db, query, knowledge_mode, answer)
                logger.info("Knowledge gap stored for query: %s...", query[:60])
        except Exception as e:
            logger.error("Background outcome classification failed: %s", e)

    background_tasks.add_task(_classify_and_record)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def chat(
    request: Request,          # required by slowapi for IP extraction
    body: ChatRequest,         # renamed from `request` to avoid collision
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    session_token: str = Depends(get_session_token),
):
    """
    Main chat endpoint.
    Creates or continues a conversation, runs the full RAG pipeline,
    stores messages, and returns the answer with citations.
    Conversations are strictly scoped to the caller's session token.
    Rate-limited per IP: controlled by RATE_LIMIT_PER_MINUTE env var.
    """
    # ── Deduplication: reject identical queries from the same IP within 5 s ──
    if is_duplicate_query(request, body.query):
        raise HTTPException(
            status_code=429,
            detail="Duplicate request detected. Please wait a moment before resending the same query.",
        )

    # ── Get or create conversation ───────────────────────────────────────────
    if body.conversation_id:
        # Ownership check: session_token must match
        conversation = await _get_owned_conversation(
            body.conversation_id, session_token, db
        )
        # Determine effective knowledge mode:
        # - If the client sent a mode, honour it and persist the change.
        # - Otherwise, use the conversation's stored mode.
        if body.knowledge_mode and body.knowledge_mode != conversation.knowledge_mode:
            conversation.knowledge_mode = body.knowledge_mode
            await db.flush()
        effective_mode = conversation.knowledge_mode
    else:
        # New conversation — use the client-supplied mode (or default to hybrid).
        effective_mode = body.knowledge_mode or "hybrid"
        # Auto-title from first message
        title = body.query[:60] + ("..." if len(body.query) > 60 else "")
        conversation = Conversation(
            title=title,
            session_id=session_token,
            knowledge_mode=effective_mode,
        )
        db.add(conversation)
        await db.flush()

    # ── Load conversation history (last 5 turns = 10 messages) ───────────────
    recent_subq = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(10)
        .subquery()
    )
    history_result = await db.execute(
        select(Message)
        .where(Message.id.in_(select(recent_subq.c.id)))
        .order_by(Message.created_at.asc())
    )
    history_messages = history_result.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in history_messages]

    # ── Store user message ────────────────────────────────────────────────────
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=body.query,
    )
    db.add(user_message)
    await db.flush()

    # ── Run RAG pipeline (or serve from cache) ──────────────────────────────
    kb_version = await run_in_threadpool(get_kb_version)
    cache_start = time.monotonic()
    # Cache key includes mode to prevent cross-mode cache collisions
    cache_query = _cache_key_with_mode(body.query, effective_mode)
    cached = await run_in_threadpool(get_cached_response, cache_query)
    cache_lookup_ms = (time.monotonic() - cache_start) * 1000

    if cached is not None:
        # ── Cache HIT ──────────────────────────────────────────────────────────────
        update_progress(
            conversation_id=conversation.id,
            session_id=session_token,
            request_id=body.request_id,
            stage=STAGE_COMPLETE,
            status=STATUS_COMPLETED,
        )
        logger.info(
            "Cache HIT for query '%s...' mode=%s (%.1f ms lookup)",
            body.query[:40],
            effective_mode,
            cache_lookup_ms,
        )
        sources = [SourceCitation(**s) for s in cached.get("sources", [])]

        sources_json = json.dumps([s.model_dump() for s in sources])
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=cached["answer"],
            sources_json=sources_json,
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        model_used = cached.get("model_used", "gemini")
        await log_event(
            db=db,
            event_type="query",
            query=body.query,
            conversation_id=conversation.id,
            response_time_ms=cache_lookup_ms,
            retrieved_chunks=cached.get("retrieved_chunks", 0),
            cache_hit=True,
            kb_version=kb_version,
            model_used=model_used,
        )

        _schedule_outcome_classification(
            background_tasks,
            body.query,
            cached["answer"],
            cached.get("retrieved_chunks", 0),
            effective_mode,
        )

        return ChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            answer=cached["answer"],
            sources=sources,
            query_time_ms=cache_lookup_ms,
            knowledge_mode=effective_mode,
            model_used=model_used,
        )

    # ── Cache MISS — run the full RAG pipeline ───────────────────────────────────
    try:
        result = await run_in_threadpool(
            run_rag_pipeline,
            body.query,
            history,
            effective_mode,
            conversation.id,
            session_token,
            body.request_id,
        )
    except RagPipelineError as e:
        logger.error(f"RAG pipeline error [{e.status_code}]: {e.user_message}")
        raise HTTPException(status_code=e.status_code, detail=e.user_message)
    except Exception as e:
        logger.error(f"RAG pipeline unexpected error: {e}")
        raise HTTPException(status_code=500, detail="RAG pipeline failed. Please try again.")

    # ── Store result in cache (only if valid / not an error) ─────────────────
    if is_cacheable(result):
        await run_in_threadpool(set_cached_response, cache_query, result)

    # ── Store assistant message ────────────────────────────────────────────
    sources_json = json.dumps([s.model_dump() for s in result["sources"]])
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result["answer"],
        sources_json=sources_json,
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)

    # ── Log analytics event ────────────────────────────────────────────────
    await log_event(
        db=db,
        event_type="query",
        query=body.query,
        conversation_id=conversation.id,
        response_time_ms=result["query_time_ms"],
        retrieved_chunks=result["retrieved_chunks"],
        cache_hit=False,
        kb_version=kb_version,
        model_used=result.get("model_used", "gemini"),
    )

    _schedule_outcome_classification(
        background_tasks,
        body.query,
        result["answer"],
        result["retrieved_chunks"],
        effective_mode,
    )

    return ChatResponse(
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        answer=result["answer"],
        sources=result["sources"],
        query_time_ms=result["query_time_ms"],
        knowledge_mode=effective_mode,
        model_used=result.get("model_used", "gemini"),
    )


@router.get("/conversations", response_model=list[ConversationListItem])
@limiter.limit("60/minute")   # frontend polls this for sidebar — relaxed
async def list_conversations(
    request: Request,          # required by slowapi for IP extraction
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    session_token: str = Depends(get_session_token),
):
    """List conversations that belong to the caller's session."""
    stmt = (
        select(Conversation, func.count(Message.id).label("message_count"))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.session_id == session_token)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()

    return [
        ConversationListItem(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=message_count,
        )
        for conv, message_count in rows
    ]


@router.get("/conversations/progress")
async def get_active_progress(
    request: Request,          # required by slowapi for IP extraction
    session_token: str = Depends(get_session_token),
):
    """
    Get active progress for all conversations in the caller's session.
    """
    return get_session_progress(session_token)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
@limiter.limit("60/minute")   # read-only — relaxed
async def get_conversation(
    request: Request,          # required by slowapi for IP extraction
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    session_token: str = Depends(get_session_token),
):
    """Get a conversation with all its messages (must be owned by caller)."""
    conversation = await _get_owned_conversation(conversation_id, session_token, db)

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        knowledge_mode=conversation.knowledge_mode,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=[SourceCitation(**s) for s in m.sources],
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
@limiter.limit("20/minute")   # destructive — moderate cap
async def delete_conversation(
    request: Request,          # required by slowapi for IP extraction
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
    session_token: str = Depends(get_session_token),
):
    """Delete a conversation and all its messages (must be owned by caller)."""
    conv = await _get_owned_conversation(conversation_id, session_token, db)
    await db.delete(conv)
    await db.commit()



