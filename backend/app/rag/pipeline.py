"""
Full RAG Pipeline Orchestrator for CampusGPT.

Combines: Query Rewriting → Hybrid Retrieval → Context Assembly → LLM Response
Supports three Knowledge Source Modes: hybrid | official | experience
The LLM generation step uses the LLMOrchestrator (Gemini with Groq fallback).
"""
import logging
import re
import time
from app.config import get_settings
from app.rag.query_rewriter import rewrite_query
from app.rag.retriever import hybrid_retrieve
from app.schemas import SourceCitation

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Structured pipeline error ─────────────────────────────────────────────────
from app.rag.errors import RagPipelineError
from app.services.llm_service import llm_orchestrator
from app.services.progress_service import (
    update_progress,
    STAGE_REWRITING,
    STAGE_RETRIEVING,
    STAGE_RERANKING,
    STAGE_GENERATING,
    STAGE_COMPLETE,
    STATUS_IN_PROGRESS,
    STATUS_COMPLETED,
    STATUS_FAILED,
)



def _classify_llm_error(exc: Exception) -> RagPipelineError:
    """
    Inspect an LLM / HTTP exception (from any provider) and return a
    :class:`RagPipelineError` with a friendly, actionable message.
    Works for errors from Gemini, Groq, or any HTTP-based LLM provider.
    """
    raw = str(exc)

    # ── Quota / rate-limit (HTTP 429 or 413 payload-too-large) ────────────────────────
    if "429" in raw or "413" in raw or "quota" in raw.lower() or "rate" in raw.lower():
        match = re.search(r"retry.*?in\s+(\d+)(\.\d+)?s", raw, re.IGNORECASE)
        if match:
            wait = int(match.group(1)) + 1
            if wait >= 60:
                wait_str = f"{wait // 60} min {wait % 60}s" if wait % 60 else f"{wait // 60} min"
            else:
                wait_str = f"{wait}s"
            return RagPipelineError(
                f"AI rate limit reached — please try again in {wait_str}.",
                status_code=429,
            )
        if "GenerateRequestsPerDay" in raw or "per_day" in raw.lower() or "per day" in raw.lower():
            return RagPipelineError(
                "AI daily quota exhausted. The free tier limit has been reached for today — "
                "please try again tomorrow or contact the admin.",
                status_code=429,
            )
        return RagPipelineError(
            "AI is temporarily rate-limited. Please wait a moment and try again.",
            status_code=429,
        )

    # ── Authentication / API key ─────────────────────────────────────────────────────
    if "401" in raw or "403" in raw or "API_KEY" in raw.upper() or "api key" in raw.lower():
        return RagPipelineError(
            "AI authentication failed — the API key may be invalid or missing.",
            status_code=503,
        )

    # ── Service unavailable / server-side error ────────────────────────────────────────
    if "503" in raw or "502" in raw or "unavailable" in raw.lower():
        return RagPipelineError(
            "AI is currently unavailable. Please try again in a few moments.",
            status_code=503,
        )

    # ── Safety / content blocked ─────────────────────────────────────────────────────
    if "safety" in raw.lower() or "blocked" in raw.lower() or "HARM" in raw:
        return RagPipelineError(
            "Your question was blocked by the AI safety filter. Please rephrase and try again.",
            status_code=422,
        )

    # ── Generic fallback ────────────────────────────────────────────────────────────
    return RagPipelineError(
        "The AI model encountered an error while generating a response. Please try again.",
        status_code=500,
    )


# ─── Startup warmup hook ────────────────────────────────────────────────────────────────
# NOTE: All LLM calls go through LLMOrchestrator in llm_service.py.
# get_gemini_model() is kept only for the startup lifespan warmup in main.py.

def get_gemini_model():
    """Startup warmup — called by main.py lifespan to initialise the LLM orchestrator.
    Returns the orchestrator instance; failure is non-fatal (Groq fallback still works).
    """
    try:
        logger.info("LLM orchestrator initialised (Gemini primary, Groq fallback).")
        return llm_orchestrator
    except Exception as e:
        logger.warning(f"LLM orchestrator warmup warning: {e}")
        return None

# ─── Mode-aware system prompts ─────────────────────────────────────────────────

