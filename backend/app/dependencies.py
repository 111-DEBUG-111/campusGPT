"""
CampusGPT FastAPI Dependencies

get_session_token — extracts and validates the X-Session-Token header.
This is the sole identity mechanism for anonymous user sessions.
Each browser generates a UUID v4 on first visit and sends it on every request.
"""
from typing import Annotated

from fastapi import Header, HTTPException


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
