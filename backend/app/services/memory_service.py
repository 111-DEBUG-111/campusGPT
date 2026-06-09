"""
Memory Service — Feature #7: Long-term conversational memory retrieval.

Architecture (V1 — SQLite-backed):
  - After each assistant response, a background task distills the turn into a
    short memory entry and embeds it.
  - At query time, all memories for the conversation are fetched and the top-K
    most relevant (by cosine similarity to the current query) are injected into
    the system prompt.

Abstraction contract:
  All callers interact with `store_memory()` and `retrieve_memories()` only.
  The underlying storage (SQLite JSON vectors today) is contained in this module.
  To migrate to Qdrant:
    1. Replace `_store_in_sqlite` / `_retrieve_from_sqlite` with Qdrant equivalents.
    2. Keep the public function signatures identical.
    3. No changes required in chat.py or pipeline.py.

Scaling note:
  SQLite JSON vector search is O(n) — fine up to ~10k memories per conversation.
  Beyond that, migrate `ConversationMemory` to a dedicated Qdrant collection.
"""
import json
import logging
import math
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import ConversationMemory
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Cosine Similarity (local, no external dependency) ───────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ─── Storage Backend (SQLite) — swap this block for Qdrant in V2 ──────────────

async def _store_in_sqlite(
    db: AsyncSession,
    conversation_id: int,
    content_summary: str,
    embedding: list[float],
    turn_range: str | None,
) -> None:
    memory = ConversationMemory(
        conversation_id=conversation_id,
        content_summary=content_summary,
        embedding_json=json.dumps(embedding),
        turn_range=turn_range,
    )
    db.add(memory)
    await db.flush()


async def _retrieve_from_sqlite(
    db: AsyncSession,
    conversation_id: int,
    query_embedding: list[float],
    top_k: int,
) -> list[str]:
    """
    Fetch all memories for the conversation and return top-k by cosine similarity.
    Returns a list of content_summary strings.
    """
    result = await db.execute(
        select(ConversationMemory)
        .where(ConversationMemory.conversation_id == conversation_id)
        .order_by(ConversationMemory.created_at.desc())
        .limit(500)  # safety cap — beyond this, migrate to Qdrant
    )
    memories = result.scalars().all()

    if not memories:
        return []

    scored: list[tuple[float, str]] = []
    for mem in memories:
        emb = json.loads(mem.embedding_json)
        sim = _cosine_similarity(query_embedding, emb)
        scored.append((sim, mem.content_summary))

    # Sort by similarity descending, return top_k summaries
    scored.sort(key=lambda x: x[0], reverse=True)
    return [summary for _, summary in scored[:top_k]]


# ─── Public Interface ─────────────────────────────────────────────────────────

async def store_memory(
    db: AsyncSession,
    conversation_id: int,
    user_message: str,
    assistant_message: str,
    embedder,
    message_ids: Optional[tuple[int, int]] = None,
) -> None:
    """
    Distill a user/assistant turn into a memory entry and store it.

    Called as a BackgroundTask after each successful response — never blocks
    the main request.

    Args:
        db: Async DB session (should be a fresh background session).
        conversation_id: The conversation this memory belongs to.
        user_message: The user's question for this turn.
        assistant_message: The assistant's answer for this turn.
        embedder: The BGE embedder singleton.
        message_ids: Optional (user_msg_id, assistant_msg_id) for turn_range.
    """
    # Distill turn into a concise memory string (no extra LLM call needed)
    memory_text = (
        f"Student asked: {user_message[:200]}\n"
        f"CampusGPT answered: {assistant_message[:300]}"
    )

    try:
        embedding = embedder.embed_query(memory_text)
    except Exception as e:
        logger.error(f"Memory embedding failed for conv {conversation_id}: {e}")
        return

    turn_range = None
    if message_ids:
        turn_range = f"{message_ids[0]}-{message_ids[1]}"

    try:
        await _store_in_sqlite(
            db=db,
            conversation_id=conversation_id,
            content_summary=memory_text,
            embedding=embedding,
            turn_range=turn_range,
        )
        await db.commit()
        logger.debug(f"Memory stored for conversation {conversation_id}")
    except Exception as e:
        logger.error(f"Memory storage failed for conv {conversation_id}: {e}")


async def retrieve_memories(
    db: AsyncSession,
    conversation_id: int,
    query_embedding: list[float],
    top_k: int | None = None,
) -> list[str]:
    """
    Retrieve the most relevant past memories for the current query.

    Returns a list of human-readable memory strings, ordered by relevance.
    Returns an empty list if no memories exist yet.
    """
    top_k = top_k or settings.memory_retrieval_top_k
    return await _retrieve_from_sqlite(db, conversation_id, query_embedding, top_k)


def format_memories(memories: list[str]) -> str:
    """Format retrieved memories into a readable block for the system prompt."""
    if not memories:
        return ""
    parts = [f"[Memory {i+1}] {m}" for i, m in enumerate(memories)]
    return "\n\n".join(parts)
