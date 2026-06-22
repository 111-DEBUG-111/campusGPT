"""
CampusGPT Response Cache — Core Logic.

Architecture
────────────
• Storage:   Upstash Redis (HTTP, serverless, survives Render restarts)
• Key:       SHA-256(normalized_query + "|v" + kb_version)
• TTL:       Configurable via CACHE_TTL_SECONDS (default 24 h)
• Layer:     Final LLM responses only (retrieval / reranking NOT cached)

Normalization (strict)
──────────────────────
Only three minimal transformations are applied so that slightly-different
queries produce different keys and therefore independent RAG responses:

  1. lowercase + strip surrounding whitespace
  2. strip terminal punctuation (? ! .)
  3. collapse internal whitespace to a single space

This means:
  "What is the attendance policy?"  →  "what is the attendance policy"
  "what is the attendance policy"   →  "what is the attendance policy"  ✅ HIT
  "Explain attendance requirements" →  "explain attendance requirements" ❌ MISS (correct)

Cache-eligibility validation (before SET)
──────────────────────────────────────────
  • result["is_error"] must be False
  • answer length > 50 characters (not empty / trivially short)
  • retrieved_chunks > 0 (retrieval actually returned something)
  • answer must NOT start with the known fallback prefix

Size guard
──────────
Responses larger than MAX_CACHE_VALUE_BYTES (512 KB) are skipped to stay
within Upstash's 1 MB per-value limit.

Fail-open design
────────────────
Any Redis error is caught and logged.  A miss is returned instead of
raising, so the RAG pipeline always runs as fallback.
"""
import hashlib
import json
import logging
import re

from app.cache.client import get_redis
from app.cache.kb_version import get_kb_version
from app.config import get_settings

logger = logging.getLogger(__name__)

# NOTE: `settings` is intentionally left as a module-level name so that
# unit tests can patch `app.cache.response_cache.settings` directly.
# It is NOT frozen at import time — we call get_settings() here which
# returns the lru_cached singleton, but tests replace this name with a
# MagicMock, so every function that reads `settings` at call-time will
# pick up the patched version.
settings = get_settings()

# Responses larger than this are not cached (Upstash 1 MB value limit guard)
MAX_CACHE_VALUE_BYTES = 512 * 1024  # 512 KB

# Prefix for all cache keys — makes flushing or inspecting easy
_KEY_PREFIX = "campusgpt:response:"

# Known fallback / error answer prefixes that must never be cached
_ERROR_PREFIXES = (
    "I'm having trouble",
    "I am having trouble",
    "Sorry, I couldn't",
    "An error occurred",
    "I couldn't generate",
)


# ─── Normalization ─────────────────────────────────────────────────────────────

def _normalize_query(query: str) -> str:
    """
    Apply minimal normalization so only cosmetically identical queries share
    a cache key.  Slightly different wording → different key → independent answer.

    Steps:
      1. lowercase + strip surrounding whitespace
      2. strip terminal punctuation (? ! .)
      3. collapse internal whitespace to single space
    """
    q = query.lower().strip()
    # Strip trailing ?, !, .
    q = q.rstrip("?!.")
    # Collapse internal whitespace
    q = re.sub(r"\s+", " ", q).strip()
    return q


# ─── Cache Key ─────────────────────────────────────────────────────────────────

def make_cache_key(query: str, kb_version: int) -> str:
    """
    Build a stable cache key that is invalidated automatically when the
    knowledge base changes.

    Format: sha256(normalized_query + "|v" + str(kb_version))
    """
    normalized = _normalize_query(query)
    raw = f"{normalized}|v{kb_version}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{_KEY_PREFIX}{digest}"


# ─── Eligibility Check ─────────────────────────────────────────────────────────

def is_cacheable(result: dict) -> bool:
    """
    Return True only if *result* represents a genuine, complete RAG answer
    that is safe to cache.

    Rejection criteria:
      • is_error flag set to True
      • empty or very short answer (< 50 chars)
      • no chunks retrieved from the knowledge base
      • answer starts with a known error / fallback prefix
    """
    if result.get("is_error", True):
        logger.debug("Cache skip: is_error=True")
        return False

    answer: str = result.get("answer", "")
    if not answer or len(answer.strip()) < 50:
        logger.debug("Cache skip: answer too short (%d chars)", len(answer))
        return False

    if result.get("retrieved_chunks", 0) == 0:
        logger.debug("Cache skip: retrieved_chunks=0")
        return False

    if any(answer.startswith(prefix) for prefix in _ERROR_PREFIXES):
        logger.debug("Cache skip: answer matches fallback prefix")
        return False

    return True


