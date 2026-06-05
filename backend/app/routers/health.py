"""
Health Check Router
"""
from fastapi import APIRouter
from app.config import get_settings
from app.rag.bm25_index import get_bm25_index

settings = get_settings()
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Health check endpoint for Render and uptime monitoring."""
    bm25 = get_bm25_index()
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "bm25_chunks": bm25.chunk_count,
    }
