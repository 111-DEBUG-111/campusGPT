"""
Full RAG Pipeline Orchestrator for CampusGPT.

Combines: Query Rewriting → Hybrid Retrieval → Context Assembly → Gemini Response
"""
import logging
import re
import time
from google import genai
from google.genai import types
from app.config import get_settings
from app.rag.query_rewriter import rewrite_query
from app.rag.retriever import hybrid_retrieve
from app.schemas import SourceCitation

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Structured pipeline error ─────────────────────────────────────────────────

class RagPipelineError(Exception):
    """
    Raised by run_rag_pipeline when a classified, user-safe error occurs.
    Carries a clean ``user_message`` and an HTTP ``status_code`` so the
    router can return a well-formed error response without leaking internals.
    """
    def __init__(self, user_message: str, status_code: int = 500):
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code


# ─── Gemini error classifier ───────────────────────────────────────────────────

def _classify_gemini_error(exc: Exception) -> RagPipelineError:
    """
    Inspect a raw Gemini / google-api exception and return a
    :class:`RagPipelineError` with a friendly, actionable message.
    """
    raw = str(exc)

    # ── Quota / rate-limit (HTTP 429) ─────────────────────────────────────────
    if "429" in raw or "quota" in raw.lower() or "rate" in raw.lower():
        # Try to pull out the retry_delay so users know how long to wait
        match = re.search(r"retry.*?in\s+(\d+)(\.\\d+)?s", raw, re.IGNORECASE)
        if match:
            wait = int(match.group(1)) + 1          # round up
            if wait >= 60:
                wait_str = f"{wait // 60} min {wait % 60}s" if wait % 60 else f"{wait // 60} min"
            else:
                wait_str = f"{wait}s"
            return RagPipelineError(
                f"Gemini AI rate limit reached — please try again in {wait_str}.",
                status_code=429,
            )
        # Daily quota exhausted (no retry-after)
        if "GenerateRequestsPerDay" in raw or "per_day" in raw.lower() or "per day" in raw.lower():
            return RagPipelineError(
                "Gemini AI daily quota exhausted. The free tier limit has been reached for today — "
                "please try again tomorrow or contact the admin.",
                status_code=429,
            )
        return RagPipelineError(
            "Gemini AI is temporarily rate-limited. Please wait a moment and try again.",
            status_code=429,
        )

    # ── Authentication / API key ───────────────────────────────────────────────
    if "401" in raw or "403" in raw or "API_KEY" in raw.upper() or "api key" in raw.lower():
        return RagPipelineError(
            "Gemini AI authentication failed — the API key may be invalid or missing.",
            status_code=503,
        )

    # ── Service unavailable / server-side error ────────────────────────────────
    if "503" in raw or "502" in raw or "unavailable" in raw.lower():
        return RagPipelineError(
            "Gemini AI is currently unavailable. Please try again in a few moments.",
            status_code=503,
        )

    # ── Safety / content blocked ───────────────────────────────────────────────
    if "safety" in raw.lower() or "blocked" in raw.lower() or "HARM" in raw:
        return RagPipelineError(
            "Your question was blocked by the AI safety filter. Please rephrase and try again.",
            status_code=422,
        )

    # ── Generic fallback ──────────────────────────────────────────────────────
    return RagPipelineError(
        "The AI model encountered an error while generating a response. Please try again.",
        status_code=500,
    )


# ─── Gemini client singleton ───────────────────────────────────────────────────
# The new google-genai SDK uses genai.Client (not genai.GenerativeModel).
# A single Client instance is reused across all requests — it manages its own
# underlying HTTP connection pool and is thread-safe.
_gemini_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    """Return the singleton google.genai Client, creating it on first call."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
        logger.info(f"Gemini client initialised (model: '{settings.gemini_model}').")
    return _gemini_client


# Keep the old name as an alias so main.py's lifespan call (`get_gemini_model()`)
# continues to work without changes there.
def get_gemini_model() -> genai.Client:
    """Alias for get_gemini_client() — preserves the lifespan hook in main.py."""
    return get_gemini_client()


SYSTEM_PROMPT = """You are CampusGPT, a knowledgeable and friendly AI assistant for university students.

You answer questions about academics, placements, clubs, internships, campus life, hostel facilities, and university policies.

Guidelines:
- Answer based ONLY on the provided context from university documents and student experiences
- If the context doesn't contain enough information, say so honestly — don't make things up
- Be friendly, concise, and helpful (like an experienced senior student)
- Use bullet points or numbered lists when listing multiple things
- Cite your sources naturally in the response (e.g., "According to the Academic Handbook...")
- If a question is outside the university context, gently redirect back to campus topics

