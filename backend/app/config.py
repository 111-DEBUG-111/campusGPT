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

    # ─── pgvector ─────────────────────────────────────────────────────────────
    # Hardcoded to 1024 for BAAI/bge-m3.  If you switch embedding models,
    # the document_chunks.embedding column must be dropped and recreated.
    vector_dimension: int = 1024

    # ─── BM25 ─────────────────────────────────────────────────────────────────
    bm25_top_k: int = 20
    vector_top_k: int = 20

    # ─── Database (Neon PostgreSQL) ───────────────────────────────────────────
    # Format: postgresql+asyncpg://user:password@host/dbname?ssl=require
    database_url: str

    # ─── S3-Compatible Object Storage (Supabase Storage) ──────────────────────
    # Supabase: Dashboard → Storage → S3 Connection → copy credentials
    # Endpoint: https://<project-ref>.supabase.co/storage/v1/s3
    storage_endpoint_url: str
    storage_access_key_id: str
    storage_secret_access_key: str
    storage_bucket_name: str = "campusgpt-uploads"
    # Optional: public CDN base URL if the bucket has public access enabled
    storage_public_url: str | None = None

    # ─── Upload ───────────────────────────────────────────────────────────────
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

    # ─── Response Cache (Upstash Redis) ───────────────────────────────────────
    # Set CACHE_ENABLED=false to disable caching entirely (e.g. during testing).
    cache_enabled: bool = True
    # Upstash REST credentials — obtain from console.upstash.com
    upstash_redis_url: str | None = None
    upstash_redis_token: str | None = None
    # Time-to-live for cached RAG responses.  Default: 24 hours.
    # KB version bumps render old entries unreachable before TTL expiry,
    # so TTL is just the final safety net for orphaned entries.
    cache_ttl_seconds: int = 86400  # 24 hours


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — safe to import anywhere."""
    return Settings()
