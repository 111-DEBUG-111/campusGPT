"""
CampusGPT FastAPI Dependencies

get_session_token — extracts and validates the X-Session-Token header.
This is the sole identity mechanism for anonymous user sessions.
Each browser generates a UUID v4 on first visit and sends it on every request.

verify_admin_cookie — validates the HttpOnly campusgpt_admin_session cookie.
The browser never sees the raw admin key; the cookie is set by POST /api/admin/login
and is HttpOnly + SameSite=Lax so it cannot be read or forged via JavaScript.
"""
from typing import Annotated

from fastapi import Header, HTTPException, Request


def get_session_token(
    x_session_token: Annotated[str | None, Header()] = None,
) -> str:
    """
    FastAPI dependency: validates X-Session-Token header and returns the token.

    Returns:
        The raw session token string (UUID v4 or similar).

    Raises:
        HTTPException 401: if the header is absent or suspiciously short.
    """
    if not x_session_token or len(x_session_token) < 8:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid X-Session-Token header. "
                   "Please refresh the page to generate a session.",
        )
    # Trim whitespace / accidental padding
    return x_session_token.strip()


_ADMIN_COOKIE_NAME = "campusgpt_admin_session"


def verify_admin_cookie(request: Request) -> None:
    """
    FastAPI dependency: validates the campusgpt_admin_session HttpOnly cookie.

    The cookie is set by POST /api/admin/login after the admin key is verified
    server-side. It is HttpOnly and SameSite=Lax, so JavaScript cannot read it
    and cross-site requests cannot carry it.

    Raises:
        HTTPException 401: if the cookie is absent or its value does not match
                           the configured ADMIN_API_KEY.
    """
    # Import here to avoid circular imports (config → dependencies → config).
    from app.config import get_settings  # noqa: PLC0415
    settings = get_settings()

    cookie_value = request.cookies.get(_ADMIN_COOKIE_NAME)
    if not cookie_value or cookie_value != settings.admin_api_key:
        raise HTTPException(
            status_code=401,
            detail="Admin session missing or expired. Please log in again.",
        )
