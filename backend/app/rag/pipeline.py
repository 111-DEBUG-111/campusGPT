"""
Full RAG Pipeline Orchestrator for CampusGPT.

Combines: Query Rewriting → Hybrid Retrieval → Context Assembly → Gemini Response
"""
import logging
import json
import time
import google.generativeai as genai
from app.config import get_settings
from app.rag.query_rewriter import rewrite_query
from app.rag.retriever import hybrid_retrieve
from app.schemas import SourceCitation

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Gemini model singleton ────────────────────────────────────────────────────
_gemini_model: genai.GenerativeModel | None = None


def get_gemini_model() -> genai.GenerativeModel:
    """Return the singleton Gemini GenerativeModel, creating it on first call."""
    global _gemini_model
    if _gemini_model is None:
        genai.configure(api_key=settings.gemini_api_key)
        _gemini_model = genai.GenerativeModel(settings.gemini_model)
        logger.info(f"Gemini model '{settings.gemini_model}' initialised.")
    return _gemini_model


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
    model = get_gemini_model()

    prompt = SYSTEM_PROMPT.format(context=context, history=history_text)

    try:
        response = model.generate_content(
            [{"role": "user", "parts": [prompt + f"\n\nStudent question: {query}"]}],
            generation_config=genai.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2048,
            ),
        )
        answer = response.text.strip()
    except Exception as e:
        logger.error(f"Gemini generation failed: {e}")
        # Re-raise so the caller (chat.py) handles it via HTTPException.
        # This guarantees a failed generation is NEVER cached.
        raise

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
