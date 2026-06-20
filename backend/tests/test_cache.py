"""
Tests for the CampusGPT response cache.

Run with:
    cd backend
    uv run pytest tests/test_cache.py -v
"""
import pytest
from unittest.mock import MagicMock, patch


# ─── Normalization ─────────────────────────────────────────────────────────────

class TestNormalization:
    """Strict normalization: only lowercase + terminal-punctuation strip + whitespace collapse."""

    def _norm(self, query: str) -> str:
        from app.cache.response_cache import _normalize_query
        return _normalize_query(query)

    def test_lowercase(self):
        assert self._norm("What is the Attendance Policy") == "what is the attendance policy"

    def test_strips_trailing_question_mark(self):
        assert self._norm("What is the attendance policy?") == "what is the attendance policy"

    def test_strips_trailing_exclamation(self):
        assert self._norm("Tell me now!") == "tell me now"

    def test_strips_trailing_period(self):
        assert self._norm("What is the attendance policy.") == "what is the attendance policy"

    def test_collapses_internal_whitespace(self):
        assert self._norm("what  is   the    policy") == "what is the policy"

    def test_same_query_different_case_same_key(self):
        assert self._norm("What is the attendance policy?") == self._norm("what is the attendance policy")

    def test_different_words_different_key(self):
        """Different questions MUST produce different normalized forms."""
        a = self._norm("What is the attendance policy?")
        b = self._norm("Explain attendance requirements")
        assert a != b, "Different queries must not collide"

    def test_no_stop_word_removal(self):
        """Stop words are NOT removed — preserves query specificity."""
        result = self._norm("what is the policy?")
        assert "what" in result
        assert "is" in result
        assert "the" in result

    def test_no_word_reordering(self):
        """Words are NOT sorted — order matters for meaning."""
        assert self._norm("exam attendance policy") != self._norm("policy attendance exam")

    def test_internal_punctuation_preserved(self):
        """Only TERMINAL punctuation is stripped, not internal."""
        assert self._norm("GPA: 3.0 or higher?") == "gpa: 3.0 or higher"


# ─── Cache Key ─────────────────────────────────────────────────────────────────

class TestCacheKey:
    def _key(self, query: str, kb_version: int) -> str:
        from app.cache.response_cache import make_cache_key
        return make_cache_key(query, kb_version)

    def test_same_query_same_version_same_key(self):
        assert self._key("attendance policy", 5) == self._key("attendance policy", 5)

    def test_same_query_different_version_different_key(self):
        """KB version change must produce a new key → old entry unreachable."""
        assert self._key("attendance policy", 5) != self._key("attendance policy", 6)

    def test_different_query_same_version_different_key(self):
        assert self._key("attendance policy", 5) != self._key("exam policy", 5)

    def test_key_has_prefix(self):
        key = self._key("test", 1)
        assert key.startswith("campusgpt:response:")

    def test_trailing_punctuation_ignored_in_key(self):
        """'policy?' and 'policy' must hash to the same key."""
        assert self._key("What is the attendance policy?", 3) == self._key(
            "What is the attendance policy", 3
        )


# ─── Cache Eligibility ─────────────────────────────────────────────────────────

class TestIsCacheable:
    def _check(self, **kwargs) -> bool:
        from app.cache.response_cache import is_cacheable
        defaults = {
            "is_error": False,
            "answer": "The attendance policy requires 75% attendance. " * 3,
            "retrieved_chunks": 3,
            "sources": [],
            "query_time_ms": 1200.0,
        }
        defaults.update(kwargs)
        return is_cacheable(defaults)

    def test_valid_result_is_cacheable(self):
        assert self._check() is True

    def test_error_flag_blocks_cache(self):
        assert self._check(is_error=True) is False

    def test_missing_is_error_defaults_to_block(self):
        """Absence of is_error flag is treated as an error (safe default)."""
        from app.cache.response_cache import is_cacheable
        result = {"answer": "x" * 100, "retrieved_chunks": 2, "sources": []}
        # is_error key missing → result.get("is_error", True) → True → not cacheable
        assert is_cacheable(result) is False

    def test_empty_answer_blocks_cache(self):
        assert self._check(answer="") is False

    def test_short_answer_blocks_cache(self):
        assert self._check(answer="Too short.") is False

    def test_zero_retrieved_chunks_blocks_cache(self):
        assert self._check(retrieved_chunks=0) is False

    def test_fallback_prefix_blocks_cache(self):
        assert self._check(answer="I'm having trouble generating a response right now.") is False

    def test_another_fallback_prefix_blocks_cache(self):
        assert self._check(answer="Sorry, I couldn't find relevant information.") is False


# ─── KB Version ────────────────────────────────────────────────────────────────

