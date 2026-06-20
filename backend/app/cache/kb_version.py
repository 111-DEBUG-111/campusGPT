"""
Knowledge Base Version Manager.

Maintains a monotonic integer counter in Redis under the key
``campusgpt:kb_version``.  Every document upload, deletion, or reindex
atomically increments this counter.

Cache keys embed the version string, so old entries become unreachable
the moment the KB changes — no manual FLUSHDB required.

Fail-safe: if Redis is unavailable, functions return 0 (cache effectively
disabled — every request will be a miss and run the full RAG pipeline).
"""
import logging
from app.cache.client import get_redis

logger = logging.getLogger(__name__)

_KB_VERSION_KEY = "campusgpt:kb_version"


def get_kb_version() -> int:
    """
    Return the current KB version integer.

    Returns 0 if Redis is unavailable (safe fallback — disables caching).
    """
    redis = get_redis()
    if redis is None:
        return 0
    try:
        value = redis.get(_KB_VERSION_KEY)
        if value is None:
            # First time: initialise to 1
            redis.set(_KB_VERSION_KEY, 1)
            logger.info("KB version initialised to 1")
            return 1
        return int(value)
    except Exception as exc:
        logger.error(f"get_kb_version failed: {exc}")
        return 0


def bump_kb_version() -> int:
    """
    Atomically increment the KB version and return the new value.

    Called after every document upload, deletion, or reindex so that
    all previously cached responses are automatically invalidated.
    Returns 0 if Redis is unavailable.
    """
    redis = get_redis()
    if redis is None:
        logger.warning("bump_kb_version: Redis unavailable, skipping increment")
        return 0
    try:
        new_version = redis.incr(_KB_VERSION_KEY)
        logger.info(f"KB version bumped to {new_version}")
        return new_version
    except Exception as exc:
        logger.error(f"bump_kb_version failed: {exc}")
        return 0
