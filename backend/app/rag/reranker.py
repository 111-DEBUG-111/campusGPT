"""
BGE Reranker — Singleton wrapper with free-tier bypass.
Uses BAAI/bge-reranker-base (~400MB) when enabled.
Reranker can be fully disabled in config to save server memory (OOM prevention).
"""
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_reranker: "Reranker | None" = None


class Reranker:
    """
    Cross-encoder reranker using BGE Reranker.
    Bypasses and does a direct pass-through of RRF-sorted chunks if disabled by config.
    """

    def __init__(self):
        if settings.disable_reranker:
            logger.info("Reranker is disabled by configuration settings (OOM memory bypass active)")
            self.model = None
            return

        try:
            from FlagEmbedding import FlagReranker
            logger.info(f"Loading reranker: {settings.reranker_model}")
            self.model = FlagReranker(settings.reranker_model, use_fp16=True)
            logger.info("Reranker loaded ✓")
        except ImportError as e:
            logger.warning(
                f"FlagEmbedding is not installed, but disable_reranker is False. "
                f"Falling back to bypassing reranking. Error: {e}"
            )
            settings.disable_reranker = True
            self.model = None

    def rerank(self, query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
        """
        Rerank chunks by cross-encoder score. If disabled, returns top-k chunks directly.

        Args:
            query: User query string
            chunks: List of chunk dicts (must have "text" key)
            top_k: How many top chunks to return

        Returns:
            Top-k chunks sorted by relevance, with "rerank_score" added.
        """
        if not chunks:
            return []

        if settings.disable_reranker or self.model is None:
            # Reranker is disabled: return top_k candidates directly based on RRF scores.
            # RRF-fused chunks are already sorted by relevance (RRF score descending).
            logger.debug(f"Reranker disabled: returning top {top_k} chunks directly from RRF input.")
            for c in chunks:
                # Add rerank_score mapping for API schema consistency
                c["rerank_score"] = float(c.get("rrf_score", 0.0))
            return chunks[:top_k]

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
