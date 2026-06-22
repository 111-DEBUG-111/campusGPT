"""
CampusGPT FastAPI Application

Startup sequence:
  1. Init Neon PostgreSQL DB (create tables if not exists)
  2. Load embedding model (BGE-small)
  3. Connect to pgvector
  4. Load BM25 index (disk cache → pgvector rebuild fallback)
  5. Load reranker
  6. Initialise Gemini client
"""
import logging
import os
from contextlib import asynccontextmanager

import nltk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.limiter import limiter

from app.config import get_settings

# Set HF_HOME *before* any HuggingFace/FlagEmbedding import so the model
# cache lands on the configured directory.  On Render, point this at a
# persistent disk (HF_HOME=/data/hf_cache) to avoid re-downloading weights
# (~500MB) on every cold start.  Falls back to /tmp/hf_cache (ephemeral).
os.environ.setdefault("HF_HOME", get_settings().hf_home)

from app.database import init_db
from app.rag.embedder import get_embedder
from app.rag.vectorstore import get_vectorstore
from app.rag.bm25_index import get_bm25_index
from app.rag.reranker import get_reranker
from app.rag.pipeline import get_gemini_model
from app.services.document_service import rebuild_bm25_from_vectorstore
from app.cache.client import ping_redis
from app.cache.kb_version import get_kb_version

# Import all routers
from app.routers import chat, documents, feedback, analytics, health, admin_auth, visits, knowledge_gaps

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Rate Limiter (shared singleton, defined in app/limiter.py) ───────────────


# ─── Startup / Shutdown ───────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — runs setup on startup, cleanup on shutdown."""
    logger.info("=" * 60)
    logger.info(f"  Starting {settings.app_name} v{settings.app_version}")
    logger.info("=" * 60)

    # 1. Init DB (create tables in Neon PostgreSQL)
    logger.info("Initializing database...")
    await init_db()

    # 2. Load embedding model (blocks until loaded)
    logger.info("Loading embedding model...")
    get_embedder()

    # 3. Connect to pgvector (initialise singleton, verifies DB reachability)
    logger.info("Initialising pgvector store...")
    get_vectorstore()

    # 4. Load BM25 — try disk cache first, rebuild from pgvector only if needed
    logger.info("Loading BM25 index...")
    current_kb_version = get_kb_version()   # fast Redis read (~10ms), 0 if Redis down
    bm25 = get_bm25_index()
    if not bm25.load_from_disk(current_kb_version):
        logger.info("BM25 disk cache miss — rebuilding from pgvector (first cold start or KB changed)...")
        await rebuild_bm25_from_vectorstore()

    # 5. Load reranker
    logger.info("Loading reranker model...")
    get_reranker()

    # 6. Initialise Gemini client
    logger.info("Initialising Gemini client...")
    get_gemini_model()

    # 7. Test Redis / cache connectivity
    logger.info("Testing Upstash Redis connectivity...")
    redis_ok = await ping_redis()
    if redis_ok:
        logger.info("✅ Upstash Redis connected — response caching active")
    else:
        logger.warning(
            "⚠️  Upstash Redis unavailable — response caching DISABLED. "
            "Set UPSTASH_REDIS_URL and UPSTASH_REDIS_TOKEN to enable."
        )

    logger.info("✅ CampusGPT ready to serve requests")
    yield

    # Cleanup (if needed)
    logger.info("Shutting down CampusGPT...")


# ─── App Factory ──────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="CampusGPT API",
        description="Production-ready RAG API for university students",
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS — allow frontend origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            settings.frontend_url,
            "http://localhost:5173",
            "http://localhost:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled error on {request.url}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Please try again."},
        )

    # Register routers
    app.include_router(health.router)
    app.include_router(admin_auth.router)   # login / logout — must be first so cookie is set before admin routes
    app.include_router(chat.router)
    app.include_router(documents.router)
    app.include_router(feedback.router)
    app.include_router(analytics.router)
    app.include_router(visits.router)
    app.include_router(knowledge_gaps.router)

    return app


app = create_app()
