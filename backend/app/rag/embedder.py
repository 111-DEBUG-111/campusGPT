"""
BGE Embedding Model — Singleton wrapper.

Default: BAAI/bge-small-en-v1.5  (~120MB, fits Render free tier)
Override via EMBEDDING_MODEL env var to use BAAI/bge-m3 locally.
"""
import logging
from typing import Union
from FlagEmbedding import FlagModel
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_embedder: "Embedder | None" = None


class Embedder:
    """
    Wraps FlagEmbedding's FlagModel for BGE embeddings.
    All embeddings are L2-normalized for cosine similarity.
    """

    def __init__(self):
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        self.model = FlagModel(
            settings.embedding_model,
            query_instruction_for_retrieval="Represent this sentence for searching relevant passages: ",
            use_fp16=True,   # Half precision — halves memory, minimal quality loss
        )
        logger.info("Embedding model loaded ✓")

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        embedding = self.model.encode_queries([text])
        return embedding[0].tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunks."""
        if not texts:
            return []
        embeddings = self.model.encode(texts, batch_size=32)
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        """Return embedding dimension for Qdrant collection creation."""
        return self.model.model.config.hidden_size


def get_embedder() -> "Embedder":
    """Return the singleton Embedder, creating it on first call."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
