"""
pgvector Vector Store for CampusGPT.

Replaces the Qdrant Cloud backend with pgvector running inside the existing
Neon PostgreSQL instance via asyncpg (already installed).

Architecture notes:
  - Uses asyncpg directly with asyncio.run() — this is safe because the
    vectorstore is always called from a thread pool (run_in_threadpool),
    never from the main async event loop.
  - Cosine similarity via pgvector's <=> operator (cosine *distance*).
    score returned = 1 - distance, so 1.0 = identical, 0.0 = orthogonal.
  - INSERT … ON CONFLICT (id) DO UPDATE makes upserts idempotent.
  - No pgvector Python package required — asyncpg handles the vector
    literal strings natively as plain text parameters.
  - Embedding dimension: hardcoded 1024 for BAAI/bge-m3.
"""
import asyncio
import logging
import uuid
from typing import Optional

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_pgvector_store: "PgVectorStore | None" = None


def _build_asyncpg_dsn() -> str:
    """
    Convert the SQLAlchemy DATABASE_URL to an asyncpg-native DSN.

    SQLAlchemy prefix:  postgresql+asyncpg://user:pass@host/db
    asyncpg native:     postgresql://user:pass@host/db
    """
    url = settings.database_url
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _vec_str(v: list[float]) -> str:
    """Format a float list as a pgvector literal: '[0.1,0.2,…]'"""
    return "[" + ",".join(str(x) for x in v) + "]"


