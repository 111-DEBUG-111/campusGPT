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
        """Create collection if it doesn't already exist."""
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

    # ─── Upsert ───────────────────────────────────────────────────────────────

    def upsert_chunks(self, chunks: list[dict]) -> int:
        """
        Upsert document chunks into Qdrant.

        Each chunk dict must have:
            text, embedding, document_id, filename, category,
            page_number (optional), chunk_index
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
