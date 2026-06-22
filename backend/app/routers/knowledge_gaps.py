"""
Knowledge Gaps Router — GET /api/admin/knowledge-gaps
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import verify_admin_cookie
from app.limiter import limiter
from app.schemas import KnowledgeGapOut
from app.services.knowledge_gap_service import get_knowledge_gaps

router = APIRouter(prefix="/api/admin", tags=["knowledge-gaps"])


@router.get("/knowledge-gaps", response_model=list[KnowledgeGapOut])
@limiter.limit("30/minute")
async def list_knowledge_gaps(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_cookie),
):
    """List university questions the KB could not fully answer."""
    gaps = await get_knowledge_gaps(db)
    return gaps