class TestKBVersion:
    def test_get_kb_version_returns_zero_when_redis_unavailable(self):
        with patch("app.cache.kb_version.get_redis", return_value=None):
            from app.cache import kb_version as kv_module
            # Clear any cached module state
            result = kv_module.get_kb_version()
            assert result == 0

    def test_bump_kb_version_returns_zero_when_redis_unavailable(self):
        with patch("app.cache.kb_version.get_redis", return_value=None):
            from app.cache import kb_version as kv_module
            result = kv_module.bump_kb_version()
            assert result == 0

    def test_bump_kb_version_calls_incr(self):
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 7
        with patch("app.cache.kb_version.get_redis", return_value=mock_redis):
            from app.cache import kb_version as kv_module
            result = kv_module.bump_kb_version()
        mock_redis.incr.assert_called_once_with("campusgpt:kb_version")
        assert result == 7

    def test_get_kb_version_initialises_to_1_when_key_missing(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # Key does not exist yet
        with patch("app.cache.kb_version.get_redis", return_value=mock_redis):
            from app.cache import kb_version as kv_module
            result = kv_module.get_kb_version()
        mock_redis.set.assert_called_once_with("campusgpt:kb_version", 1)
        assert result == 1


# ─── Cache Get / Set (integration with mocked Redis) ──────────────────────────

class TestCacheGetSet:
    """Test the get/set functions using a fully mocked Redis client."""

    def _make_result(self, answer: str = None) -> dict:
        text = answer or ("The attendance policy requires 75% attendance. " * 3)
        return {
            "is_error": False,
            "answer": text,
            "sources": [],
            "retrieved_chunks": 3,
            "query_time_ms": 1234.5,
        }

    def test_get_returns_none_when_redis_unavailable(self):
        with patch("app.cache.response_cache.get_redis", return_value=None):
            from app.cache.response_cache import get_cached_response
            assert get_cached_response("test query") is None

    def test_get_returns_none_on_cache_miss(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with (
            patch("app.cache.response_cache.get_redis", return_value=mock_redis),
            patch("app.cache.response_cache.get_kb_version", return_value=5),
        ):
            from app.cache.response_cache import get_cached_response
            assert get_cached_response("attendance policy") is None

    def test_get_returns_decoded_payload_on_hit(self):
        import json
        payload = {"answer": "75% required", "sources": [], "retrieved_chunks": 2}
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(payload)
        with (
            patch("app.cache.response_cache.get_redis", return_value=mock_redis),
            patch("app.cache.response_cache.get_kb_version", return_value=5),
        ):
            from app.cache.response_cache import get_cached_response
            result = get_cached_response("attendance policy")
        assert result is not None
        assert result["answer"] == "75% required"

    def test_set_calls_redis_set_with_ttl(self):
        mock_redis = MagicMock()
        with (
            patch("app.cache.response_cache.get_redis", return_value=mock_redis),
            patch("app.cache.response_cache.get_kb_version", return_value=3),
        ):
            from app.cache.response_cache import set_cached_response
            set_cached_response("attendance policy?", self._make_result())
        assert mock_redis.set.called
        call_kwargs = mock_redis.set.call_args
        # TTL should be passed as ex= argument
        assert call_kwargs.kwargs.get("ex") is not None or len(call_kwargs.args) >= 3

    def test_set_skipped_when_cache_disabled(self):
        mock_redis = MagicMock()
        with (
            patch("app.cache.response_cache.get_redis", return_value=mock_redis),
            patch("app.cache.response_cache.get_kb_version", return_value=1),
            patch("app.cache.response_cache.settings") as mock_settings,
        ):
            mock_settings.cache_enabled = False
            mock_settings.cache_ttl_seconds = 86400
            from app.cache.response_cache import set_cached_response
            set_cached_response("test", self._make_result())
        mock_redis.set.assert_not_called()

    def test_get_returns_none_when_cache_disabled(self):
        mock_redis = MagicMock()
        with (
            patch("app.cache.response_cache.get_redis", return_value=mock_redis),
            patch("app.cache.response_cache.settings") as mock_settings,
        ):
            mock_settings.cache_enabled = False
            from app.cache.response_cache import get_cached_response
            result = get_cached_response("test")
        assert result is None
        mock_redis.get.assert_not_called()

    def test_redis_error_on_get_returns_none(self):
        """Redis errors during GET must fail-open (return None, not raise)."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("Connection refused")
        with (
            patch("app.cache.response_cache.get_redis", return_value=mock_redis),
            patch("app.cache.response_cache.get_kb_version", return_value=1),
        ):
            from app.cache.response_cache import get_cached_response
            result = get_cached_response("test")
        assert result is None  # Must not raise

    def test_redis_error_on_set_is_silent(self):
        """Redis errors during SET must fail-open (no exception propagated)."""
        mock_redis = MagicMock()
        mock_redis.set.side_effect = Exception("Connection refused")
        with (
            patch("app.cache.response_cache.get_redis", return_value=mock_redis),
            patch("app.cache.response_cache.get_kb_version", return_value=1),
        ):
            from app.cache.response_cache import set_cached_response
            # Must not raise
            set_cached_response("test", self._make_result())