class PgVectorStore:
    """
    Sync-compatible vector store backed by pgvector on Neon PostgreSQL.

    Public interface is identical to the old QdrantVectorStore:
      upsert_chunks(chunks)           → int
      search(query_embedding, ...)    → list[dict]
      delete_by_document_id(doc_id)  → int
      fetch_all_chunks(limit)         → list[dict]
      get_collection_info()           → dict
    """

    def __init__(self):
        self._dsn = _build_asyncpg_dsn()
        logger.info("PgVectorStore initialised (asyncpg → Neon PostgreSQL) ✓")

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _get_conn(self) -> asyncpg.Connection:
        """Open a single asyncpg connection with SSL required for Neon."""
        return await asyncpg.connect(self._dsn, ssl="require")

    def _run(self, coro):
        """Run a coroutine synchronously (safe inside a threadpool thread)."""
        return asyncio.run(coro)

    # ── Upsert ────────────────────────────────────────────────────────────────

    async def _upsert_chunks_async(self, chunks: list[dict]) -> int:
        conn = await self._get_conn()
        try:
            sql = """
                INSERT INTO document_chunks
                    (id, document_id, filename, category, text, embedding,
                     page_number, chunk_index,
                     section_title, section_path, chunk_type, heading_level)
                VALUES
                    ($1, $2, $3, $4, $5, $6::vector,
                     $7, $8, $9, $10, $11, $12)
                ON CONFLICT (id) DO UPDATE SET
                    text          = EXCLUDED.text,
                    embedding     = EXCLUDED.embedding,
                    filename      = EXCLUDED.filename,
                    category      = EXCLUDED.category,
                    page_number   = EXCLUDED.page_number,
                    chunk_index   = EXCLUDED.chunk_index,
                    section_title = EXCLUDED.section_title,
                    section_path  = EXCLUDED.section_path,
                    chunk_type    = EXCLUDED.chunk_type,
                    heading_level = EXCLUDED.heading_level
            """
            rows = [
                (
                    str(uuid.uuid4()),
                    c["document_id"],
                    c["filename"],
                    c["category"],
                    c["text"],
                    _vec_str(c["embedding"]),
                    c.get("page_number"),
                    c["chunk_index"],
                    c.get("section_title"),
                    c.get("section_path"),
                    c.get("chunk_type", "text"),
                    c.get("heading_level"),
                )
                for c in chunks
            ]
            await conn.executemany(sql, rows)
        finally:
            await conn.close()
        logger.info(f"Upserted {len(chunks)} chunks into pgvector")
        return len(chunks)

    def upsert_chunks(self, chunks: list[dict]) -> int:
        if not chunks:
            return 0
        return self._run(self._upsert_chunks_async(chunks))

    # ── Search ────────────────────────────────────────────────────────────────

    async def _search_async(
        self,
        query_embedding: list[float],
        top_k: int,
        filter_category: Optional[str],
    ) -> list[dict]:
        conn = await self._get_conn()
        try:
            vec = _vec_str(query_embedding)
            if filter_category:
                rows = await conn.fetch(
                    """
                    SELECT id, text, document_id, filename, category,
                           page_number, chunk_index,
                           section_title, section_path, chunk_type, heading_level,
                           1 - (embedding <=> $1::vector) AS score
                    FROM document_chunks
                    WHERE category = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    vec, filter_category, top_k,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, text, document_id, filename, category,
                           page_number, chunk_index,
                           section_title, section_path, chunk_type, heading_level,
                           1 - (embedding <=> $1::vector) AS score
                    FROM document_chunks
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                    """,
                    vec, top_k,
                )
        finally:
            await conn.close()

        return [
            {
                "id": str(r["id"]),
                "text": r["text"],
                "score": float(r["score"]),
                "document_id": r["document_id"],
                "filename": r["filename"],
                "category": r["category"],
                "page_number": r["page_number"],
                "chunk_index": r["chunk_index"] or 0,
                "section_title": r["section_title"],
                "section_path": r["section_path"],
                "chunk_type": r["chunk_type"] or "text",
                "heading_level": r["heading_level"],
            }
            for r in rows
        ]

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 20,
        filter_category: Optional[str] = None,
    ) -> list[dict]:
        return self._run(self._search_async(query_embedding, top_k, filter_category))

    # ── Delete ────────────────────────────────────────────────────────────────

    async def _delete_async(self, document_id: int) -> None:
        conn = await self._get_conn()
        try:
            await conn.execute(
                "DELETE FROM document_chunks WHERE document_id = $1", document_id
            )
        finally:
            await conn.close()

    def delete_by_document_id(self, document_id: int) -> int:
        self._run(self._delete_async(document_id))
        logger.info(f"Deleted chunks for document_id={document_id}")
        return 0

    # ── Fetch all (for BM25 rebuild) ──────────────────────────────────────────

    async def _fetch_all_async(self, limit: int) -> list[dict]:
        conn = await self._get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, text, document_id, filename, category,
                       page_number, chunk_index,
                       section_title, section_path, chunk_type, heading_level
                FROM document_chunks
                LIMIT $1
                """,
                limit,
            )
        finally:
            await conn.close()

        return [
            {
                "id": str(r["id"]),
                "text": r["text"],
                "document_id": r["document_id"],
                "filename": r["filename"],
                "category": r["category"],
                "page_number": r["page_number"],
                "chunk_index": r["chunk_index"] or 0,
                "section_title": r["section_title"],
                "section_path": r["section_path"],
                "chunk_type": r["chunk_type"] or "text",
                "heading_level": r["heading_level"],
            }
            for r in rows
        ]

    def fetch_all_chunks(self, limit: int = 100_000) -> list[dict]:
        return self._run(self._fetch_all_async(limit))

    # ── Info ──────────────────────────────────────────────────────────────────

    async def _info_async(self) -> dict:
        conn = await self._get_conn()
        try:
            row = await conn.fetchrow("SELECT COUNT(*) AS total FROM document_chunks")
        finally:
            await conn.close()
        total = row["total"] if row else 0
        return {"vectors_count": total, "points_count": total}

    def get_collection_info(self) -> dict:
        return self._run(self._info_async())


def get_vectorstore() -> PgVectorStore:
    """Return the singleton pgvector store."""
    global _pgvector_store
    if _pgvector_store is None:
        _pgvector_store = PgVectorStore()
    return _pgvector_store
