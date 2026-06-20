"""
Document Service — Orchestrates upload → parse → embed → index → store.
Files are persisted in Cloudflare R2 (S3-compatible object storage).
"""
import logging
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.models import Document
from app.r2_storage import upload_file as r2_upload, download_file as r2_download, delete_file as r2_delete
from app.rag.ingestion import ingest_pdf, ingest_text_file
from app.rag.embedder import get_embedder
from app.rag.vectorstore import get_vectorstore
from app.rag.bm25_index import get_bm25_index
from app.cache.kb_version import bump_kb_version

logger = logging.getLogger(__name__)
settings = get_settings()


def _safe_filename(original: str) -> str:
    """
    Return a safe, UUID-prefixed filename for storage.

    Security measures applied:
      1. Strip all directory components (prevents path traversal like ../../etc/passwd).
      2. Remove any character that isn't alphanumeric, a dot, hyphen, or underscore.
      3. Prepend a UUID4 so the stored key is unguessable and collision-free.
    """
    # 1. Strip directory components — only keep the bare filename
    name = Path(original).name
    # 2. Allow only safe characters; replace everything else with underscores
    name = re.sub(r"[^\w.\-]", "_", name)
    # 3. Collapse consecutive underscores for readability
    name = re.sub(r"_+", "_", name).strip("_")
    # 4. Fallback for degenerate inputs
    if not name:
        name = "upload"
    # 5. Prepend UUID — stored key is never just the user's string
    return f"{uuid.uuid4().hex}_{name}"


async def save_upload(file: UploadFile) -> tuple[str, int]:
    """Upload a file to Cloudflare R2.

    Returns (r2_object_key, size_bytes).  The caller must persist
    ``file.filename`` (the *original* name) separately for display purposes.
    The returned key is stored as ``Document.filename`` and used for all
    subsequent R2 operations (download, delete).
    """
    safe_name = _safe_filename(file.filename or "upload")
    r2_key = f"uploads/{safe_name}"

    content = await file.read()
    await r2_upload(content, r2_key)

    logger.info(
        f"R2 upload: '{file.filename}' → key='{r2_key}' ({len(content)} bytes)"
    )
    return r2_key, len(content)


async def process_document(
    document_id: int,
    r2_key: str,
    filename: str,
    category: str,
    db: AsyncSession,
) -> int:
    """
    Background processing: download from R2 → ingest → embed → upsert into pgvector → update BM25.
    Uses a temporary local file for the ingestion step (ingestion libs need a real Path).
    Returns number of chunks indexed.
    """
    # Update status to "indexing"
    await db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(status="indexing")
    )
    await db.commit()

    try:
        # ── Download from R2 ────────────────────────────────────────────────────
        file_bytes = await r2_download(r2_key)

        # ── Write to a temp file (ingestion libs require a Path) ───────────────
        suffix = Path(filename).suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        try:
            # ── Ingest ──────────────────────────────────────────────────────────
            if suffix == ".pdf":
                chunks = await run_in_threadpool(
                    ingest_pdf, tmp_path, document_id, filename, category
                )
            elif suffix in (".txt", ".md"):
                chunks = await run_in_threadpool(
                    ingest_text_file, tmp_path, document_id, filename, category
                )
            else:
                raise ValueError(f"Unsupported file type: {suffix}")
        finally:
            # Always clean up the temp file
            tmp_path.unlink(missing_ok=True)

        if not chunks:
            raise ValueError("No content extracted from document")

        # ── Embed ──────────────────────────────────────────────────────────────
        embedder = get_embedder()
        texts = [c["text"] for c in chunks]
        embeddings = await run_in_threadpool(embedder.embed_documents, texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding

        # ── Upsert into pgvector ─────────────────────────────────────────────────
        vectorstore = get_vectorstore()
        await run_in_threadpool(vectorstore.upsert_chunks, chunks)

        # ── Update BM25 ────────────────────────────────────────────────────────
        bm25 = get_bm25_index()
        bm25.add_chunks([{k: v for k, v in c.items() if k != "embedding"} for c in chunks])

        # ── Update document status ─────────────────────────────────────────────
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                status="indexed",
                chunk_count=len(chunks),
                indexed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        # ── Invalidate response cache ──────────────────────────────────────────
        # Any cached answers may now be stale (new document changes KB content).
        new_version = await run_in_threadpool(bump_kb_version)
        logger.info(f"Document {document_id} indexed: {len(chunks)} chunks (kb_version={new_version})")
        return len(chunks)

    except Exception as e:
        logger.error(f"Document indexing failed for id={document_id}: {e}")
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status="error", error_message=str(e)[:500])
        )
        await db.commit()
        raise


async def delete_document(document_id: int, db: AsyncSession) -> None:
    """Remove document from DB, Qdrant, BM25 index, and Cloudflare R2."""
    # Get document info
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        return

    # Delete from pgvector
    vectorstore = get_vectorstore()
    await run_in_threadpool(vectorstore.delete_by_document_id, document_id)

    # Update BM25
    bm25 = get_bm25_index()
    bm25.remove_by_document_id(document_id)

    # Delete file from R2 (doc.filename stores the R2 object key)
    await r2_delete(doc.filename)

    # Delete from DB
    await db.delete(doc)
    await db.commit()

    # Invalidate response cache — deleted document may be cited in cached answers.
    new_version = await run_in_threadpool(bump_kb_version)
    logger.info(f"Document {document_id} (key={doc.filename}) deleted (kb_version={new_version})")


async def rebuild_bm25_from_vectorstore() -> int:
    """Rebuild BM25 in-memory index from all pgvector chunks (used on startup)."""
    vectorstore = get_vectorstore()
    bm25 = get_bm25_index()

    chunks = await run_in_threadpool(vectorstore.fetch_all_chunks)
    bm25.build_from_chunks(chunks)

    # Invalidate cache — reindexing may have changed KB content.
    new_version = await run_in_threadpool(bump_kb_version)
    logger.info(f"BM25 rebuilt from pgvector: {len(chunks)} chunks (kb_version={new_version})")
    return len(chunks)
