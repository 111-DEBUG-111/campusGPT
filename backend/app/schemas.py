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
    # Section metadata — populated for semantically-chunked documents.
    # None for legacy chunks ingested before the semantic chunker.
    section_title: Optional[str] = None   # immediate heading (e.g. "2.1 Grading")
    section_path: Optional[str] = None    # breadcrumb (e.g. "Academics > 2.1 Grading")
    chunk_type: Optional[str] = None      # "text" | "table" | "heading_intro"
    # Knowledge Source Modes metadata — added v2.0
    source_type: Optional[str] = None     # "official" | "experience"
    author: Optional[str] = None          # e.g. "Divyansh Rathore" (experience only)


# ─── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[int] = None
    # Knowledge Source Mode — persisted per conversation.
    # If omitted, the server reads the conversation's stored mode.
    knowledge_mode: Optional[str] = Field(
        None, pattern="^(hybrid|official|experience)$"
    )
    request_id: Optional[str] = None


class ChatResponse(BaseModel):
    conversation_id: int
    message_id: int
    answer: str
    sources: list[SourceCitation]
    query_time_ms: float
    knowledge_mode: str = "hybrid"  # echo back the mode used
    model_used: str = "gemini"      # model that generated the response


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: list[SourceCitation]
    created_at: datetime
    feedback_given: bool = False
    feedback_type: Optional[str] = None
    feedback_timestamp: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = []
    knowledge_mode: str = "hybrid"  # returned so the frontend can restore the selector

    model_config = {"from_attributes": True}


class ConversationListItem(BaseModel):
    id: int
    title: str
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
    # Knowledge Source Modes — added v2.0
    source_type: str = "official"
    author: Optional[str] = None
    uploaded_at: datetime
    indexed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentOut]
    total: int


class DocumentUpdate(BaseModel):
    """Payload for PATCH /api/admin/documents/{id}"""
    source_type: Optional[str] = Field(None, pattern="^(official|experience)$")
    author: Optional[str] = Field(None, max_length=255)
    category: Optional[str] = None


# ─── Feedback ─────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    message_id: int
    rating: str = Field(..., pattern="^(helpful|not_helpful)$")
    comment: Optional[str] = Field(None, max_length=500)


class FeedbackResponse(BaseModel):
    id: int
    message_id: Optional[int] = None
    rating: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NegativeFeedbackOut(BaseModel):
    id: int
    message_id: Optional[int] = None
    conversation_id: Optional[int] = None
    created_at: datetime
    conversation_title: Optional[str] = None
    user_question: Optional[str] = None
    assistant_response: Optional[str] = None
    rating: str

    model_config = {"from_attributes": True}


class PaginatedNegativeFeedbackResponse(BaseModel):
    items: list[NegativeFeedbackOut]
    total: int
    page: int
    pages: int
    limit: int


# ─── Analytics ────────────────────────────────────────────────────────────────

class AnalyticsSummary(BaseModel):
    total_unique_visitors: int
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

class KnowledgeGapOut(BaseModel):
    id: int
    query: str
    count: int
    knowledge_mode: str
    last_answer_snippet: str | None
    first_seen_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class ReindexResponse(BaseModel):
    message: str
    documents_reindexed: int
