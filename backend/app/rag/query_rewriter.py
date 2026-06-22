"""
Query Rewriter — Uses the LLM Orchestrator (Gemini + Groq fallback) to expand
the user's query into multiple variants.

This improves recall by searching with diverse phrasings of the same question.
"""
import json
import logging
import re

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


REWRITE_PROMPT = """\
You are a search query optimizer for a university knowledge base.

Given a student's question, generate {n} alternative phrasings that:
- Capture the same intent but use different words
- Include both formal and informal versions
- Consider common abbreviations (e.g. "CGPA" vs "grade point average")
- Are concise (under 20 words each)

Return ONLY a JSON array of strings. No explanation, no markdown fences.

Original query: "{query}"

Example output:
["What is the minimum attendance required?", "attendance percentage needed to pass", "how many classes can I miss?"]

Your output:"""


def _extract_json_array(text: str) -> list[str] | None:
    """
    Multi-strategy JSON array extractor — handles:
      • Clean JSON  →  direct parse
      • Wrapped in markdown code fences  →  fence stripper then parse
      • JSON buried inside prose / think blocks  →  regex search
    Returns None if no valid list[str] found.
    """
    # Strategy 1: try as-is (works when response_mime_type forces clean JSON)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(s) for s in parsed]
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown code fences then retry
    # handles ```json ... ``` and ``` ... ```
    fence_stripped = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        parsed = json.loads(fence_stripped)
        if isinstance(parsed, list):
            return [str(s) for s in parsed]
    except json.JSONDecodeError:
        pass

    # Strategy 3: find the first [...] array anywhere in the text
    # (catches prose preamble, <think> blocks, trailing notes, etc.)
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return [str(s) for s in parsed]
        except json.JSONDecodeError:
            pass

    return None


def rewrite_query(query: str, n: int | None = None) -> list[str]:
    """
    Generate alternative query phrasings using Gemini.

    Args:
        query: Original user query
        n: Number of rewrites (default: settings.max_query_rewrites)

    Returns:
        List of alternative query strings (empty list on any failure —
        the retriever falls back gracefully to the original query).
    """
    # Import here to avoid circular imports
    from app.services.llm_service import llm_orchestrator

    n = n or settings.max_query_rewrites

    try:
        raw_response, model_used = llm_orchestrator.generate_with_fallback(
            prompt=REWRITE_PROMPT.format(query=query, n=n),
            temperature=0.3,
            max_tokens=1024,
            response_mime_type="application/json",
        )
        rewrites = _extract_json_array(raw_response)

        if rewrites:
            result = [r for r in rewrites[:n] if isinstance(r, str) and r.strip()]
            logger.info(f"Query rewritten into {len(result)} variants")
            return result

        # Extraction failed — log raw response at DEBUG for debugging
        logger.debug(f"Could not extract JSON array from rewriter response: {raw_response!r}")

    except Exception as e:
        # Non-fatal: the retriever continues with the original query
        logger.debug(f"Query rewrite skipped: {e}")

    return []
