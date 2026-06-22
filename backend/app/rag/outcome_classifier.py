"""
Outcome Classifier — Labels chat responses for admin knowledge-gap tracking.

Classifies each query/answer pair as:
  - answered       — substantive university answer provided
  - knowledge_gap  — on-topic but KB lacked enough specific information
  - off_topic      — not about university/campus life

Uses the LLMOrchestrator so Gemini → Groq fallback applies here too.
"""
import json
import logging
import re

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_VALID_OUTCOMES = frozenset({"answered", "knowledge_gap", "off_topic"})

_OFF_TOPIC_PHRASES = (
    "only respond to university",
    "only answer university",
    "outside the university context",
    "outside of university",
    "campus-related questions",
    "university-related queries",
    "not related to university",
    "focus on university",
    "stick to university",
    "campus topics",
)

_KNOWLEDGE_GAP_PHRASES = (
    "don't specify",
    "doesn't specify",
    "do not specify",
    "does not specify",
    "don't contain",
    "doesn't contain",
    "do not contain",
    "does not contain",
    "not available in",
    "not available in the",
    "not available in official",
    "no specific information",
    "doesn't have enough information",
    "don't have enough information",
    "does not have enough",
    "do not have enough",
    "not contain enough information",
    "doesn't include",
    "do not include",
    "does not include",
    "provided documents don't",
    "provided documents do not",
    "however, the provided documents",
    "however, the documents",
    "unfortunately, the university documents",
    "unfortunately, the documents",
    "i'd recommend checking",
    "i'd recommend contacting",
    "recommend checking with",
    "recommend contacting",
    "for the most current information",
    "for the most accurate",
    "check with your program",
    "international relations office",
    "accounts/finance department",
    "contact the accounts",
    "contacting the accounts",
    "admissions portal",
)

_CLASSIFY_PROMPT = """\
You are classifying CampusGPT chat outcomes for an admin dashboard.

Given a student question and CampusGPT's answer, classify the outcome as exactly one of:

- "answered": The platform fully answered the student's specific question using the knowledge base.
- "knowledge_gap": The question IS about university/campus topics BUT the answer could NOT fully answer the student's specific question. Use this when the answer admits missing details, gives only tangentially related info, or tells the student to contact a department / check elsewhere. Partial related context that does NOT answer the exact question still counts as knowledge_gap.
- "off_topic": The question is NOT about university/campus life. The assistant declined or redirected the user.

Student question: "{query}"

CampusGPT answer: "{answer}"

Chunks retrieved from knowledge base: {retrieved_chunks}

Return ONLY JSON: {{"outcome": "answered" | "knowledge_gap" | "off_topic"}}
"""


def heuristic_outcome(query: str, answer: str) -> str | None:
    """
    Fast phrase-based classification for common patterns.
    Returns None when heuristics are inconclusive.
    """
    answer_lower = answer.lower()

    if any(phrase in answer_lower for phrase in _OFF_TOPIC_PHRASES):
        return "off_topic"

    if any(phrase in answer_lower for phrase in _KNOWLEDGE_GAP_PHRASES):
        return "knowledge_gap"

    return None


def _extract_outcome(text: str) -> str | None:
    """Parse outcome from classifier JSON response."""
    if not text:
        return None

    stripped = text.strip()

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            outcome = str(parsed.get("outcome", "")).strip().lower()
            if outcome in _VALID_OUTCOMES:
                return outcome
    except json.JSONDecodeError:
        pass

    fence_stripped = re.sub(r"```(?:json)?\s*|\s*```", "", stripped).strip()
    try:
        parsed = json.loads(fence_stripped)
        if isinstance(parsed, dict):
            outcome = str(parsed.get("outcome", "")).strip().lower()
            if outcome in _VALID_OUTCOMES:
                return outcome
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{[^{}]*"outcome"\s*:\s*"([^"]+)"[^{}]*\}', stripped, re.DOTALL)
    if match:
        outcome = match.group(1).strip().lower()
        if outcome in _VALID_OUTCOMES:
            return outcome

    return None


def classify_query_outcome(query: str, answer: str, retrieved_chunks: int) -> str:
    """
    Classify a chat outcome using heuristics first, then the LLM orchestrator
    (Gemini with automatic Groq fallback).

    Returns one of: "answered", "knowledge_gap", "off_topic".
    Defaults to "answered" on any failure (fail-safe).
    """
    heuristic = heuristic_outcome(query, answer)
    if heuristic is not None:
        logger.info(
            "Outcome classified via heuristic as %s for query: %s...",
            heuristic,
            query[:60],
        )
        return heuristic

    # Import here to avoid circular imports at module level
    from app.services.llm_service import llm_orchestrator

    query_snip = query[:500]
    answer_snip = answer[:1500]

    try:
        raw, model_used = llm_orchestrator.generate_with_fallback(
            prompt=_CLASSIFY_PROMPT.format(
                query=query_snip.replace('"', "'"),
                answer=answer_snip.replace('"', "'"),
                retrieved_chunks=retrieved_chunks,
            ),
            temperature=0.0,
            max_tokens=256,
            response_mime_type="application/json",
        )
        outcome = _extract_outcome(raw)
        if outcome:
            logger.info(
                "Outcome classified via LLM (%s) as %s for query: %s...",
                model_used,
                outcome,
                query[:60],
            )
            return outcome
        logger.warning("Could not parse outcome from classifier response: %r", raw[:200])
    except Exception as e:
        logger.warning("Outcome classification failed: %s", e)

    return "answered"
