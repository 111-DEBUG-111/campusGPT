"""
Analytics Service — Query logging and aggregation.
"""
import logging
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date

from app.models import AnalyticsEvent, Message, Feedback, Document, Conversation
from app.schemas import AnalyticsSummary

logger = logging.getLogger(__name__)

# Maximum query length to store — matches ChatRequest.query max_length.
_QUERY_MAX_LENGTH = 2000


class _HTMLStripper(HTMLParser):
    """Minimal HTML-tag stripper using the stdlib parser (no deps)."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:  # noqa: D102
        self._parts.append(data)

    def get_text(self) -> str:  # noqa: D102
        return "".join(self._parts)


def _sanitize_query(query: str) -> str:
    """
    Strip HTML tags and enforce the max-length cap before storage.

    This closes the stored-XSS vector: even if an attacker submits
    ``<script>alert(1)</script>`` as a chat query the value persisted
    in AnalyticsEvent.query will be the plain-text equivalent
    (``alert(1)`` in that example) rather than raw markup.
    """
    stripper = _HTMLStripper()
    stripper.feed(query)
    clean = stripper.get_text().strip()
    return clean[:_QUERY_MAX_LENGTH]


async def log_event(
    db: AsyncSession,
    event_type: str,
    query: str | None = None,
    conversation_id: int | None = None,
    response_time_ms: float | None = None,
    retrieved_chunks: int | None = None,
) -> None:
    """Log an analytics event.

    The ``query`` string is sanitised before storage: HTML tags are stripped
    and the value is truncated to ``_QUERY_MAX_LENGTH`` characters so that
    no raw markup can be persisted and later reflected in the dashboard.
    """
    sanitized_query = _sanitize_query(query) if query is not None else None
    event = AnalyticsEvent(
        event_type=event_type,
        query=sanitized_query,
        conversation_id=conversation_id,
        response_time_ms=response_time_ms,
        retrieved_chunks=retrieved_chunks,
    )
    db.add(event)
    await db.commit()


async def get_analytics_summary(db: AsyncSession) -> AnalyticsSummary:
    """Aggregate analytics data for the dashboard."""

    # Total questions
    q_count = await db.scalar(
        select(func.count()).select_from(AnalyticsEvent)
        .where(AnalyticsEvent.event_type == "query")
    )

    # Total conversations
    conv_count = await db.scalar(
        select(func.count()).select_from(Conversation)
    )

    # Documents
    doc_count = await db.scalar(
        select(func.count()).select_from(Document)
        .where(Document.status == "indexed")
    )

    # Total chunks
    chunk_sum = await db.scalar(
        select(func.sum(Document.chunk_count))
        .where(Document.status == "indexed")
    )

    # Feedback counts
    helpful = await db.scalar(
        select(func.count()).select_from(Feedback)
        .where(Feedback.rating == "helpful")
    )
    not_helpful = await db.scalar(
        select(func.count()).select_from(Feedback)
        .where(Feedback.rating == "not_helpful")
    )

    # Average response time
    avg_rt = await db.scalar(
        select(func.avg(AnalyticsEvent.response_time_ms))
        .where(AnalyticsEvent.event_type == "query")
        .where(AnalyticsEvent.response_time_ms.isnot(None))
    )

    # Top 10 queries
    top_q_result = await db.execute(
        select(AnalyticsEvent.query, func.count().label("count"))
        .where(AnalyticsEvent.event_type == "query")
        .where(AnalyticsEvent.query.isnot(None))
        .group_by(AnalyticsEvent.query)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_queries = [{"query": r[0], "count": r[1]} for r in top_q_result.fetchall()]

    # Questions by day (last 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    qbd_result = await db.execute(
        select(
            cast(AnalyticsEvent.created_at, Date).label("date"),
            func.count().label("count")
        )
        .where(AnalyticsEvent.event_type == "query")
        .where(AnalyticsEvent.created_at >= thirty_days_ago)
        .group_by(cast(AnalyticsEvent.created_at, Date))
        .order_by(cast(AnalyticsEvent.created_at, Date))
    )
    questions_by_day = [{"date": str(r[0]), "count": r[1]} for r in qbd_result.fetchall()]

    # Feedback by day
    fbd_result = await db.execute(
        select(
            cast(Feedback.created_at, Date).label("date"),
            Feedback.rating,
            func.count().label("count")
        )
        .where(Feedback.created_at >= thirty_days_ago)
        .group_by(cast(Feedback.created_at, Date), Feedback.rating)
        .order_by(cast(Feedback.created_at, Date))
    )
    feedback_by_day = [
        {"date": str(r[0]), "rating": r[1], "count": r[2]}
        for r in fbd_result.fetchall()
    ]

    return AnalyticsSummary(
        total_questions=q_count or 0,
        total_conversations=conv_count or 0,
        total_documents=doc_count or 0,
        total_chunks=int(chunk_sum or 0),
        helpful_count=helpful or 0,
        not_helpful_count=not_helpful or 0,
        avg_response_time_ms=round(avg_rt or 0, 1),
        top_queries=top_queries,
        feedback_by_day=feedback_by_day,
        questions_by_day=questions_by_day,
    )
