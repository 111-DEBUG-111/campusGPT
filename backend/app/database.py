"""
CampusGPT SQLAlchemy Database Setup
Uses asyncpg for async PostgreSQL (Neon) support.
"""
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

logger = logging.getLogger(__name__)
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


async def _apply_migrations(conn) -> None:
    """
    Lightweight incremental migration runner.
    Uses IF NOT EXISTS / IF EXISTS guards so every statement is idempotent
    and safe to replay on every startup (no-ops once already applied).

    Add new ALTER TABLE statements here instead of touching create_all —
    create_all only creates missing tables; it never alters existing ones.
    """
    migrations = [
        # v1.1 — anonymous session isolation
        # Scopes each conversation to the browser session that created it.
        """
        ALTER TABLE conversations
            ADD COLUMN IF NOT EXISTS session_id VARCHAR(128)
        """,
        # Index for fast per-session queries (WHERE session_id = ?)
        """
        CREATE INDEX IF NOT EXISTS ix_conversations_session_id
            ON conversations (session_id)
        """,

        # v1.2 — document_chunks table for pgvector storage
        # Created here (not via ORM) so we can use the `vector(X)` column
        # type without requiring the pgvector Python package in SQLAlchemy.
        # Dynamically sized based on settings.vector_dimension.
        f"""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id             VARCHAR(36)   PRIMARY KEY,
            document_id    INTEGER       NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            filename       VARCHAR(255)  NOT NULL,
            category       VARCHAR(100)  NOT NULL,
            text           TEXT          NOT NULL,
            embedding      vector({settings.vector_dimension})  NOT NULL,
            page_number    INTEGER,
            chunk_index    INTEGER       NOT NULL DEFAULT 0,
            section_title  VARCHAR(500),
            section_path   VARCHAR(1000),
            chunk_type     VARCHAR(50)   NOT NULL DEFAULT 'text',
            heading_level  INTEGER
        )
        """,

        # v1.2a — metadata indexes on document_chunks
        "CREATE INDEX IF NOT EXISTS ix_dc_document_id ON document_chunks (document_id)",
        "CREATE INDEX IF NOT EXISTS ix_dc_category     ON document_chunks (category)",
        "CREATE INDEX IF NOT EXISTS ix_dc_section_title ON document_chunks (section_title)",
        "CREATE INDEX IF NOT EXISTS ix_dc_chunk_type   ON document_chunks (chunk_type)",

        # v1.2b — IVFFlat index for cosine ANN search on document_chunks
        # lists=100 is a good default up to ~1M vectors; tune upward if needed.
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding
            ON document_chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """,

        # v1.3 — cache tracking columns on analytics_events
        # nullable: backfills gracefully; rows predating caching have NULL.
        "ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS cache_hit BOOLEAN",
        "ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS kb_version INTEGER",

        # v1.4 — performance indexes on high-query columns
        # These prevent full-table scans on the most frequent WHERE / ORDER BY paths.
        # analytics_events.event_type — every aggregation query filters on this
        "CREATE INDEX IF NOT EXISTS ix_analytics_events_event_type ON analytics_events (event_type)",
        # analytics_events.created_at — WHERE created_at >= thirty_days_ago range scans
        "CREATE INDEX IF NOT EXISTS ix_analytics_events_created_at ON analytics_events (created_at)",
        # messages.created_at — ORDER BY created_at in every conversation fetch
        "CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages (created_at)",
        # documents.status — WHERE status = 'indexed' filter in document listing
        "CREATE INDEX IF NOT EXISTS ix_documents_status ON documents (status)",

        # v2.0 — Knowledge Source Modes
        # source_type column on documents: 'official' | 'experience'
        # Existing rows get DEFAULT 'official' automatically.
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'official'",
        # author: populated for student-experience documents
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS author VARCHAR(255)",
        "CREATE INDEX IF NOT EXISTS ix_documents_source_type ON documents (source_type)",
        # knowledge_mode on conversations: 'hybrid' | 'official' | 'experience'
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS knowledge_mode VARCHAR(20) NOT NULL DEFAULT 'hybrid'",
        # source_type / author on document_chunks — inherits from parent document
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'official'",
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS author VARCHAR(255)",
        "CREATE INDEX IF NOT EXISTS ix_dc_source_type ON document_chunks (source_type)",

        # v2.1 — unique visitor tracking (chat-page sessions)
        # Backfill from existing conversations so prior chat users are not undercounted.
        """
        INSERT INTO visitor_sessions (session_id, first_seen_at, last_seen_at)
        SELECT DISTINCT session_id, MIN(created_at), MAX(updated_at)
        FROM conversations
        WHERE session_id IS NOT NULL
        GROUP BY session_id
        ON CONFLICT (session_id) DO NOTHING
        """,

        # v2.2 — knowledge gap tracking index (table created via create_all)
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_knowledge_gaps_query_normalized ON knowledge_gaps (query_normalized)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_gaps_last_seen_at ON knowledge_gaps (last_seen_at)",

        # v2.3 — LLM fallback model tracking
        "ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS model_used VARCHAR(50)",

        # v2.4 — feedback system improvements: add review columns and adjust cascades
        "ALTER TABLE feedback ALTER COLUMN rating TYPE VARCHAR(20)",
        "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS conversation_id INTEGER",
        "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS conversation_title VARCHAR(255)",
        "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS user_question TEXT",
        "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS assistant_response TEXT",
        "ALTER TABLE feedback ALTER COLUMN message_id DROP NOT NULL",
        "ALTER TABLE feedback DROP CONSTRAINT IF EXISTS feedback_message_id_fkey",
        "ALTER TABLE feedback ADD CONSTRAINT feedback_message_id_fkey FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL",
        "ALTER TABLE feedback DROP CONSTRAINT IF EXISTS feedback_conversation_id_fkey",
        "ALTER TABLE feedback ADD CONSTRAINT feedback_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL",
        "CREATE INDEX IF NOT EXISTS ix_feedback_conversation_id ON feedback (conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_feedback_rating ON feedback (rating)",
        "CREATE INDEX IF NOT EXISTS ix_feedback_created_at ON feedback (created_at)",
    ]
    for sql in migrations:
        await conn.execute(text(sql))


async def init_db() -> None:
    """
    Initialise the database:
      1. Enable the pgvector extension (must happen before create_all so
         the `vector` column type is available when creating document_chunks).
      2. Verify pgvector table dimensions and drop table to migrate if mismatch exists.
      3. Create all missing tables via SQLAlchemy metadata.
      4. Apply incremental column / index migrations.
    """
    async with engine.begin() as conn:
        # Step 1 — pgvector extension (idempotent)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Step 2 — Verify pgvector table dimensions
        table_exists = await conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'document_chunks'
            )
        """))
        if table_exists.scalar():
            col_type_res = await conn.execute(text("""
                SELECT format_type(atttypid, atttypmod) 
                FROM pg_attribute 
                WHERE attrelid = 'document_chunks'::regclass AND attname = 'embedding'
            """))
            col_type = col_type_res.scalar()
            target_type = f"vector({settings.vector_dimension})"
            if col_type and target_type not in col_type:
                logger.warning(
                    f"Vector dimension mismatch: Database has '{col_type}', "
                    f"config expects '{target_type}'. Dropping document_chunks table "
                    f"to recreate with correct dimension."
                )
                await conn.execute(text("DROP TABLE IF EXISTS document_chunks CASCADE"))
                await conn.execute(text("""
                    UPDATE documents 
                       SET status = 'pending', 
                           chunk_count = 0, 
                           indexed_at = NULL,
                           error_message = 'Vector dimension mismatch - requires re-indexing'
                """))

        # Step 3 — create tables
        await conn.run_sync(Base.metadata.create_all)
        # Step 4 — incremental migrations
        await _apply_migrations(conn)



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
