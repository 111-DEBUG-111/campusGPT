"""
Query Rewriter — Uses Gemini to expand the user's query into multiple variants.

This improves recall by searching with diverse phrasings of the same question.
"""
import logging
import json
import google.generativeai as genai
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_client():
    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(settings.gemini_model)


REWRITE_PROMPT = """You are a search query optimizer for a university knowledge base.

Given a student's question, generate {n} alternative phrasings that:
- Capture the same intent but use different words
- Include both formal and informal versions
- Consider common abbreviations (e.g. "CGPA" vs "grade point average")
- Are concise (under 20 words each)

Return ONLY a JSON array of strings, nothing else.

Original query: "{query}"

Example output:
["What is the minimum attendance required?", "attendance percentage needed to pass", "how many classes can I miss?"]

Your output:"""


def rewrite_query(query: str, n: int | None = None) -> list[str]:
    """
    Generate alternative query phrasings using Gemini.

    Args:
        query: Original user query
        n: Number of rewrites (default: settings.max_query_rewrites)

    Returns:
        List of alternative query strings (may be empty on failure).
    """
    n = n or settings.max_query_rewrites

    try:
        model = _get_client()
        response = model.generate_content(
            REWRITE_PROMPT.format(query=query, n=n),
            generation_config=genai.GenerationConfig(
                temperature=0.3,
                max_output_tokens=512,
            ),
        )
        text = response.text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        rewrites = json.loads(text)
        if isinstance(rewrites, list):
            logger.info(f"Query rewritten into {len(rewrites)} variants")
            return [str(r) for r in rewrites[:n]]

    except Exception as e:
        logger.warning(f"Query rewrite failed (non-fatal): {e}")

    return []  # Graceful fallback — retriever uses original query only
