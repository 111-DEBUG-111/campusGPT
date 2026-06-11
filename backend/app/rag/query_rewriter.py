"""
Query Rewriter — Uses Gemini to expand the user's query into multiple variants.

This improves recall by searching with diverse phrasings of the same question.
"""
import json
import logging
import re

import google.generativeai as genai

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_client() -> genai.GenerativeModel:
    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(settings.gemini_model)


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
    n = n or settings.max_query_rewrites

    try:
        model = _get_client()
        response = model.generate_content(
            REWRITE_PROMPT.format(query=query, n=n),
            generation_config=genai.GenerationConfig(
                temperature=0.3,
                # Higher token budget so thinking-mode models don't truncate
                # mid-string. 3 rewrites × ~20 words ≈ 120 tokens; give 4×
                # headroom for thinking overhead.
                max_output_tokens=1024,
                # Force the model to output raw JSON — no prose, no fences
                response_mime_type="application/json",
            ),
        )

        raw = response.text.strip()
        rewrites = _extract_json_array(raw)

        if rewrites:
            result = [r for r in rewrites[:n] if isinstance(r, str) and r.strip()]
            logger.info(f"Query rewritten into {len(result)} variants")
            return result

        # Extraction failed — log raw response at DEBUG for debugging
        logger.debug(f"Could not extract JSON array from rewriter response: {raw!r}")

    except Exception as e:
        # Non-fatal: the retriever continues with the original query
        logger.debug(f"Query rewrite skipped: {e}")

    return []
