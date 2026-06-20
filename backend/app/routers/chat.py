"""
Chat Router — POST /api/chat, GET/DELETE /api/conversations
All conversation endpoints are scoped to the caller's session token.
"""
import json
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_session_token
from app.limiter import limiter, is_duplicate_query
from app.models import Conversation, Message
from app.schemas import (
    ChatRequest, ChatResponse, ConversationOut,
    ConversationListItem, MessageOut, SourceCitation
)
from app.rag.pipeline import run_rag_pipeline, RagPipelineError
from app.services.analytics_service import log_event
from app.cache.response_cache import get_cached_response, set_cached_response, is_cacheable
from app.cache.kb_version import get_kb_version

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api", tags=["chat"])


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


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def chat(
    request: Request,          # required by slowapi for IP extraction
    body: ChatRequest,         # renamed from `request` to avoid collision
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
    # Catches double-click spam and rapid-fire identical submissions that slip
    # through IP-based limits (e.g., many users behind a university NAT share
    # one IP but rarely send the exact same query at the exact same second).
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
    else:
        # Auto-title from first message
        title = body.query[:60] + ("..." if len(body.query) > 60 else "")
        conversation = Conversation(title=title, session_id=session_token)
        db.add(conversation)
        await db.flush()

    # ── Load conversation history (last 5 turns = 10 messages) ───────────────
    # Subquery: grab the 10 most-recent messages ordered DESC
    recent_subq = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(10)
        .subquery()
    )
    # Outer query: re-order them ASC so the LLM sees correct chronology
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
    # Snapshot the KB version before the cache lookup so both the GET and
    # the log_event() call see a consistent version for this request.
    kb_version = await run_in_threadpool(get_kb_version)
    cache_start = time.monotonic()
    cached = await run_in_threadpool(get_cached_response, body.query)
    cache_lookup_ms = (time.monotonic() - cache_start) * 1000

    if cached is not None:
        # ── Cache HIT ──────────────────────────────────────────────────────────────
        logger.info(
            "Cache HIT for query '%s...' (%.1f ms lookup)",
            body.query[:40],
            cache_lookup_ms,
        )
        sources = [SourceCitation(**s) for s in cached.get("sources", [])]

        # Always insert a real Message row so feedback routes continue to work.
        # The cached answer is stored verbatim; the message_id is returned to
        # the client so they can submit feedback on this specific response.
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

        # Analytics: record the hit even though the pipeline didn't run.
        # response_time_ms reflects the actual user-perceived latency (fast).
        await log_event(
            db=db,
            event_type="query",
            query=body.query,
            conversation_id=conversation.id,
            response_time_ms=cache_lookup_ms,
            retrieved_chunks=cached.get("retrieved_chunks", 0),
            cache_hit=True,
            kb_version=kb_version,
        )

        return ChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            answer=cached["answer"],
            sources=sources,
            query_time_ms=cache_lookup_ms,
        )

    # ── Cache MISS — run the full RAG pipeline ───────────────────────────────────
    try:
        result = await run_in_threadpool(run_rag_pipeline, body.query, history)
    except RagPipelineError as e:
        # Classified error from the pipeline — forward the clean user message
        # and the correct HTTP status code (429 for quota, 503 for auth/unavail, etc.)
        logger.error(f"RAG pipeline error [{e.status_code}]: {e.user_message}")
        raise HTTPException(status_code=e.status_code, detail=e.user_message)
    except Exception as e:
        logger.error(f"RAG pipeline unexpected error: {e}")
        raise HTTPException(status_code=500, detail="RAG pipeline failed. Please try again.")

    # ── Store result in cache (only if valid / not an error) ─────────────────
    if is_cacheable(result):
        await run_in_threadpool(set_cached_response, body.query, result)

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
    )

    return ChatResponse(
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        answer=result["answer"],
        sources=result["sources"],
        query_time_ms=result["query_time_ms"],
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
    result = await db.execute(
        select(Conversation)
        .where(Conversation.session_id == session_token)   # ← isolation
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    conversations = result.scalars().all()

    output = []
    for conv in conversations:
        count_result = await db.scalar(
            select(func.count()).select_from(Message)
            .where(Message.conversation_id == conv.id)
        )
        output.append(
            ConversationListItem(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=count_result or 0,
            )
        )
    return output


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
