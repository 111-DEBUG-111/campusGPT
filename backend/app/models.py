"""
SQLAlchemy Models for CampusGPT
"""
import json
from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Float, Text,
    DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Conversation -------------------------------------------------------------

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Anonymous session token — identifies which browser session owns this conversation.
    # NULL for legacy rows created before auth was introduced (they become invisible to users).
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="New Conversation")
    # knowledge_mode: "hybrid" | "official" | "experience"
    knowledge_mode: Mapped[str] = mapped_column(String(20), default="hybrid")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )


# --- Message ------------------------------------------------------------------

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    feedback: Mapped[list["Feedback"]] = relationship(
        "Feedback", back_populates="message", passive_deletes=True
    )

    @property
    def sources(self) -> list[dict]:
        if self.sources_json:
            return json.loads(self.sources_json)
        return []

    @property
    def feedback_given(self) -> bool:
        return len(self.feedback) > 0

    @property
    def feedback_type(self) -> str | None:
        return self.feedback[0].rating if self.feedback else None

    @property
    def feedback_timestamp(self) -> datetime | None:
        return self.feedback[0].created_at if self.feedback else None


# --- Feedback -----------------------------------------------------------------

class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rating: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Immutable snapshots for administrative review
    conversation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    conversation_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    assistant_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    message: Mapped["Message | None"] = relationship("Message", back_populates="feedback")


# --- Document -----------------------------------------------------------------

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100), default="general")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # Knowledge Source Modes — added v2.0
    # source_type: "official" | "experience"
    source_type: Mapped[str] = mapped_column(String(20), default="official")
    # author: populated only for experience documents
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Analytics Event ----------------------------------------------------------

class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieved_chunks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Cache tracking (added v1.3)
    cache_hit: Mapped[bool | None] = mapped_column(nullable=True)
    kb_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # LLM fallback model tracking (added v2.3)
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

# --- Visitor Session ----------------------------------------------------------

class VisitorSession(Base):
    """Tracks unique chat-page visitors by anonymous browser session token."""
    __tablename__ = "visitor_sessions"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --- Knowledge Gap ------------------------------------------------------------

class KnowledgeGap(Base):
    """University questions the KB could not fully answer (aggregated by normalized query)."""
    __tablename__ = "knowledge_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    query: Mapped[str] = mapped_column(Text)
    query_normalized: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    knowledge_mode: Mapped[str] = mapped_column(String(20), default="hybrid")
    last_answer_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# NOTE: document_chunks table is managed via raw DDL in database.py
# (see _apply_migrations). It uses the pgvector `vector` column type which
# requires the extension to be enabled first — handled there.
# We do not define an ORM model for it to avoid the pgvector Python package
# dependency; all vector ops use raw SQL via asyncpg.
