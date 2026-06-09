"""
CampusGPT SQLAlchemy Database Setup
Uses aiosqlite for async SQLite support.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def _migrate_existing_db(conn) -> None:
    """
    Safely add new nullable columns and tables to an existing SQLite database.

    SQLite does not support adding columns with `ALTER TABLE ... ADD COLUMN`
    unless the column is nullable or has a default value. All new columns here
    satisfy that requirement.

    TODO (post-MVP): Replace this with Alembic for versioned, production-grade
    migrations when moving beyond the MVP stage.
    """
    import logging
    log = logging.getLogger(__name__)

    # Columns to add: (table, column, type_definition)
    new_columns = [
        ("conversations", "user_id",             "VARCHAR(128)"),
        ("conversations", "summary",              "TEXT"),
        ("conversations", "summary_updated_at",   "DATETIME"),
        ("messages",      "retrieved_chunks_json", "TEXT"),
    ]

    for table, col, col_type in new_columns:
        try:
            await conn.execute(
                __import__("sqlalchemy").text(
                    f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"
                )
            )
            log.info(f"Migration: added column {table}.{col}")
        except Exception:
            # Column already exists — this is expected on subsequent startups.
            pass


async def init_db() -> None:
    """Create all tables on startup and apply lightweight column migrations."""
    async with engine.begin() as conn:
        # 1. Create new tables (IF NOT EXISTS — safe to repeat)
        await conn.run_sync(Base.metadata.create_all)
        # 2. Add new nullable columns to existing tables
        await _migrate_existing_db(conn)


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
