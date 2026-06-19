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
    # bge-m3: 1024-dim, up to 8192 tokens — production quality
    # bge-small-en-v1.5: 384-dim, 512 tokens — low-memory fallback (~120MB)
    embedding_model: str = "BAAI/bge-m3"

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

    # ─── Chunking ─────────────────────────────────────────────────────────────
    # Tune these together based on your embedding model:
    #   bge-m3  (8192 token ctx)  → chunk_size=800, chunk_min_tokens=80
    #   bge-small (512 token ctx) → chunk_size=400, chunk_min_tokens=40
    chunk_size: int = 800          # target tokens per semantic chunk
    chunk_overlap: int = 0         # legacy — semantic chunker uses sentence overlap instead
    chunk_min_tokens: int = 80     # minimum tokens; smaller chunks discarded as noise

    # ─── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_per_minute: int = 20

    # ─── RAG ──────────────────────────────────────────────────────────────────
    max_context_chunks: int = 5
    max_query_rewrites: int = 3


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — safe to import anywhere."""
    return Settings()
