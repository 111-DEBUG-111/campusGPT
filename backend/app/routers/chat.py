"""
Chat Router — POST /api/chat, GET/DELETE /api/conversations
All conversation endpoints are scoped to the caller's session token.
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_session_token
from app.limiter import limiter
from app.models import Conversation, Message
from app.schemas import (
    ChatRequest, ChatResponse, ConversationOut,
    ConversationListItem, MessageOut, SourceCitation
)
from app.rag.pipeline import run_rag_pipeline
from app.services.analytics_service import log_event

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

    # ── Run RAG pipeline ──────────────────────────────────────────────────────
    try:
        result = await run_in_threadpool(run_rag_pipeline, body.query, history)
    except Exception as e:
        logger.error(f"RAG pipeline error: {e}")
        raise HTTPException(status_code=500, detail="RAG pipeline failed. Please try again.")

    # ── Store assistant message ───────────────────────────────────────────────
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

    # ── Log analytics event ───────────────────────────────────────────────────
    await log_event(
        db=db,
        event_type="query",
        query=body.query,
        conversation_id=conversation.id,
        response_time_ms=result["query_time_ms"],
        retrieved_chunks=result["retrieved_chunks"],
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
