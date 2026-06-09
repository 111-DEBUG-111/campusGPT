"""
CampusGPT Backend Configuration
All settings are loaded from environment variables with sensible defaults.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ──────────────────────────────────────────────────────────────────
    app_name: str = "CampusGPT"
    app_version: str = "1.0.0"
    debug: bool = False

    # ─── Security ─────────────────────────────────────────────────────────────
    admin_api_key: str = "change-me-in-production"
    frontend_url: str = "http://localhost:5173"

    # ─── Google Gemini ────────────────────────────────────────────────────────
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash"

    # ─── Embeddings ───────────────────────────────────────────────────────────
    # Default: bge-small-en-v1.5 (~120MB, fits Render free 512MB)
    # Override to "BAAI/bge-m3" when self-hosting with more RAM
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # ─── Reranker ─────────────────────────────────────────────────────────────
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_top_k: int = 5

    # ─── Qdrant ───────────────────────────────────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "campusgpt_docs"

    # ─── BM25 ─────────────────────────────────────────────────────────────────
    bm25_top_k: int = 20
    vector_top_k: int = 20

    # ─── Database ─────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/campusgpt.db"

    # ─── Upload ───────────────────────────────────────────────────────────────
    upload_dir: str = "./data/uploads"
    max_upload_size_mb: int = 50
    chunk_size: int = 512          # tokens per chunk
    chunk_overlap: int = 64        # token overlap between chunks

    # ─── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_per_minute: int = 20

    # ─── RAG ──────────────────────────────────────────────────────────────────
    max_context_chunks: int = 5
    max_query_rewrites: int = 3

    # ─── Conversation History (Feature #1) ───────────────────────────────────
    # Number of most-recent messages sent to the LLM as conversation context.
    history_window: int = 10

    # ─── Conversation Summarization (Feature #2) ──────────────────────────────
    # Total message count that triggers background summarization.
    summarize_threshold: int = 50

    # ─── Response Cache (Feature #4) ──────────────────────────────────────────
    # How long a cached response is valid (seconds). Default: 24 hours.
    cache_ttl_seconds: int = 86400
    # Minimum cosine similarity to consider a query a cache hit.
    cache_similarity_threshold: float = 0.97
    # Max entries kept in the in-memory LRU cache.
    cache_max_memory_entries: int = 500

    # ─── Memory Retrieval (Feature #7) ────────────────────────────────────────
    # Number of long-term memory entries retrieved per query.
    memory_retrieval_top_k: int = 3


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — safe to import anywhere."""
    return Settings()
