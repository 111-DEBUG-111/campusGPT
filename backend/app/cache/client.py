"""
Upstash Redis Client Singleton for CampusGPT.

Uses the upstash-redis HTTP client — works on Render free tier where
persistent TCP connections to external Redis are unreliable.

Graceful degradation: if UPSTASH_REDIS_URL / UPSTASH_REDIS_TOKEN are not
configured, get_redis() returns None and all cache operations become no-ops.
"""
import logging
from upstash_redis import Redis
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_client: Redis | None = None
_init_attempted: bool = False


def get_redis() -> Redis | None:
    """
    Return the Upstash Redis singleton, or None if not configured.

    Thread-safe for read-only singleton access.  The first call initialises
    the client; subsequent calls return the cached reference.
    """
    global _redis_client, _init_attempted

    if _init_attempted:
        return _redis_client

    _init_attempted = True

    if not settings.upstash_redis_url or not settings.upstash_redis_token:
        logger.warning(
            "UPSTASH_REDIS_URL / UPSTASH_REDIS_TOKEN not set. "
            "Response caching is DISABLED."
        )
        return None

    try:
        _redis_client = Redis(
            url=settings.upstash_redis_url,
            token=settings.upstash_redis_token,
        )
        logger.info("Upstash Redis client initialised.")
    except Exception as exc:  # pragma: no cover
        logger.error(f"Failed to initialise Upstash Redis client: {exc}")
        _redis_client = None

    return _redis_client


async def ping_redis() -> bool:
    """
    Test connectivity to Upstash Redis.  Called once on startup.
    Returns True on success, False on failure or if not configured.
    """
    redis = get_redis()
    if redis is None:
        return False
    try:
        result = redis.ping()
        logger.info(f"Upstash Redis ping: {result}")
        return True
    except Exception as exc:
        logger.error(f"Upstash Redis ping failed: {exc}")
        return False
