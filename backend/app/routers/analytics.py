"""
Analytics Router — GET /api/admin/analytics
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.limiter import limiter
from app.schemas import AnalyticsSummary
from app.services.analytics_service import get_analytics_summary

settings = get_settings()
router = APIRouter(prefix="/api/admin", tags=["analytics"])


def verify_admin(x_admin_key: Annotated[str | None, Header()] = None) -> None:
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


@router.get("/analytics", response_model=AnalyticsSummary)
@limiter.limit("10/minute")   # heavy DB aggregation — cap dashboard polling
async def analytics_dashboard(
    request: Request,          # required by slowapi for IP extraction
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """Get analytics summary for the admin dashboard."""
    return await get_analytics_summary(db)
