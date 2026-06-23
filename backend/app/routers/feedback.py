"""
Feedback Router — POST /api/feedback, GET /api/admin/feedback/negative
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.dependencies import verify_admin_cookie, get_session_token
from app.limiter import limiter
from app.models import Feedback, Message, Conversation
from app.schemas import (
    FeedbackRequest, FeedbackResponse,
    PaginatedNegativeFeedbackResponse
)
from app.services.analytics_service import log_event

router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
@limiter.limit("30/minute")   # generous but bounded — prevents analytics spam
async def submit_feedback(
    request: Request,          # required by slowapi for IP extraction
    body: FeedbackRequest,     # renamed from `request` to avoid collision
    db: AsyncSession = Depends(get_db),
    session_token: str = Depends(get_session_token),
):
    """Submit helpful/not-helpful feedback for an assistant message."""
    # Verify message exists and belongs to the user's session
    result = await db.execute(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.id == body.message_id)
        .where(Conversation.session_id == session_token)
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.role != "assistant":
        raise HTTPException(status_code=400, detail="Can only rate assistant messages")

    # Prevent duplicate submissions for the same message
    existing_result = await db.execute(
        select(Feedback).where(Feedback.message_id == body.message_id)
    )
    existing_feedback = existing_result.scalar_one_or_none()
    if existing_feedback:
        # Return existing state and skip logging duplicates
        return existing_feedback

    # Retrieve conversation title and preceding user message at this moment
    conversation_id = message.conversation_id
    conversation_title = None
    user_question = None
    assistant_response = message.content

    # Get conversation
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()
    if conversation:
        conversation_title = conversation.title

    # Get preceding user message
    user_msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .where(Message.role == "user")
        .where(Message.created_at < message.created_at)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    user_msg = user_msg_result.scalar_one_or_none()
    if user_msg:
        user_question = user_msg.content

    # Store feedback with immutable snapshot fields
    feedback = Feedback(
        message_id=body.message_id,
        rating=body.rating,
        comment=body.comment,
        conversation_id=conversation_id,
        conversation_title=conversation_title,
        user_question=user_question,
        assistant_response=assistant_response,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    # Log analytics
    await log_event(db=db, event_type="feedback", query=body.rating)

    return feedback


@router.get("/admin/feedback/negative", response_model=PaginatedNegativeFeedbackResponse)
@limiter.limit("30/minute")
async def get_negative_feedback(
    request: Request,
    page: int = 1,
    limit: int = 10,
    search: str = "",
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_cookie),
):
    """Retrieve negative feedback records (admin-only)."""
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10
    elif limit > 100:
        limit = 100

    offset = (page - 1) * limit

    # Build query on Feedback model (which is the source of truth)
    query = select(Feedback).where(Feedback.rating == "not_helpful")

    # Apply search filter if specified
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (Feedback.user_question.ilike(search_pattern)) |
            (Feedback.assistant_response.ilike(search_pattern)) |
            (Feedback.conversation_title.ilike(search_pattern))
        )

    # Sort by newest first
    query = query.order_by(Feedback.created_at.desc())

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get paginated feedbacks
    query = query.offset(offset).limit(limit)
    feedback_result = await db.execute(query)
    feedbacks = feedback_result.scalars().all()

    pages = (total + limit - 1) // limit if total > 0 else 1

    return PaginatedNegativeFeedbackResponse(
        items=list(feedbacks),
        total=total,
        page=page,
        pages=pages,
        limit=limit,
    )
