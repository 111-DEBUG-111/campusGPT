"""
Hosted Gemini Embedding Model — Singleton wrapper.
Uses the hosted Google Gemini Embedding API (gemini-embedding-001 by default).
Memory usage: ~0MB local RAM.
"""
import logging
import time
from typing import Optional
from google import genai
from google.genai import types
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_embedder: "Embedder | None" = None


class Embedder:
    """
    Wraps the Google GenAI SDK to generate text embeddings.
    Uses the hosted model gemini-embedding-001 by default, configured to output 768 dimensions.
    """

    def __init__(self):
        logger.info(f"Initializing Gemini Embedding Client (model={settings.embedding_model})")
        self.client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=3)
            )
        )
        logger.info("✓ Gemini Embedding Client initialized")

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        if not text.strip():
            return [0.0] * self.dimension

        start = time.time()
        response = self.client.models.embed_content(
            model=settings.embedding_model,
            contents=text,
            config=types.EmbedContentConfig(
                outputDimensionality=self.dimension
            )
        )
        latency_ms = (time.time() - start) * 1000

        logger.info(f"Query embedding generated: {len(text)} chars in {latency_ms:.1f}ms")
        if not response.embeddings or len(response.embeddings) == 0:
            raise ValueError("Gemini API returned an empty embedding response.")
        
        return response.embeddings[0].values

    def embed_documents(
        self, 
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[float]]:
        """
        Embed a batch of document chunks.
        
        Args:
            texts: List of document chunks to embed
            batch_size: Override default batch size (default: 100)
        
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        batch_size = batch_size or 100
        num_docs = len(texts)
        start_time = time.time()

        embeddings: list[list[float]] = []

        logger.info(f"Embedding {num_docs} chunks in batches of {batch_size} via Gemini...")

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = self.client.models.embed_content(
                model=settings.embedding_model,
                contents=batch,
                config=types.EmbedContentConfig(
                    outputDimensionality=self.dimension
                )
            )
            if not response.embeddings:
                raise ValueError("Gemini API returned an empty embedding response.")
            for emb in response.embeddings:
                embeddings.append(emb.values)

        elapsed_time = time.time() - start_time
        throughput = num_docs / elapsed_time if elapsed_time > 0 else 0
        
        logger.info(f"📊 Embedding batch completed: {num_docs} docs in {elapsed_time:.1f}s ({throughput:.1f} docs/sec)")
        
        return embeddings

    @property
    def dimension(self) -> int:
        """Return embedding dimension configured in settings (default: 768)."""
        return settings.vector_dimension


def get_embedder() -> "Embedder":
    """Return the singleton Embedder, creating it on first call."""
    global _embedder
    if _embedder is None:
        logger.info("Creating new Embedder instance (Gemini API)")
        _embedder = Embedder()
    return _embedder
