"""
Response Cache Service — Feature #4.

Architecture:
  - Hot path: in-memory OrderedDict (LRU eviction, max N entries)
  - Cold path: SQLite `response_cache` table (survives restarts)
  - Cache key: semantic similarity ≥ threshold AND knowledge_version match

Invalidation strategy:
  - Every document change (upload / update / delete / re-index) increments
    the `knowledge_version` counter in the `knowledge_version` table.
  - Cache lookups compare the stored knowledge_version against the current one.
    Mismatched entries are skipped (logically stale) — no table scan needed.
  - Expired entries are removed lazily on access (TTL-based).

Upgrade path to Redis:
  Replace `_MemoryCache` and the SQLite persistence methods with a Redis client.
  The public interface (get_cached_response / store_response / bump_knowledge_version)
  stays identical, so the chat router needs no changes.
"""
import json
import logging
import math
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import ResponseCache, KnowledgeVersion
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── In-Memory LRU Cache ──────────────────────────────────────────────────────

class _MemoryCache:
    """
    Thread-unsafe in-memory LRU cache for same-process access.
    FastAPI runs in a single async event loop so this is safe.
    """
    def __init__(self, max_size: int):
        self._max = max_size
        self._store: OrderedDict[int, dict] = OrderedDict()  # db_id → entry

    def get(self, db_id: int) -> dict | None:
        if db_id not in self._store:
            return None
        self._store.move_to_end(db_id)  # mark as recently used
        return self._store[db_id]

    def put(self, db_id: int, entry: dict) -> None:
        self._store[db_id] = entry
        self._store.move_to_end(db_id)
        if len(self._store) > self._max:
            self._store.popitem(last=False)  # evict LRU

    def evict(self, db_id: int) -> None:
        self._store.pop(db_id, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


# Module-level singleton — shared across all requests in the process.
_memory_cache = _MemoryCache(max_size=settings.cache_max_memory_entries)


# ─── Cosine Similarity ────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Efficient dot-product cosine similarity for equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ─── Knowledge Version Helpers ────────────────────────────────────────────────

async def get_knowledge_version(db: AsyncSession) -> int:
    """Return the current knowledge version (creates the row if it doesn't exist)."""
    row = await db.get(KnowledgeVersion, 1)
    if row is None:
        row = KnowledgeVersion(id=1, version=0)
        db.add(row)
        await db.flush()
    return row.version


async def bump_knowledge_version(db: AsyncSession) -> int:
    """
    Increment the knowledge version counter.
    Called whenever the knowledge base changes (upload / delete / re-index).
    All existing cache entries with the old version are now logically stale
    and will be skipped on the next lookup — no explicit DELETE needed.
    """
    row = await db.get(KnowledgeVersion, 1)
    if row is None:
        row = KnowledgeVersion(id=1, version=1)
        db.add(row)
    else:
        row.version += 1
    await db.flush()
    # Also clear the in-memory cache so we don't serve stale entries within
    # the same process restart cycle.
    _memory_cache.clear()
    logger.info(f"Knowledge version bumped to {row.version}. Response cache invalidated.")
    return row.version


# ─── Public Interface ─────────────────────────────────────────────────────────

async def get_cached_response(
    db: AsyncSession,
    query_embedding: list[float],
    knowledge_version: int,
) -> Optional[dict]:
    """
    Look up a cached response for the given query embedding.

    Returns a dict with keys `answer`, `sources` (list[dict]) if a cache hit
    is found, or None otherwise.

    Cache hit conditions:
      1. `knowledge_version` in the DB entry matches the current version.
      2. Cosine similarity between stored and query embedding ≥ threshold.
      3. Entry has not expired (expires_at > now).
    """
    now = datetime.now(timezone.utc)
    threshold = settings.cache_similarity_threshold

    # Load all non-expired entries with the correct knowledge version.
    result = await db.execute(
        select(ResponseCache)
        .where(ResponseCache.knowledge_version == knowledge_version)
        .where(ResponseCache.expires_at > now)
        .order_by(ResponseCache.hit_count.desc())  # check popular entries first
        .limit(200)  # guard against huge tables
    )
    candidates = result.scalars().all()

    best_sim = 0.0
    best_entry: ResponseCache | None = None

    for entry in candidates:
        # Try memory cache first (avoids JSON decode)
        mem = _memory_cache.get(entry.id)
        if mem:
            stored_emb = mem["embedding"]
        else:
            stored_emb = json.loads(entry.query_embedding_json)
            _memory_cache.put(entry.id, {"embedding": stored_emb, "db_id": entry.id})

        sim = _cosine_similarity(query_embedding, stored_emb)
        if sim > best_sim:
            best_sim = sim
            best_entry = entry

    if best_entry is None or best_sim < threshold:
        logger.debug(f"Cache miss (best similarity={best_sim:.4f}, threshold={threshold})")
        return None

    # Cache hit — increment counter and return
    best_entry.hit_count += 1
    await db.flush()
    logger.info(
        f"Cache HIT (similarity={best_sim:.4f}, hits={best_entry.hit_count}, "
        f"id={best_entry.id}): '{best_entry.query_text[:60]}'"
    )
    return {
        "answer": best_entry.answer,
        "sources": json.loads(best_entry.sources_json),
    }


async def store_response(
    db: AsyncSession,
    query_text: str,
    query_embedding: list[float],
    answer: str,
    sources: list[dict],
    knowledge_version: int,
) -> None:
    """
    Persist a new cache entry to SQLite and warm the in-memory cache.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.cache_ttl_seconds)
    entry = ResponseCache(
        query_text=query_text,
        query_embedding_json=json.dumps(query_embedding),
        knowledge_version=knowledge_version,
        answer=answer,
        sources_json=json.dumps(sources),
        expires_at=expires_at,
    )
    db.add(entry)
    await db.flush()
    _memory_cache.put(entry.id, {"embedding": query_embedding, "db_id": entry.id})
    logger.debug(f"Cached response for query '{query_text[:60]}' (expires {expires_at})")
