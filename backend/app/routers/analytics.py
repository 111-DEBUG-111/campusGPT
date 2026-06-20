"""
Analytics Router — GET /api/admin/analytics
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import verify_admin_cookie
from app.limiter import limiter
from app.schemas import AnalyticsSummary
from app.services.analytics_service import get_analytics_summary

router = APIRouter(prefix="/api/admin", tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsSummary)
@limiter.limit("10/minute")   # heavy DB aggregation — cap dashboard polling
async def analytics_dashboard(
    request: Request,          # required by slowapi for IP extraction
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_cookie),
):
    """Get analytics summary for the admin dashboard."""
    return await get_analytics_summary(db)
