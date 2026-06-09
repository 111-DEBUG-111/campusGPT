"""
Chat Router — POST /api/chat, GET /api/conversations

Orchestrates all 7 chat improvements:
  #1  Correct conversation history retrieval (DESC + limit + reverse)
  #2  Auto-summarization as a BackgroundTask when message count ≥ threshold
  #3  Store retrieved chunks on the Message model for debugging/analytics
  #4  Response caching: check cache before RAG, store result after
  #5  User ownership: bind conversations to user_id, enforce access control
  #6  Feedback system exists in feedback.py; MessageOut now exposes chunks
  #7  Memory retrieval: inject relevant past memories into the RAG prompt
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from starlette.concurrency import run_in_threadpool

from app.database import get_db, AsyncSessionLocal
from app.models import Conversation, Message, ConversationMemory
from app.schemas import (
    ChatRequest, ChatResponse, ConversationOut,
    ConversationListItem, MessageOut, SourceCitation, MemoryOut
)
from app.rag.pipeline import run_rag_pipeline
from app.rag.embedder import get_embedder
from app.services.analytics_service import log_event
from app.services.conversation_service import get_conversation_context, maybe_summarize
from app.services.cache_service import (
    get_cached_response, store_response, get_knowledge_version
)
from app.services.memory_service import store_memory, retrieve_memories

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


# ─── Ownership Helper ─────────────────────────────────────────────────────────
# Feature #5: Abstracted so a future JWT middleware can replace the user_id
# check without touching any endpoint logic.

def _assert_ownership(conversation: Conversation, user_id: str | None) -> None:
    """
    Raise 403 if `user_id` does not match the conversation owner.

    Policy:
      - If the conversation has no owner (legacy / public), allow all access.
      - If the conversation has an owner, only that user_id may access it.
      - If the request has no user_id, treat as anonymous — deny ownerless access.
    """
    if conversation.user_id is None:
        return  # legacy public conversation — no restriction
    if user_id is None or user_id != conversation.user_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: this conversation belongs to another user.",
        )


# ─── Background Tasks ─────────────────────────────────────────────────────────

async def _bg_summarize(conversation_id: int) -> None:
    """Background task: summarize conversation if it has grown long enough."""
    async with AsyncSessionLocal() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv:
            await maybe_summarize(db, conv)


async def _bg_store_memory(
    conversation_id: int,
    user_message: str,
    assistant_message: str,
    user_msg_id: int,
    assistant_msg_id: int,
) -> None:
    """Background task: distill and store the current turn as a memory entry."""
    embedder = get_embedder()
    async with AsyncSessionLocal() as db:
        await store_memory(
            db=db,
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
            embedder=embedder,
            message_ids=(user_msg_id, assistant_msg_id),
        )


# ─── POST /api/chat ────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Main chat endpoint.

    Creates or continues a conversation, checks the response cache, runs the
    full RAG pipeline (if no cache hit), stores messages + retrieved chunks,
    and triggers background summarization and memory storage.
    """
    # ── Get or create conversation ───────────────────────────────────────────
    if request.conversation_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == request.conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Feature #5: enforce ownership
        _assert_ownership(conversation, request.user_id)
    else:
        # Auto-title from first message
        title = request.query[:60] + ("..." if len(request.query) > 60 else "")
        conversation = Conversation(
            title=title,
            user_id=request.user_id,  # Feature #5
        )
        db.add(conversation)
        await db.flush()

    # ── Build context (Feature #1 fix + Feature #2 summary) ──────────────────
    summary, history = await get_conversation_context(db, conversation)

    # ── Embed query (needed for cache lookup + memory retrieval) ─────────────
    embedder = get_embedder()
    query_embedding: list[float] = await run_in_threadpool(
        embedder.embed_query, request.query
    )

    # ── Feature #4: Cache lookup ──────────────────────────────────────────────
    kv = await get_knowledge_version(db)
    cached = await get_cached_response(db, query_embedding, kv)

    if cached:
        # Cache hit — store the user message + a synthetic assistant message
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=request.query,
        )
        db.add(user_message)
        await db.flush()

        sources_objs = [SourceCitation(**s) for s in cached["sources"]]
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=cached["answer"],
            sources_json=json.dumps(cached["sources"]),
            retrieved_chunks_json=json.dumps([]),  # no new chunks (served from cache)
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        return ChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            answer=cached["answer"],
            sources=sources_objs,
            query_time_ms=0.0,
            cached=True,
        )

    # ── Feature #7: Retrieve relevant past memories ───────────────────────────
    relevant_memories = await retrieve_memories(
        db=db,
        conversation_id=conversation.id,
        query_embedding=query_embedding,
    )
    if relevant_memories:
        logger.info(
            f"Injecting {len(relevant_memories)} memories into prompt "
            f"for conversation {conversation.id}"
        )

    # ── Store user message ────────────────────────────────────────────────────
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.query,
    )
    db.add(user_message)
    await db.flush()

    # ── Run RAG pipeline ──────────────────────────────────────────────────────
    try:
        result = await run_in_threadpool(
            run_rag_pipeline,
            request.query,
            history,
            summary,             # Feature #2
            relevant_memories,   # Feature #7
        )
    except Exception as e:
        logger.error(f"RAG pipeline error: {e}")
        raise HTTPException(status_code=500, detail="RAG pipeline failed. Please try again.")

    # ── Feature #3: Store retrieved chunks on the message ────────────────────
    raw_chunks: list[dict] = result.get("chunks", [])
    # Serialise only the fields we care about (skip large embeddings)
    chunks_for_storage = [
        {
            "filename": c.get("filename"),
            "category": c.get("category"),
            "page_number": c.get("page_number"),
            "text": c.get("text", "")[:500],
            "rerank_score": round(c.get("rerank_score", 0.0), 6),
            "rrf_score": round(c.get("rrf_score", 0.0), 6),
        }
        for c in raw_chunks
    ]

    # ── Store assistant message ───────────────────────────────────────────────
    sources_json = json.dumps([s.model_dump() for s in result["sources"]])
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result["answer"],
        sources_json=sources_json,
        retrieved_chunks_json=json.dumps(chunks_for_storage),  # Feature #3
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)

    # ── Feature #4: Store response in cache ───────────────────────────────────
    await store_response(
        db=db,
        query_text=request.query,
        query_embedding=query_embedding,
        answer=result["answer"],
        sources=[s.model_dump() for s in result["sources"]],
        knowledge_version=kv,
    )
    await db.commit()

    # ── Log analytics event ───────────────────────────────────────────────────
    await log_event(
        db=db,
        event_type="query",
        query=request.query,
        conversation_id=conversation.id,
        response_time_ms=result["query_time_ms"],
        retrieved_chunks=result["retrieved_chunks"],
    )

    # ── Background tasks ──────────────────────────────────────────────────────
    # Feature #2: Summarize if conversation is long enough
    background_tasks.add_task(_bg_summarize, conversation.id)

    # Feature #7: Store this turn as a memory entry
    background_tasks.add_task(
        _bg_store_memory,
        conversation.id,
        request.query,
        result["answer"],
        user_message.id,
        assistant_message.id,
    )

    return ChatResponse(
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        answer=result["answer"],
        sources=result["sources"],
        query_time_ms=result["query_time_ms"],
        cached=False,
    )