# ─── Get ───────────────────────────────────────────────────────────────────────

def get_cached_response(query: str) -> dict | None:
    """
    Look up a cached RAG response for *query*.

    Returns the decoded result dict on a hit, or None on a miss / error.
    Also returns None if caching is disabled (CACHE_ENABLED=false or Redis
    not configured).
    """
    # Use getattr so tests that replace `settings` with a MagicMock still
    # behave correctly even if cache_enabled is not explicitly set.
    if not getattr(settings, "cache_enabled", True):
        return None

    redis = get_redis()
    if redis is None:
        return None

    kb_version = get_kb_version()
    if kb_version == 0:
        # Redis unavailable — skip cache entirely
        return None

    key = make_cache_key(query, kb_version)
    try:
        raw = redis.get(key)
        if raw is None:
            return None
        data = json.loads(raw)
        logger.info("Cache HIT for key %s (kb_version=%d)", key[-12:], kb_version)
        return data
    except json.JSONDecodeError as exc:
        logger.warning("Cache value JSON decode error for key %s: %s", key[-12:], exc)
        return None
    except Exception as exc:
        logger.error("Cache GET error: %s", exc)
        return None


# ─── Set ───────────────────────────────────────────────────────────────────────

def set_cached_response(query: str, result: dict) -> None:
    """
    Store a validated RAG response in Redis.

    *result* must pass ``is_cacheable()`` before calling this function.
    The KB version is fetched internally so the key is always consistent.

    No-op on Redis errors (fail-open).
    """
    # Use getattr so tests that replace `settings` with a MagicMock still
    # behave correctly even if cache_enabled is not explicitly set.
    if not getattr(settings, "cache_enabled", True):
        return

    redis = get_redis()
    if redis is None:
        return

    kb_version = get_kb_version()
    if kb_version == 0:
        return

    # Build a cacheable payload — store sources as plain dicts (serializable)
    payload = {
        "answer": result["answer"],
        "sources": [
            s.model_dump() if hasattr(s, "model_dump") else s
            for s in result.get("sources", [])
        ],
        "retrieved_chunks": result.get("retrieved_chunks", 0),
        # Do NOT cache query_time_ms — it's pipeline-specific and misleading
        # for cached responses; the router will use the actual cache lookup time.
    }

    try:
        raw = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        logger.error("Cache serialization error: %s", exc)
        return

    # Size guard: skip caching if payload exceeds the Upstash value limit
    if len(raw.encode("utf-8")) > MAX_CACHE_VALUE_BYTES:
        logger.warning(
            "Cache skip: payload too large (%d bytes > %d byte limit)",
            len(raw.encode("utf-8")),
            MAX_CACHE_VALUE_BYTES,
        )
        return

    key = make_cache_key(query, kb_version)
    try:
        redis.set(key, raw, ex=settings.cache_ttl_seconds)
        logger.info(
            "Cache SET key %s (kb_version=%d, ttl=%ds, size=%d bytes)",
            key[-12:],
            kb_version,
            settings.cache_ttl_seconds,
            len(raw),
        )
    except Exception as exc:
        logger.error("Cache SET error: %s", exc)


# ─── Flush (admin) ─────────────────────────────────────────────────────────────

def flush_response_cache() -> int:
    """
    Delete all cached response keys from Redis.

    Uses SCAN + DEL with the key prefix pattern so only CampusGPT response
    entries are removed — other Redis keys (e.g. kb_version) are preserved.

    Returns the number of keys deleted, or -1 on error.
    """
    redis = get_redis()
    if redis is None:
        logger.warning("flush_response_cache: Redis not available")
        return 0

    pattern = f"{_KEY_PREFIX}*"
    deleted = 0
    try:
        cursor = 0
        while True:
            cursor, keys = redis.scan(cursor, match=pattern, count=100)
            if keys:
                redis.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        logger.info("Cache flush: deleted %d response keys", deleted)
        return deleted
    except Exception as exc:
        logger.error("Cache flush error: %s", exc)
        return -1
