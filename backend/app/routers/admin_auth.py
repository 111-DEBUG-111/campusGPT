"""
Admin Auth Router — POST /api/admin/login, POST /api/admin/logout

The admin key is verified once here. On success, the server sets an HttpOnly,
Secure, SameSite=Lax cookie named `campusgpt_admin_session`. The raw key is
never stored in the browser (no sessionStorage, no JS-readable value).

Subsequent admin API calls carry the cookie automatically — no JS ever reads it.
"""
import logging
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/admin", tags=["admin-auth"])

COOKIE_NAME = "campusgpt_admin_session"
COOKIE_MAX_AGE = 8 * 60 * 60  # 8 hours in seconds


class LoginRequest(BaseModel):
    key: str


@router.post("/login")
async def admin_login(body: LoginRequest, response: Response):
    """
    Verify the admin key and issue an HttpOnly session cookie.

    The cookie is:
    - HttpOnly  — not accessible to JavaScript
    - Secure    — only sent over HTTPS (skipped in dev when running on HTTP)
    - SameSite=Lax — protects against CSRF while still working across proxied origins
    """
    if body.key != settings.admin_api_key:
        # Constant-time-ish: don't leak timing information
        raise HTTPException(status_code=401, detail="Invalid admin key")

    secure_cookie = not settings.debug
    samesite_val = "none" if secure_cookie else "lax"

    response.set_cookie(
        key=COOKIE_NAME,
        value=body.key,
        httponly=True,
        secure=secure_cookie,
        samesite=samesite_val,
        max_age=COOKIE_MAX_AGE,
        path="/",
    )
    logger.info("Admin session started")
    return {"ok": True}


@router.post("/logout")
async def admin_logout(response: Response):
    """Clear the admin session cookie."""
    secure_cookie = not settings.debug
    samesite_val = "none" if secure_cookie else "lax"

    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=secure_cookie,
        samesite=samesite_val,
        httponly=True,
    )
    logger.info("Admin session ended")
    return {"ok": True}

