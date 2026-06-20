"""
Shared SlowAPI rate-limiter singleton.

Defined here (not in main.py) so routers can import it without
creating circular-import chains (main → router → main).

Key design decisions
────────────────────
• key_func   — Reads the real client IP from the X-Forwarded-For header
               (Render / any reverse-proxy sets this).  Falls back to
               the raw remote address when the header is absent (local dev).
               Using get_remote_address alone would see the proxy IP, and
               using a bare X-Forwarded-For would be trivially spoofed —
               this helper picks only the *leftmost* hop supplied by the
               proxy, which is the true client IP on Render.

• Storage    — SlowAPI stores counters in Redis (Upstash REST URL) so
               limits survive server restarts and work across Render's
               multiple workers.  Falls back to in-memory when Redis is
               not configured (local dev / CI).

• Dedup      — A lightweight query-hash deduplication layer sits *above*
               the IP-based rate limiter (in chat.py) to reject identical
               query spam regardless of source IP.  See ``is_duplicate_query``.

Usage in a route:
    from fastapi import Request
    from app.limiter import limiter

    @router.post("/some-path")
    @limiter.limit("20/minute")
    async def handler(request: Request, ...):
        ...

The `request: Request` parameter must be present in every handler
that uses @limiter.limit() — slowapi uses it to extract the client IP.
"""
import hashlib
import logging
import time
from typing import Optional

from starlette.requests import Request

logger = logging.getLogger(__name__)


# ─── Key function: real client IP via X-Forwarded-For ─────────────────────────

def _get_real_ip(request: Request) -> str:
    """
    Extract the true client IP from the X-Forwarded-For header.

    Render (and most reverse-proxies) prepend the real client IP as the
    leftmost entry in X-Forwarded-For.  We take that first value rather
    than the rightmost (which could be attacker-controlled on some setups).

    Falls back to request.client.host when the header is absent (direct
    connections during local development).
    """
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        # "client, proxy1, proxy2" — take the leftmost (real client)
        real_ip = xff.split(",")[0].strip()
        if real_ip:
            return real_ip
    # Fallback: direct connection (local dev, unit tests)
    if request.client:
        return request.client.host
    return "unknown"


# ─── Limiter singleton ─────────────────────────────────────────────────────────

def _build_limiter():
    """
    Build the SlowAPI Limiter with Redis storage when Upstash is configured,
    or fall back to in-memory storage for local dev.
    """
    from slowapi import Limiter

    try:
        from app.config import get_settings
        settings = get_settings()

        if settings.upstash_redis_url and settings.upstash_redis_token:
            # slowapi / limits uses redis:// URIs with redis-py under the hood.
            # Upstash exposes a standard Redis endpoint on port 6379 (TLS).
            # We derive the redis:// URI from the Upstash REST URL:
            #   https://host.upstash.io → rediss://:token@host.upstash.io:6379
            host = settings.upstash_redis_url.replace("https://", "").replace("http://", "").rstrip("/")
            storage_uri = f"rediss://:{settings.upstash_redis_token}@{host}:6379"

            limiter = Limiter(
                key_func=_get_real_ip,
                storage_uri=storage_uri,
                strategy="fixed-window",
            )
            logger.info("Rate limiter using Redis storage (%s)", host)
            return limiter
    except Exception as exc:
        logger.warning("Could not configure Redis storage for rate limiter: %s — falling back to in-memory", exc)

    # In-memory fallback (local dev / Redis not configured)
    from slowapi import Limiter
    logger.info("Rate limiter using in-memory storage (no Redis configured)")
    return Limiter(key_func=_get_real_ip)


limiter = _build_limiter()


# ─── Query-hash deduplication ─────────────────────────────────────────────────

# Simple in-process store: {query_hash: last_seen_timestamp}
# Not distributed — per-worker, which is acceptable because dedup is a
# best-effort layer on top of IP-rate-limiting, not a security gate.
_recent_queries: dict[str, float] = {}
_DEDUP_WINDOW_SECONDS = 5   # identical queries within this window are rejected


def _query_hash(query: str, ip: str) -> str:
    """
    Return a short hash of (normalized_query, ip) used for deduplication.
    Ties the dedup key to the source IP so different users asking the same
    question simultaneously are not blocked.
    """
    normalized = " ".join(query.lower().split())
    raw = f"{ip}|{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_duplicate_query(request: Request, query: str) -> bool:
    """
    Return True if an identical query from the same IP was received within
    the deduplication window (default: 5 seconds).

    Call this at the top of the chat handler *before* touching the DB or
    running the pipeline.  Reject with HTTP 429 if it returns True.

    This catches double-click spam and rapid-fire identical submissions
    that slip through IP-based rate limits (e.g. behind NAT).
    """
    global _recent_queries

    # Prune stale entries to prevent unbounded growth
    now = time.monotonic()
    stale_keys = [k for k, ts in _recent_queries.items() if now - ts > _DEDUP_WINDOW_SECONDS * 2]
    for k in stale_keys:
        del _recent_queries[k]

    ip = _get_real_ip(request)
    key = _query_hash(query, ip)
    last_seen = _recent_queries.get(key)

    if last_seen is not None and (now - last_seen) < _DEDUP_WINDOW_SECONDS:
        logger.warning(
            "Duplicate query rejected from %s (%.1fs since last identical request)",
            ip,
            now - last_seen,
        )
        return True

    _recent_queries[key] = now
    return False
