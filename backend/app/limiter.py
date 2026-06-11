"""
Shared SlowAPI rate-limiter singleton.

Defined here (not in main.py) so routers can import it without
creating circular-import chains (main → router → main).

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
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
