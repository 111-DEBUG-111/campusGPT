"""
CampusGPT FastAPI Application

Startup sequence:
  1. Init Neon PostgreSQL DB (create tables if not exists)
  2. Load embedding model (BGE-small)
  3. Connect to Qdrant
  4. Rebuild BM25 index from Qdrant
  5. Load reranker
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.limiter import limiter

from app.config import get_settings
from app.database import init_db
from app.rag.embedder import get_embedder
from app.rag.vectorstore import get_vectorstore
from app.rag.bm25_index import get_bm25_index
from app.rag.reranker import get_reranker
from app.services.document_service import rebuild_bm25_from_qdrant

# Import all routers
from app.routers import chat, documents, feedback, analytics, health

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

    # 3. Connect to Qdrant
    logger.info("Connecting to Qdrant...")
    get_vectorstore()

    # 4. Rebuild BM25 from Qdrant
    logger.info("Rebuilding BM25 index from Qdrant...")
    await rebuild_bm25_from_qdrant()

    # 5. Load reranker
    logger.info("Loading reranker model...")
    get_reranker()

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
    app.include_router(chat.router)
    app.include_router(documents.router)
    app.include_router(feedback.router)
    app.include_router(analytics.router)

    return app


app = create_app()
