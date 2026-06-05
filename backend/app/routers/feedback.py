"""
Feedback Router — POST /api/feedback
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Feedback, Message
from app.schemas import FeedbackRequest, FeedbackResponse
from app.services.analytics_service import log_event

router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit helpful/not-helpful feedback for an assistant message."""
    # Verify message exists
    result = await db.execute(
        select(Message).where(Message.id == request.message_id)
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="Can only rate assistant messages")

    # Store feedback
    feedback = Feedback(
        message_id=request.message_id,
        rating=request.rating,
        comment=request.comment,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    # Log analytics
    await log_event(db=db, event_type="feedback", query=request.rating)

    return feedback