Context from university knowledge base:
{context}

Conversation history:
{history}
"""


def format_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a readable context block for Gemini."""
    if not chunks:
        return "No relevant documents found in the knowledge base."

    context_parts = []
    for i, chunk in enumerate(chunks, start=1):
        # Build source label: filename + page + section breadcrumb
        source_info = f"[Source {i}: {chunk['filename']}"
        if chunk.get("page_number"):
            source_info += f", Page {chunk['page_number']}"
        if chunk.get("section_path"):
            source_info += f", Section: {chunk['section_path']}"
        elif chunk.get("section_title"):
            source_info += f", Section: {chunk['section_title']}"
        source_info += f", Category: {chunk['category']}]"

        context_parts.append(f"{source_info}\n{chunk['text']}")

    return "\n\n---\n\n".join(context_parts)


def format_history(messages: list[dict]) -> str:
    """Format conversation history for context."""
    if not messages:
        return "No previous messages."
    parts = []
    for msg in messages[-6:]:  # Last 3 turns (6 messages)
        role = "Student" if msg["role"] == "user" else "CampusGPT"
        parts.append(f"{role}: {msg['content'][:300]}")
    return "\n".join(parts)


def chunks_to_citations(chunks: list[dict]) -> list[SourceCitation]:
    """Convert retrieved chunks to SourceCitation objects for the response."""
    seen = set()
    citations = []
    for chunk in chunks:
        key = f"{chunk['filename']}:{chunk.get('page_number')}:{chunk.get('section_title')}"
        if key not in seen:
            seen.add(key)
        citations.append(
            SourceCitation(
                document_id=str(chunk.get("document_id", "")),
                filename=chunk["filename"],
                category=chunk["category"],
                page_number=chunk.get("page_number"),
                chunk_text=chunk["text"][:300] + ("..." if len(chunk["text"]) > 300 else ""),
                relevance_score=round(chunk.get("rerank_score", chunk.get("rrf_score", 0.0)), 4),
                # Section metadata (None for legacy chunks)
                section_title=chunk.get("section_title"),
                section_path=chunk.get("section_path"),
                chunk_type=chunk.get("chunk_type"),
            )
        )
    return citations


def run_rag_pipeline(
    query: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Full RAG pipeline.

    Args:
        query: User's question
        conversation_history: List of {"role": str, "content": str} dicts

    Returns:
        {
            "answer": str,
            "sources": list[SourceCitation],
            "retrieved_chunks": int,
            "query_time_ms": float,
        }
    """
    start_time = time.time()
    history = conversation_history or []

    # ── Step 1: Query Rewriting ────────────────────────────────────────────────
    logger.info(f"RAG pipeline started for query: {query[:80]}...")
    rewritten_queries = rewrite_query(query)
    logger.info(f"Query rewrites: {rewritten_queries}")

    # ── Step 2: Hybrid Retrieval ───────────────────────────────────────────────
    chunks = hybrid_retrieve(
        query=query,
        queries=rewritten_queries,
        top_k_rerank=settings.max_context_chunks,
    )
    logger.info(f"Retrieved {len(chunks)} final chunks after reranking")

    # ── Step 3: Context Assembly ───────────────────────────────────────────────
    context = format_context(chunks)
    history_text = format_history(history)

    # ── Step 4: Gemini Response ────────────────────────────────────────────────
    client = get_gemini_client()

    prompt = SYSTEM_PROMPT.format(context=context, history=history_text)
    full_prompt = prompt + f"\n\nStudent question: {query}"

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2048,
            ),
        )
        answer = response.text.strip()
    except Exception as e:
        logger.error(f"Gemini generation failed: {e}")
        # Convert to a structured error with a clean user message and HTTP
        # status code.  The router catches RagPipelineError specifically and
        # returns the right HTTP status + detail — no internal details leaked.
        raise _classify_gemini_error(e) from e

    # ── Step 5: Citations ──────────────────────────────────────────────────────
    citations = chunks_to_citations(chunks)

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(f"RAG pipeline completed in {elapsed_ms:.0f}ms")

    return {
        "answer": answer,
        "sources": citations,
        "retrieved_chunks": len(chunks),
        "query_time_ms": elapsed_ms,
        # is_error=False signals to the cache layer that this result is safe
        # to store.  The cache checks this flag before every SET operation.
        "is_error": False,
    }
