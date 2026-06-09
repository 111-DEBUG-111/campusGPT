"""
Pydantic Schemas for CampusGPT API
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


# ─── Source / Citation ────────────────────────────────────────────────────────

class SourceCitation(BaseModel):
    document_id: str
    filename: str
    category: str
    page_number: Optional[int] = None
    chunk_text: str
    relevance_score: float


# ─── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[int] = None
    # Feature #5: Browser-generated UUID (Option A). The field is intentionally
    # typed as Optional[str] so that a future auth middleware can populate it
    # from a validated JWT `sub` without any schema change.
    user_id: Optional[str] = Field(None, max_length=128)


class ChatResponse(BaseModel):
    conversation_id: int
    message_id: int
    answer: str
    sources: list[SourceCitation]
    query_time_ms: float
    # Feature #4: True when the answer was served from cache.
    cached: bool = False


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: list[SourceCitation]
    # Feature #3: Full retrieved chunk data (useful for debugging / QA eval).
    retrieved_chunks: list[dict] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    title: str
    # Feature #5: surfaced so the frontend can verify ownership
    user_id: Optional[str] = None
    summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = []

    model_config = {"from_attributes": True}


class ConversationListItem(BaseModel):
    id: int
    title: str
    user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


# ─── Document / Upload ────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: int
    filename: str
    original_filename: str
    category: str
    description: Optional[str] = None
    chunk_count: int
    status: str
    file_size_bytes: int
    uploaded_at: datetime
    indexed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentOut]
    total: int


# ─── Feedback ─────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    message_id: int
    rating: str = Field(..., pattern="^(helpful|not_helpful)$")
    comment: Optional[str] = Field(None, max_length=500)


class FeedbackResponse(BaseModel):
    id: int
    message_id: int
    rating: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Analytics ────────────────────────────────────────────────────────────────

class AnalyticsSummary(BaseModel):
    total_questions: int
    total_conversations: int
    total_documents: int
    total_chunks: int
    helpful_count: int
    not_helpful_count: int
    avg_response_time_ms: float
    top_queries: list[dict]
    feedback_by_day: list[dict]
    questions_by_day: list[dict]


# ─── Admin ────────────────────────────────────────────────────────────────────

class ReindexResponse(BaseModel):
    message: str
    documents_reindexed: int


# ─── Memory (Feature #7 debug endpoint) ──────────────────────────────────────

class MemoryOut(BaseModel):
    id: int
    conversation_id: int
    content_summary: str
    turn_range: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
