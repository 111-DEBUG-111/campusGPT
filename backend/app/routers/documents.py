"""
Documents Router — Admin upload, indexing, listing, deletion.
Protected by ADMIN_API_KEY header.
"""
import logging
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Header, Request, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db, AsyncSessionLocal
from app.limiter import limiter
from app.models import Document
from app.schemas import DocumentOut, DocumentListResponse, ReindexResponse
from app.services.document_service import (
    save_upload, process_document, delete_document, rebuild_bm25_from_vectorstore
)

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/admin", tags=["admin"])

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}
MAX_SIZE_BYTES = settings.max_upload_size_mb * 1024 * 1024


def verify_admin(x_admin_key: Annotated[str | None, Header()] = None) -> None:
    """Dependency: validates the X-Admin-Key header."""
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing admin API key")


@router.post("/upload", response_model=DocumentOut)
@limiter.limit("10/minute")   # admin uploads: conservative limit to protect the embedding queue
async def upload_document(
    request: Request,          # required by slowapi for IP extraction
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form(default="general"),
    description: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """
    Upload a PDF/TXT/MD document and trigger background indexing.

    Supported categories: general, academics, placements, hostel, clubs, policies, faq
    """
    # Validate file type
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {settings.max_upload_size_mb}MB"
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Reset file pointer for uploading to R2
    await file.seek(0)

    # Upload to Cloudflare R2
    r2_key, file_size = await save_upload(file)

    # Create DB record  (filename stores the R2 object key)
    doc = Document(
        filename=r2_key,
        original_filename=file.filename,
        category=category,
        description=description or None,
        status="pending",
        file_size_bytes=file_size,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    logger.info(f"Document uploaded: {file.filename} → R2 key={r2_key}, id={doc.id}, queued for indexing")

    async def _index_in_background():
        """Creates its own DB session — safe to run after the request session closes."""
        async with AsyncSessionLocal() as bg_db:
            try:
                await process_document(
                    document_id=doc.id,
                    r2_key=r2_key,
                    filename=file.filename,
                    category=category,
                    db=bg_db,
                )
            except Exception as e:
                logger.error(f"Background indexing failed for doc {doc.id}: {e}")

    background_tasks.add_task(_index_in_background)
    return doc


@router.get("/documents", response_model=DocumentListResponse)
@limiter.limit("60/minute")   # read-only, cheap — relaxed limit
async def list_documents(
    request: Request,          # required by slowapi for IP extraction
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """List all uploaded documents with their indexing status."""
    result = await db.execute(
        select(Document).order_by(Document.uploaded_at.desc())
    )
    docs = result.scalars().all()
    return DocumentListResponse(documents=list(docs), total=len(docs))


@router.delete("/documents/{document_id}", status_code=204)
@limiter.limit("20/minute")   # destructive — moderate cap
async def delete_doc(
    request: Request,          # required by slowapi for IP extraction
    document_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """Delete a document from pgvector, BM25, R2 storage, and DB."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await delete_document(document_id, db)


@router.post("/reindex", response_model=ReindexResponse)
@limiter.limit("3/minute")    # STRICTEST: triggers full BM25 rebuild — very expensive
async def reindex_all(
    request: Request,          # required by slowapi for IP extraction
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """
    Rebuild BM25 index from pgvector (useful after manual data changes).
    Does NOT re-embed documents — use delete + re-upload for that.
    """
    chunk_count = await rebuild_bm25_from_vectorstore()
    result = await db.execute(
        select(Document).where(Document.status == "indexed")
    )
    docs = result.scalars().all()
    return ReindexResponse(
        message=f"BM25 rebuilt from {chunk_count} chunks",
        documents_reindexed=len(docs),
    )


@router.get("/documents/{document_id}", response_model=DocumentOut)
@limiter.limit("60/minute")   # read-only, cheap — relaxed limit
async def get_document(
    request: Request,          # required by slowapi for IP extraction
    document_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin),
):
    """Get details for a single document."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc
