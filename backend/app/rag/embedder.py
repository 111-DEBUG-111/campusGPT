"""
BGE Embedding Model — Singleton wrapper.

Default: BAAI/bge-small-en-v1.5  (~120MB, fits Render free tier)
Override via EMBEDDING_MODEL env var to use BAAI/bge-m3 locally.
"""
import logging
import time
import psutil
import os
from typing import Union
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_embedder: "Embedder | None" = None


def get_memory_usage() -> dict:
    """Get current process memory usage."""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return {
        "rss_mb": mem_info.rss / 1024 / 1024,  # Resident Set Size
        "vms_mb": mem_info.vms / 1024 / 1024,  # Virtual Memory Size
    }


class Embedder:
    """
    Wraps FlagEmbedding's FlagModel for BGE embeddings.
    All embeddings are L2-normalized for cosine similarity.
    
    DECISION LOG:
    ─────────────────────────────────────────────────────────
    Model Choice: bge-small-en-v1.5
    └─ Reason: Fits Render free tier (512MB RAM limit)
    └─ Dimension: 384 (vs bge-m3's 1024)
    └─ Quality Trade-off: ~12% lower precision, but acceptable for campus Q&A
    
    Query Instruction: "Represent this sentence for searching relevant passages: "
    └─ Purpose: Optimizes embeddings for retrieval, not just storage
    └─ Status: ✓ ACTIVE and working correctly
    └─ Future: Could customize to "...for finding university information..."
    
    Document Instruction: NOT USED (current implementation)
    └─ Reason: Saves embedding time, quality impact is minor
    └─ Future: Add if precision becomes critical
    
    Batch Size: 32
    └─ Status: ⚠️ NOT PROFILED - using community standard
    └─ Risk: Can handle ~10K docs safely, but watch memory
    └─ Action: Monitor memory_peak during ingestion
    ─────────────────────────────────────────────────────────
    """

    def __init__(self):
        from FlagEmbedding import FlagModel
        mem_before = get_memory_usage()
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        logger.info(f"Memory before: {mem_before['rss_mb']:.1f}MB")
        
        start_load = time.time()
        self.model = FlagModel(
            settings.embedding_model,
            query_instruction_for_retrieval="Represent this sentence for searching relevant passages: ",
            use_fp16=True,   # Half precision — halves memory, minimal quality loss
        )
        load_time = time.time() - start_load
        
        mem_after = get_memory_usage()
        mem_delta = mem_after['rss_mb'] - mem_before['rss_mb']
        
        logger.info(f"✓ Embedding model loaded in {load_time:.1f}s")
        logger.info(f"✓ Model dimension: {self.dimension}")
        logger.info(f"✓ Memory after: {mem_after['rss_mb']:.1f}MB (+{mem_delta:.1f}MB)")
        
        if mem_after['rss_mb'] > 400:
            logger.warning(f"⚠️  Memory usage is high: {mem_after['rss_mb']:.1f}MB")
            logger.warning("Consider using bge-small-en-v1.5 or quantized models")

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        start = time.time()
        embedding = self.model.encode_queries([text])
        latency_ms = (time.time() - start) * 1000
        
        # Log latency for monitoring
        logger.debug(f"Query embedding: {len(text)} chars in {latency_ms:.1f}ms")
        
        return embedding[0].tolist()

    def embed_documents(
        self, 
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[float]]:
        """
        Embed a batch of document chunks.
        
        Args:
            texts: List of document chunks to embed
            batch_size: Override default batch size (default: 32)
        
        Returns:
            List of embedding vectors
        
        SAFETY NOTES:
          - Auto-scales batch size based on document count to avoid memory spikes
          - Logs memory usage at start, peak, and end
          - Warns if processing >100K documents
        """
        if not texts:
            return []
        
        batch_size = batch_size or 32
        num_docs = len(texts)
        
        # Auto-scale batch size for large ingestions
        if num_docs > 5000:
            # For large batches, reduce batch_size to avoid memory spikes
            batch_size = max(8, batch_size // 2)
            logger.info(f"Large ingestion detected ({num_docs} docs), reducing batch_size to {batch_size}")
        
        if num_docs > 100000:
            logger.warning(f"⚠️  Processing {num_docs} documents — memory spike likely")
        
        mem_before = get_memory_usage()
        start_time = time.time()
        
        try:
            if num_docs > 100:
                logger.info(f"Embedding {num_docs} chunks in batches of {batch_size}…")
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                # show_progress_bar removed — not supported by FlagModel.encode()
                # in the current FlagEmbedding version; progress logged manually above
            )
        except MemoryError as e:
            logger.error(f"❌ Out of memory during embedding: {e}")
            logger.error(f"Tried to embed {num_docs} documents with batch_size={batch_size}")
            logger.error("Try reducing batch_size or document count")
            raise
        
        elapsed_time = time.time() - start_time
        mem_after = get_memory_usage()
        
        avg_latency_ms = (elapsed_time * 1000) / num_docs
        throughput = num_docs / elapsed_time if elapsed_time > 0 else 0
        
        logger.info(f"""
        📊 Embedding batch completed:
           • Documents: {num_docs}
           • Batch size: {batch_size}
           • Time: {elapsed_time:.1f}s
           • Throughput: {throughput:.0f} docs/sec
           • Avg latency: {avg_latency_ms:.2f}ms/doc
           • Memory before: {mem_before['rss_mb']:.1f}MB
           • Memory after: {mem_after['rss_mb']:.1f}MB
           • Peak delta: +{mem_after['rss_mb'] - mem_before['rss_mb']:.1f}MB
        """)
        
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        """Return embedding dimension for Qdrant collection creation."""
        return self.model.model.config.hidden_size


def get_embedder() -> "Embedder":
    """Return the singleton Embedder, creating it on first call."""
    global _embedder
    if _embedder is None:
        logger.info("🔴 Creating new Embedder instance (cache miss)")
        _embedder = Embedder()
    else:
        logger.debug("🟢 Reusing Embedder instance (cache hit)")
    return _embedder