_SYSTEM_PROMPT_HYBRID = """You are CampusGPT, a knowledgeable and friendly AI assistant for university students.

You answer questions about academics, placements, clubs, internships, campus life, hostel facilities, and university policies.

Guidelines:
- Answer based ONLY on the provided context from university documents and student experiences
- If the context doesn't contain enough information, say so honestly — don't make things up
- Be friendly, concise, and helpful (like an experienced senior student)
- Use bullet points or numbered lists when listing multiple things
- If a question is outside the university context, gently redirect back to campus topics

IMPORTANT — Source Separation Rules (Hybrid Mode):
- When both official documents AND student experience sources are present in the context, you MUST separate them into two clearly labeled sections:
  ### Official Information
  (facts from official university documents, policies, handbooks)
  ### Student Insight
  (advice, observations, and practical tips from student experiences)
- Never blend official facts with personal experiences in the same sentence or paragraph.
- Never present a student's personal experience as official university policy.
- If only one source type is present, you may omit the other section entirely.

Context from university knowledge base:
{context}

Conversation history:
{history}
"""

_SYSTEM_PROMPT_OFFICIAL = """You are CampusGPT, a precise AI assistant for university students.

You answer questions strictly based on official university documents.

Guidelines:
- Answer ONLY using the provided official document context
- If information is not available in the official documents, clearly state: "This information is not available in official university documents."
- Do NOT supplement with personal opinions, student experiences, or information not in the context
- Be precise, factual, and formal
- Cite the source document naturally (e.g., "According to the Academic Handbook...")
- If a question is outside the university context, gently redirect back to campus topics

Context from official university documents:
{context}

Conversation history:
{history}
"""

_SYSTEM_PROMPT_EXPERIENCE = """You are CampusGPT, a friendly AI assistant sharing student perspectives for university students.

You answer questions based on student experience and personal insights.

Guidelines:
- Answer based on the student experience context provided
- ALWAYS include a clear disclaimer: these responses are based on student experiences and personal opinions, and may NOT represent official university policy
- Present insights as student perspectives, not facts (e.g., "Based on student experiences...", "Students have found that...", "One student shared...")
- Do not present any experience-based content as official university policy
- Be friendly, conversational, and relatable — like advice from a senior student
- If a question requires official policy information, recommend checking official university documents
- If a question is outside the university context, gently redirect back to campus topics

Context from student experiences:
{context}

Conversation history:
{history}
"""

_SYSTEM_PROMPTS = {
    "hybrid": _SYSTEM_PROMPT_HYBRID,
    "official": _SYSTEM_PROMPT_OFFICIAL,
    "experience": _SYSTEM_PROMPT_EXPERIENCE,
}


def _get_system_prompt(knowledge_mode: str) -> str:
    return _SYSTEM_PROMPTS.get(knowledge_mode, _SYSTEM_PROMPT_HYBRID)


# ─── Context formatting ────────────────────────────────────────────────────────

