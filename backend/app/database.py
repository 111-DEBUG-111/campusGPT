"""
CampusGPT SQLAlchemy Database Setup
Uses asyncpg for async PostgreSQL (Neon) support.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # pool_pre_ping detects dropped connections (Neon idles out after 5 min)
    pool_pre_ping=True,
    # Neon free tier allows ~10 concurrent connections
    pool_size=5,
    max_overflow=10,
    # asyncpg requires ssl via connect_args, NOT as a URL query param.
    # Strip ?sslmode=... / ?ssl=... / ?channel_binding=... from DATABASE_URL.
    connect_args={"ssl": "require"},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def init_db() -> None:
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
