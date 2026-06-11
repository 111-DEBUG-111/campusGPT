"""
Document Service — Orchestrates upload → parse → embed → index → store.
"""
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.models import Document
from app.rag.ingestion import ingest_pdf, ingest_text_file
from app.rag.embedder import get_embedder
from app.rag.vectorstore import get_vectorstore
from app.rag.bm25_index import get_bm25_index

logger = logging.getLogger(__name__)
settings = get_settings()


def _safe_filename(original: str) -> str:
    """
    Return a safe, UUID-prefixed filename for storage.

    Security measures applied:
      1. Strip all directory components (prevents path traversal like ../../etc/passwd).
      2. Remove any character that isn't alphanumeric, a dot, hyphen, or underscore.
      3. Prepend a UUID4 so the stored path is unguessable and collision-free.
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
    # 5. Prepend UUID — stored filename is never just the user's string
    return f"{uuid.uuid4().hex}_{name}"


async def save_upload(file: UploadFile, upload_dir: Path) -> tuple[Path, int]:
    """Save an uploaded file to disk with a sanitised UUID-based name.

    Returns (stored_path, size_bytes).  The caller must persist
    ``file.filename`` (the *original* name) separately for display purposes.
    """
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(file.filename or "upload")
    dest = upload_dir / safe_name
    # UUID prefix makes collisions astronomically unlikely, but guard anyway
    while dest.exists():
        safe_name = _safe_filename(file.filename or "upload")
        dest = upload_dir / safe_name

    content = await file.read()
    dest.write_bytes(content)
    logger.info(
        f"Saved upload '{file.filename}' → '{dest.name}' ({len(content)} bytes)"
    )
    return dest, len(content)


async def process_document(
    document_id: int,
    file_path: Path,
    filename: str,
    category: str,
    db: AsyncSession,
) -> int:
    """
    Background processing: ingest → embed → upsert into Qdrant → update BM25.
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
        # ── Ingest ──────────────────────────────────────────────────────────────
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            chunks = await run_in_threadpool(
                ingest_pdf, file_path, document_id, filename, category
            )
        elif suffix in (".txt", ".md"):
            chunks = await run_in_threadpool(
                ingest_text_file, file_path, document_id, filename, category
            )
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        if not chunks:
            raise ValueError("No content extracted from document")

        # ── Embed ──────────────────────────────────────────────────────────────
        embedder = get_embedder()
        texts = [c["text"] for c in chunks]
        embeddings = await run_in_threadpool(embedder.embed_documents, texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding

        # ── Upsert into Qdrant ────────────────────────────────────────────────
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

        logger.info(f"Document {document_id} indexed: {len(chunks)} chunks")
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
    """Remove document from DB, Qdrant, and BM25 index."""
    # Get document info
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        return

    # Delete from Qdrant
    vectorstore = get_vectorstore()
    await run_in_threadpool(vectorstore.delete_by_document_id, document_id)

    # Update BM25
    bm25 = get_bm25_index()
    bm25.remove_by_document_id(document_id)

    # Delete file from disk
    upload_dir = Path(settings.upload_dir)
    file_path = upload_dir / doc.filename
    if file_path.exists():
        file_path.unlink()

    # Delete from DB
    await db.delete(doc)
    await db.commit()
    logger.info(f"Document {document_id} ({doc.filename}) deleted")


async def rebuild_bm25_from_qdrant() -> int:
    """Rebuild BM25 in-memory index from all Qdrant chunks (used on startup)."""
    vectorstore = get_vectorstore()
    bm25 = get_bm25_index()

    chunks = await run_in_threadpool(vectorstore.fetch_all_chunks)
    bm25.build_from_chunks(chunks)
    logger.info(f"BM25 rebuilt from Qdrant: {len(chunks)} chunks")
    return len(chunks)