def format_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a readable context block for the LLM.
    Source type labels are included so the LLM can correctly attribute each chunk.
    """
    if not chunks:
        return "No relevant documents found in the knowledge base."

    context_parts = []
    for i, chunk in enumerate(chunks, start=1):
        # Build source label: filename + page + section breadcrumb + source type
        source_type = chunk.get("source_type", "official")
        source_label = "Official Document" if source_type == "official" else "Student Experience"
        if chunk.get("author"):
            source_label += f" ({chunk['author']})"

        source_info = f"[Source {i}: {chunk['filename']}"
        if chunk.get("page_number"):
            source_info += f", Page {chunk['page_number']}"
        if chunk.get("section_path"):
            source_info += f", Section: {chunk['section_path']}"
        elif chunk.get("section_title"):
            source_info += f", Section: {chunk['section_title']}"
        source_info += f", Category: {chunk['category']}, Type: {source_label}]"

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
                # Knowledge Source metadata
                source_type=chunk.get("source_type", "official"),
                author=chunk.get("author"),
            )
        )
    return citations


def run_rag_pipeline(
    query: str,
    conversation_history: list[dict] | None = None,
    knowledge_mode: str = "hybrid",
    conversation_id: int | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    *,
    max_context_chunks: int | None = None,
    top_k_bm25: int | None = None,
    top_k_vector: int | None = None,
    n_query_rewrites: int | None = None,
    use_reranker: bool | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict:
    """
    Full RAG pipeline.

    Args:
        query: User's question
        conversation_history: List of {"role": str, "content": str} dicts
        knowledge_mode: "hybrid" | "official" | "experience"
        conversation_id: ID of the conversation
        session_id: session token of the user
        request_id: Client-side generated request UUID

    Tuning overrides (keyword-only, all optional):
        Each defaults to None, meaning "use the configured env/settings value".
        They exist so an evaluation harness can sweep configurations within a
        single process instead of restarting with a different .env.  Callers
        that pass nothing get exactly the previous behaviour.

        max_context_chunks: Final chunks fed to the LLM (env: MAX_CONTEXT_CHUNKS)
        top_k_bm25: BM25 candidates per query (env: BM25_TOP_K)
        top_k_vector: Vector candidates per query (env: VECTOR_TOP_K)
        n_query_rewrites: Query expansion variants (env: MAX_QUERY_REWRITES);
            pass 0 to skip expansion entirely
        use_reranker: Force the cross-encoder on/off (env: DISABLE_RERANKER)
        temperature: Generation temperature (default 0.3)
        max_tokens: Generation token cap (default 2048)

    Returns:
        {
            "answer": str,
            "sources": list[SourceCitation],
            "retrieved_chunks": int,
            "query_time_ms": float,
            "knowledge_mode": str,
        }
    """
    start_time = time.time()
    history = conversation_history or []

    def emit_stage(stage: str, status: str, error_message: str | None = None):
        if conversation_id is not None and session_id is not None:
            update_progress(
                conversation_id=conversation_id,
                session_id=session_id,
                request_id=request_id,
                stage=stage,
                status=status,
                error_message=error_message,
            )

    # ── Step 1: Query Rewriting ────────────────────────────────────────────────
    logger.info(f"RAG pipeline started for query: {query[:80]}... (mode={knowledge_mode})")
    emit_stage(STAGE_REWRITING, STATUS_IN_PROGRESS)
    try:
        if n_query_rewrites == 0:
            # Explicitly disabled for this call — retrieve on the raw query only.
            rewritten_queries = []
            logger.info("Query rewriting skipped (n_query_rewrites=0)")
        else:
            rewritten_queries = rewrite_query(query, n=n_query_rewrites)
            logger.info(f"Query rewrites: {rewritten_queries}")
    except Exception as e:
        logger.error(f"RAG pipeline failed during query rewriting: {e}")
        emit_stage(STAGE_REWRITING, STATUS_FAILED, "Failed during retrieval")
        raise

    # ── Step 2: Hybrid Retrieval (mode-filtered) & Step 3: Reranking ───────────
    emit_stage(STAGE_RETRIEVING, STATUS_IN_PROGRESS)
    state_tracker = {"active_stage": STAGE_RETRIEVING}

    def on_rerank_start():
        state_tracker["active_stage"] = STAGE_RERANKING
        emit_stage(STAGE_RERANKING, STATUS_IN_PROGRESS)

    try:
        chunks = hybrid_retrieve(
            query=query,
            queries=rewritten_queries,
            top_k_bm25=top_k_bm25,
            top_k_vector=top_k_vector,
            top_k_rerank=max_context_chunks or settings.max_context_chunks,
            knowledge_mode=knowledge_mode,
            on_rerank_start=on_rerank_start,
            use_reranker=use_reranker,
        )
        logger.info(f"Retrieved {len(chunks)} final chunks after reranking (mode={knowledge_mode})")
    except Exception as e:
        logger.error(f"RAG pipeline failed during retrieval/reranking: {e}")
        if state_tracker["active_stage"] == STAGE_RERANKING:
            emit_stage(STAGE_RERANKING, STATUS_FAILED, "Failed during reranking")
        else:
            emit_stage(STAGE_RETRIEVING, STATUS_FAILED, "Failed during retrieval")
        raise

    # ── Step 4: Context Assembly & generating answer ───────────────────────────
    emit_stage(STAGE_GENERATING, STATUS_IN_PROGRESS)
    context = format_context(chunks)
    history_text = format_history(history)

    # ── Fallback LLM Response (mode-aware prompt) ──────────────────────
    system_prompt = _get_system_prompt(knowledge_mode)
    prompt = system_prompt.format(context=context, history=history_text)
    full_prompt = prompt + f"\n\nStudent question: {query}"

    try:
        answer, model_used = llm_orchestrator.generate_with_fallback(
            prompt=full_prompt,
            temperature=0.3 if temperature is None else temperature,
            max_tokens=max_tokens or 2048,
        )
    except Exception as e:
        emit_stage(STAGE_GENERATING, STATUS_FAILED, "Failed during generation")
        if isinstance(e, RagPipelineError):
            raise e
        logger.error(f"LLM generation failed: {e}")
        raise _classify_llm_error(e) from e

    # ── Step 5: Citations ──────────────────────────────────────────────────────
    citations = chunks_to_citations(chunks)

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(f"RAG pipeline completed in {elapsed_ms:.0f}ms")

    emit_stage(STAGE_COMPLETE, STATUS_COMPLETED)

    return {
        "answer": answer,
        "sources": citations,
        "retrieved_chunks": len(chunks),
        "query_time_ms": elapsed_ms,
        "knowledge_mode": knowledge_mode,
        "model_used": model_used,
        # is_error=False signals to the cache layer that this result is safe
        # to store.  The cache checks this flag before every SET operation.
        "is_error": False,
    }
