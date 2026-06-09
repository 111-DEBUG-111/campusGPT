"""
Conversation Service — History retrieval, summarization, and context building.

Feature #1: Fix history ordering — retrieve most recent N messages in chronological order.
Feature #2: Auto-summarization when message count exceeds the threshold.
"""
import logging
import json
import google.generativeai as genai
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import Conversation, Message
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Feature #1: Correct History Retrieval ───────────────────────────────────

async def get_recent_history(
    db: AsyncSession,
    conversation_id: int,
    window: int | None = None,
) -> list[dict]:
    """
    Return the most recent `window` messages in chronological (ascending) order.

    Fix: The old code used ORDER BY ASC + LIMIT which returned the *oldest*
    messages. The correct approach is to ORDER BY DESC + LIMIT (get newest),
    then reverse the result so the LLM sees them in time order.
    """
    window = window or settings.history_window

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())  # newest first
        .limit(window)
    )
    messages = result.scalars().all()
    # Reverse to restore chronological order for the LLM
    messages = list(reversed(messages))
    return [{"role": m.role, "content": m.content} for m in messages]


# ─── Feature #2: Conversation Summarization ──────────────────────────────────

async def get_message_count(db: AsyncSession, conversation_id: int) -> int:
    """Return total message count for a conversation."""
    return await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.conversation_id == conversation_id)
    ) or 0


async def maybe_summarize(
    db: AsyncSession,
    conversation: Conversation,
) -> None:
    """
    Check if the conversation has grown beyond the summarization threshold.
    If so, call Gemini to generate a running summary and persist it.

    Designed to run as a FastAPI BackgroundTask so it never blocks the response.
    """
    count = await get_message_count(db, conversation.id)
    if count < settings.summarize_threshold:
        return

    # Avoid re-summarizing a conversation that was already summarized recently
    # (only re-run if at least 20 new messages have arrived since last summary)
    if conversation.summary_updated_at:
        # Count messages since last summary update
        new_count = await db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation.id)
            .where(Message.created_at > conversation.summary_updated_at)
        ) or 0
        if new_count < 20:
            logger.debug(
                f"Skipping summarization for conv {conversation.id}: "
                f"only {new_count} new messages since last summary."
            )
            return

    logger.info(f"Generating summary for conversation {conversation.id} ({count} messages)...")

    # Fetch all messages for the conversation (we need everything for a good summary)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    all_messages = result.scalars().all()

    # Build a condensed transcript (truncate long messages to save tokens)
    transcript_parts = []
    for m in all_messages:
        role = "Student" if m.role == "user" else "CampusGPT"
        transcript_parts.append(f"{role}: {m.content[:400]}")
    transcript = "\n".join(transcript_parts)

    summary_prompt = (
        "You are summarizing a conversation between a university student and CampusGPT.\n\n"
        "Create a concise but comprehensive summary (max 300 words) covering:\n"
        "- Main topics the student asked about\n"
        "- Key information provided in the answers\n"
        "- Any unresolved questions or follow-ups\n\n"
        f"Conversation transcript:\n{transcript}\n\n"
        "Summary:"
    )

    try:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        response = model.generate_content(
            summary_prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=400,
            ),
        )
        summary = response.text.strip()
        conversation.summary = summary
        conversation.summary_updated_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(f"Summary stored for conversation {conversation.id}")
    except Exception as e:
        logger.error(f"Summarization failed for conversation {conversation.id}: {e}")


# ─── Context Builder ──────────────────────────────────────────────────────────

async def get_conversation_context(
    db: AsyncSession,
    conversation: Conversation,
) -> tuple[str | None, list[dict]]:
    """
    Return (summary, recent_messages) for use in the RAG pipeline.

    - summary: the stored running summary (if any) — covers older history
    - recent_messages: the most recent N messages in chronological order
    """
    summary = conversation.summary  # may be None for short conversations
    recent = await get_recent_history(db, conversation.id)
    return summary, recent
