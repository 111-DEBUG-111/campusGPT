"""
Visits Router — POST /api/visit
Records anonymous chat-page visits for unique visitor analytics.
"""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_session_token
from app.limiter import limiter
from app.services.analytics_service import record_visit

router = APIRouter(prefix="/api", tags=["visits"])


@router.post("/visit", status_code=204)
@limiter.limit("30/minute")
async def track_visit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_token: str = Depends(get_session_token),
):
    """Record a chat-page visit for the current browser session."""
    await record_visit(db, session_token)
    return Response(status_code=204)
