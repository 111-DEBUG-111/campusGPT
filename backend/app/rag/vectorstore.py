"""
Qdrant Vector Store Wrapper for CampusGPT.

Uses Qdrant Cloud Free tier — fully persistent, no ephemeral disk issues.
"""
import logging
import uuid
from typing import Optional
from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny,
    SearchRequest, ScoredPoint,
    PayloadSchemaType,
)
from app.config import get_settings
from app.rag.embedder import get_embedder

logger = logging.getLogger(__name__)
settings = get_settings()

_qdrant_client: "QdrantVectorStore | None" = None


class QdrantVectorStore:
    """
    Async-compatible wrapper around Qdrant.
    We use the sync client because FlagEmbedding is synchronous —
    all heavy ops run in thread pool via FastAPI's run_in_threadpool.
    """

    def __init__(self):
        logger.info(f"Connecting to Qdrant at {settings.qdrant_url}")
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=30,
        )
        self.collection = settings.qdrant_collection
        self._ensure_collection()
        logger.info("Qdrant connected ✓")

    def _ensure_collection(self):
        """Create collection if it doesn't already exist, then ensure payload indexes."""
        embedder = get_embedder()
        existing = [c.name for c in self.client.get_collections().collections]

        if self.collection not in existing:
            logger.info(f"Creating Qdrant collection '{self.collection}' dim={embedder.dimension}")
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=embedder.dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Collection created ✓")

        # Ensure payload indexes.
        # All calls are idempotent — safe on every startup regardless of
        # whether the collection is new or pre-existing.
        _indexes = [
            ("document_id", PayloadSchemaType.INTEGER),
            ("section_title", PayloadSchemaType.KEYWORD),
            ("chunk_type", PayloadSchemaType.KEYWORD),
        ]
        for field_name, schema in _indexes:
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field_name,
                field_schema=schema,
            )
        logger.info("Payload indexes ensured ✓ (document_id, section_title, chunk_type)")

    # ─── Upsert ───────────────────────────────────────────────────────────────

    def upsert_chunks(self, chunks: list[dict]) -> int:
        """
        Upsert document chunks into Qdrant.

        Required keys per chunk: text, embedding, document_id, filename,
        category, chunk_index.
        Optional keys (new semantic fields): page_number, section_title,
        section_path, chunk_type, heading_level.
        Missing optional keys default to None / "text" gracefully.
        """
        if not chunks:
            return 0

        points = []
        for chunk in chunks:
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=chunk["embedding"],
                    payload={
                        "text": chunk["text"],
                        "document_id": chunk["document_id"],
                        "filename": chunk["filename"],
                        "category": chunk["category"],
                        "page_number": chunk.get("page_number"),
                        "chunk_index": chunk["chunk_index"],
                        # ── Semantic metadata (new) ──────────────────────────
                        "section_title": chunk.get("section_title"),
                        "section_path": chunk.get("section_path"),
                        "chunk_type": chunk.get("chunk_type", "text"),
                        "heading_level": chunk.get("heading_level"),
                    },
                )
            )

        self.client.upsert(collection_name=self.collection, points=points)
        logger.info(f"Upserted {len(points)} chunks into Qdrant")
        return len(points)

    # ─── Search ───────────────────────────────────────────────────────────────

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 20,
        filter_category: Optional[str] = None,
    ) -> list[dict]:
        """
        Vector similarity search.
        Returns list of dicts with text, score, and metadata.
        """
        query_filter = None
        if filter_category:
            query_filter = Filter(
                must=[FieldCondition(
                    key="category",
                    match=MatchValue(value=filter_category)
                )]
            )

        response = self.client.query_points(
            collection_name=self.collection,
            query=query_embedding,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        results = response.points

        return [
            {
                "id": str(r.id),
                "text": r.payload["text"],
                "score": r.score,
                "document_id": r.payload["document_id"],
                "filename": r.payload["filename"],
                "category": r.payload["category"],
                "page_number": r.payload.get("page_number"),
                "chunk_index": r.payload.get("chunk_index", 0),
                # Semantic metadata — None for legacy chunks without these fields
                "section_title": r.payload.get("section_title"),
                "section_path": r.payload.get("section_path"),
                "chunk_type": r.payload.get("chunk_type", "text"),
                "heading_level": r.payload.get("heading_level"),
            }
            for r in results
        ]

    # ─── Delete ───────────────────────────────────────────────────────────────

    def delete_by_document_id(self, document_id: int) -> int:
        """Delete all chunks belonging to a document."""
        result = self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id)
                )]
            ),
        )
        logger.info(f"Deleted chunks for document_id={document_id}")
        return 0  # Qdrant doesn't return count for filter deletes

    # ─── Fetch all chunks (for BM25 rebuild) ─────────────────────────────────

    def fetch_all_chunks(self, limit: int = 100_000) -> list[dict]:
        """Scroll through all stored chunks for BM25 index rebuild."""
        records, _ = self.client.scroll(
            collection_name=self.collection,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {
                "id": str(r.id),
                "text": r.payload["text"],
                "document_id": r.payload["document_id"],
                "filename": r.payload["filename"],
                "category": r.payload["category"],
                "page_number": r.payload.get("page_number"),
                "chunk_index": r.payload.get("chunk_index", 0),
                # Semantic metadata — None for legacy chunks
                "section_title": r.payload.get("section_title"),
                "section_path": r.payload.get("section_path"),
                "chunk_type": r.payload.get("chunk_type", "text"),
                "heading_level": r.payload.get("heading_level"),
            }
            for r in records
        ]

    def get_collection_info(self) -> dict:
        info = self.client.get_collection(self.collection)
        return {
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
        }


def get_vectorstore() -> QdrantVectorStore:
    """Return the singleton vector store."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantVectorStore()
    return _qdrant_client