# ─── GET /api/conversations ───────────────────────────────────────────────────

@router.get("/conversations", response_model=list[ConversationListItem])
async def list_conversations(
    skip: int = 0,
    limit: int = 50,
    # Feature #5: optional filter — only return this user's conversations
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List conversations with message counts.

    If `user_id` is provided, returns only that user's conversations.
    Omit `user_id` to list all conversations (admin use or anonymous mode).
    """
    query = select(Conversation).order_by(Conversation.updated_at.desc())
    if user_id:
        query = query.where(Conversation.user_id == user_id)

    result = await db.execute(query.offset(skip).limit(limit))
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
                user_id=conv.user_id,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=count_result or 0,
            )
        )
    return output


# ─── GET /api/conversations/{id} ─────────────────────────────────────────────

@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: int,
    user_id: str | None = None,  # Feature #5
    db: AsyncSession = Depends(get_db),
):
    """Get a conversation with all its messages."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Feature #5: ownership check
    _assert_ownership(conversation, user_id)

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        user_id=conversation.user_id,
        summary=conversation.summary,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=[SourceCitation(**s) for s in m.sources],
                retrieved_chunks=m.retrieved_chunks,  # Feature #3
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


# ─── DELETE /api/conversations/{id} ──────────────────────────────────────────

@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: int,
    user_id: str | None = None,  # Feature #5
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Feature #5: ownership check
    _assert_ownership(conv, user_id)

    await db.delete(conv)
    await db.commit()


# ─── GET /api/conversations/{id}/memories (debug) ────────────────────────────

@router.get(
    "/conversations/{conversation_id}/memories",
    response_model=list[MemoryOut],
)
async def get_conversation_memories(
    conversation_id: int,
    user_id: str | None = None,  # Feature #5
    db: AsyncSession = Depends(get_db),
):
    """
    List stored memory entries for a conversation (debug / QA endpoint).
    Useful for inspecting what the memory layer has learned about a conversation.
    """
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    _assert_ownership(conversation, user_id)

    mem_result = await db.execute(
        select(ConversationMemory)
        .where(ConversationMemory.conversation_id == conversation_id)
        .order_by(ConversationMemory.created_at.desc())
    )
    memories = mem_result.scalars().all()
    return [
        MemoryOut(
            id=m.id,
            conversation_id=m.conversation_id,
            content_summary=m.content_summary,
            turn_range=m.turn_range,
            created_at=m.created_at,
        )
        for m in memories
    ]
