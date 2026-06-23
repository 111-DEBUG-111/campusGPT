"""
BGE Reranker — Singleton wrapper.

Uses BAAI/bge-reranker-base (~400MB) by default.
Override via RERANKER_MODEL env var.
"""
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_reranker: "Reranker | None" = None


class Reranker:
    """
    Cross-encoder reranker using BGE Reranker.
    Scores (query, passage) pairs for fine-grained relevance.
    """

    def __init__(self):
        from FlagEmbedding import FlagReranker
        logger.info(f"Loading reranker: {settings.reranker_model}")
        self.model = FlagReranker(settings.reranker_model, use_fp16=True)
        logger.info("Reranker loaded ✓")

    def rerank(self, query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
        """
        Rerank chunks by cross-encoder score.

        Args:
            query: User query string
            chunks: List of chunk dicts (must have "text" key)
            top_k: How many top chunks to return

        Returns:
            Top-k chunks sorted by reranker score, with "rerank_score" added.
        """
        if not chunks:
            return []

        pairs = [[query, c["text"]] for c in chunks]
        scores = self.model.compute_score(pairs, normalize=True)

        # Attach scores and sort
        for chunk, score in zip(chunks, scores):
            chunk["rerank_score"] = float(score)

        ranked = sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)
        return ranked[:top_k]


def get_reranker() -> Reranker:
    """Return the singleton Reranker."""
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker
