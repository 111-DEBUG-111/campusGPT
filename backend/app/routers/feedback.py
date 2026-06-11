"""
Feedback Router — POST /api/feedback
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.limiter import limiter
from app.models import Feedback, Message
from app.schemas import FeedbackRequest, FeedbackResponse
from app.services.analytics_service import log_event

router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
@limiter.limit("30/minute")   # generous but bounded — prevents analytics spam
async def submit_feedback(
    request: Request,          # required by slowapi for IP extraction
    body: FeedbackRequest,     # renamed from `request` to avoid collision
    db: AsyncSession = Depends(get_db),
):
    """Submit helpful/not-helpful feedback for an assistant message."""
    # Verify message exists
    result = await db.execute(
        select(Message).where(Message.id == body.message_id)
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="Can only rate assistant messages")

    # Store feedback
    feedback = Feedback(
        message_id=body.message_id,
        rating=body.rating,
        comment=body.comment,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    # Log analytics
    await log_event(db=db, event_type="feedback", query=body.rating)

    return feedback
