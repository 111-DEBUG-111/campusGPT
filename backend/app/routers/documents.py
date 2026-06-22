"""
Documents Router — Admin upload, indexing, listing, deletion, and source editing.
Protected by ADMIN_API_KEY header.
"""
import logging
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Header, Request, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.database import get_db, AsyncSessionLocal
from app.dependencies import verify_admin_cookie
from app.limiter import limiter
from app.models import Document
from app.schemas import DocumentOut, DocumentListResponse, ReindexResponse, DocumentUpdate
from app.services.document_service import (
    save_upload, process_document, delete_document,
    rebuild_bm25_from_vectorstore, update_document_source,
)
from app.cache.response_cache import flush_response_cache

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/admin", tags=["admin"])

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}
MAX_SIZE_BYTES = settings.max_upload_size_mb * 1024 * 1024
ALLOWED_SOURCE_TYPES = {"official", "experience"}


@router.post("/upload", response_model=DocumentOut)
@limiter.limit("10/minute")   # admin uploads: conservative limit to protect the embedding queue
async def upload_document(
    request: Request,          # required by slowapi for IP extraction
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form(default="general"),
    description: str = Form(default=""),
    source_type: str = Form(default="official"),   # mandatory — "official" | "experience"
    author: str = Form(default=""),                # optional; only meaningful for experience
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_cookie),
):
    """
    Upload a PDF/TXT/MD document and trigger background indexing.

    Supported categories: general, academics, placements, hostel, clubs, policies, faq
    Knowledge Source: official | experience
    """
    # Validate source type
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_type '{source_type}'. Must be one of: {', '.join(sorted(ALLOWED_SOURCE_TYPES))}",
        )

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

    # Normalise optional author
    clean_author = author.strip() or None

    # Create DB record  (filename stores the R2 object key)
    doc = Document(
        filename=r2_key,
        original_filename=file.filename,
        category=category,
        description=description or None,
        status="pending",
        file_size_bytes=file_size,
        source_type=source_type,
        author=clean_author,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    logger.info(
        f"Document uploaded: {file.filename} → R2 key={r2_key}, id={doc.id}, "
        f"source_type={source_type}, author={clean_author}, queued for indexing"
    )

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
                    source_type=source_type,
                    author=clean_author,
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
    _: None = Depends(verify_admin_cookie),
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
    _: None = Depends(verify_admin_cookie),
):
    """Delete a document from pgvector, BM25, R2 storage, and DB."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await delete_document(document_id, db)


@router.patch("/documents/{document_id}", response_model=DocumentOut)
@limiter.limit("20/minute")
async def update_doc(
    request: Request,
    document_id: int,
    body: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_cookie),
):
    """
    Update a document's source classification (and optionally category/author).

    When source_type changes:
    - All document_chunks are updated to reflect the new source_type/author.
    - The response cache is flushed immediately.
    - The KB version is bumped.
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Determine effective values (keep existing if not provided in patch)
    new_source_type = body.source_type if body.source_type is not None else doc.source_type
    new_author = body.author if body.author is not None else doc.author
    new_category = body.category if body.category is not None else None  # None = unchanged

    await update_document_source(
        document_id=document_id,
        source_type=new_source_type,
        author=new_author,
        category=new_category,
        db=db,
    )

    # Re-fetch updated doc to return
    await db.refresh(doc)
    return doc


@router.post("/reindex", response_model=ReindexResponse)
@limiter.limit("3/minute")    # STRICTEST: triggers full BM25 rebuild — very expensive
async def reindex_all(
    request: Request,          # required by slowapi for IP extraction
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_cookie),
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
    _: None = Depends(verify_admin_cookie),
):
    """Get details for a single document."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/cache/flush", status_code=200)
@limiter.limit("5/minute")    # nuclear option — strict cap
async def flush_cache(
    request: Request,          # required by slowapi for IP extraction
    _: None = Depends(verify_admin_cookie),
):
    """
    Flush all cached RAG responses from Upstash Redis.

    Use this as an emergency override when you need to force all users to
    receive fresh answers immediately (e.g., after a critical document update
    that must propagate before the 24-hour TTL expires).

    The KB version counter is NOT reset, so the regular version-based
    invalidation continues to work correctly after the flush.

    Returns the number of cache entries deleted.
    """
    deleted = await run_in_threadpool(flush_response_cache)
    if deleted == -1:
        raise HTTPException(
            status_code=503,
            detail="Cache flush failed — Redis unavailable. Check UPSTASH_REDIS_URL.",
        )
    logger.info(f"Admin cache flush: {deleted} entries deleted")
    return {"deleted_keys": deleted, "message": f"Flushed {deleted} cached response(s)."}
