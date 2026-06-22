"""
Knowledge Gap Service — Record and list unanswered university questions.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.response_cache import _normalize_query
from app.models import KnowledgeGap
from app.services.analytics_service import _sanitize_query

logger = logging.getLogger(__name__)

_ANSWER_SNIPPET_MAX = 300


def _answer_snippet(answer: str) -> str:
    clean = answer.strip()
    if len(clean) <= _ANSWER_SNIPPET_MAX:
        return clean
    return clean[:_ANSWER_SNIPPET_MAX] + "..."


async def record_knowledge_gap(
    db: AsyncSession,
    query: str,
    knowledge_mode: str,
    answer: str,
) -> None:
    """Upsert a knowledge-gap entry keyed by normalized query text."""
    sanitized = _sanitize_query(query)
    normalized = _normalize_query(sanitized)
    if not normalized:
        return

    now = datetime.now(timezone.utc)
    snippet = _answer_snippet(answer)

    result = await db.execute(
        select(KnowledgeGap).where(KnowledgeGap.query_normalized == normalized)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.count += 1
        existing.last_seen_at = now
        existing.last_answer_snippet = snippet
        existing.knowledge_mode = knowledge_mode
        stored_count = existing.count
    else:
        db.add(
            KnowledgeGap(
                query=sanitized,
                query_normalized=normalized,
                count=1,
                knowledge_mode=knowledge_mode,
                last_answer_snippet=snippet,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        stored_count = 1

    await db.commit()
    logger.info("Recorded knowledge gap (count=%s): %s", stored_count, sanitized[:80])


async def get_knowledge_gaps(db: AsyncSession, limit: int = 50) -> list[KnowledgeGap]:
    """Return knowledge gaps sorted by most recently asked."""
    result = await db.execute(
        select(KnowledgeGap)
        .order_by(KnowledgeGap.last_seen_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
