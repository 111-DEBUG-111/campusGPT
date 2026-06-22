import unittest
from unittest.mock import MagicMock, patch
from app.services.llm_service import (
    LLMOrchestrator,
    _is_fallback_eligible_error,
    GeminiProvider,
    GroqProvider
)
from app.rag.errors import RagPipelineError


class TestLLMFallback(unittest.TestCase):

    def test_is_fallback_eligible_error(self):
        # Eligible errors
        self.assertTrue(_is_fallback_eligible_error(Exception("429 rate limit exceeded")))
        self.assertTrue(_is_fallback_eligible_error(Exception("GenerateRequestsPerDay quota exceeded")))
        self.assertTrue(_is_fallback_eligible_error(Exception("503 Service Unavailable")))
        self.assertTrue(_is_fallback_eligible_error(Exception("Connection timed out")))
        self.assertTrue(_is_fallback_eligible_error(Exception("Deadline exceeded")))
        
        # Non-eligible errors (safety blocks)
        self.assertFalse(_is_fallback_eligible_error(Exception("Your request was blocked by the AI safety filter")))
        
        # Eligible errors (authentication/invalid key errors should fallback)
        self.assertTrue(_is_fallback_eligible_error(Exception("401 Unauthorized - API key invalid")))
        self.assertTrue(_is_fallback_eligible_error(Exception("403 Forbidden - access denied")))

    @patch("app.services.llm_service.settings")
    def test_happy_path_gemini_succeeds(self, mock_settings):
        # Setup settings to have keys
        mock_settings.gemini_api_key = "gemini-key"
        mock_settings.groq_api_key = "groq-key"
        mock_settings.gemini_model = "gemini-2.5-flash"
        mock_settings.groq_model = "qwen/qwen3-32b"

        orchestrator = LLMOrchestrator()
        orchestrator._providers["gemini"] = MagicMock(spec=GeminiProvider)
        orchestrator._providers["qwen"] = MagicMock(spec=GroqProvider)

        # Gemini succeeds
        orchestrator._providers["gemini"].generate.return_value = "Gemini answer"

        ans, model = orchestrator.generate_with_fallback("test prompt")
        
        self.assertEqual(ans, "Gemini answer")
        self.assertEqual(model, "gemini")
        orchestrator._providers["gemini"].generate.assert_called_once()
        orchestrator._providers["qwen"].generate.assert_not_called()

    @patch("app.services.llm_service.settings")
    def test_gemini_fails_transient_fallback_to_qwen(self, mock_settings):
        mock_settings.gemini_api_key = "gemini-key"
        mock_settings.groq_api_key = "groq-key"
        mock_settings.gemini_model = "gemini-2.5-flash"
        mock_settings.groq_model = "qwen/qwen3-32b"

        orchestrator = LLMOrchestrator()
        orchestrator._providers["gemini"] = MagicMock(spec=GeminiProvider)
        orchestrator._providers["qwen"] = MagicMock(spec=GroqProvider)

        # Gemini fails with 429, Qwen succeeds
        orchestrator._providers["gemini"].generate.side_effect = Exception("HTTP 429 Too Many Requests")
        orchestrator._providers["qwen"].generate.return_value = "Qwen answer"

        ans, model = orchestrator.generate_with_fallback("test prompt")

        self.assertEqual(ans, "Qwen answer")
        self.assertEqual(model, "qwen")
        orchestrator._providers["gemini"].generate.assert_called_once()
        orchestrator._providers["qwen"].generate.assert_called_once()

    @patch("app.services.llm_service.settings")
    def test_all_fail_graceful_error(self, mock_settings):
        mock_settings.gemini_api_key = "gemini-key"
        mock_settings.groq_api_key = "groq-key"
        mock_settings.gemini_model = "gemini-2.5-flash"
        mock_settings.groq_model = "qwen/qwen3-32b"

        orchestrator = LLMOrchestrator()
        orchestrator._providers["gemini"] = MagicMock(spec=GeminiProvider)
        orchestrator._providers["qwen"] = MagicMock(spec=GroqProvider)

        # All providers fail
        orchestrator._providers["gemini"].generate.side_effect = Exception("HTTP 429 Too Many Requests")
        orchestrator._providers["qwen"].generate.side_effect = Exception("Groq error")

        with self.assertRaises(RagPipelineError) as exc_info:
            orchestrator.generate_with_fallback("test prompt")

        self.assertEqual(exc_info.exception.status_code, 503)
        self.assertIn("All AI models are currently experiencing high load", exc_info.exception.user_message)

    @patch("app.services.llm_service.settings")
    def test_gemini_fails_safety_no_fallback(self, mock_settings):
        mock_settings.gemini_api_key = "gemini-key"
        mock_settings.groq_api_key = "groq-key"

        orchestrator = LLMOrchestrator()
        orchestrator._providers["gemini"] = MagicMock(spec=GeminiProvider)
        orchestrator._providers["qwen"] = MagicMock(spec=GroqProvider)

        # Gemini fails with a safety error (non-transient)
        orchestrator._providers["gemini"].generate.side_effect = Exception("Safety block triggered - HARM_CATEGORY_HARASSMENT")

        with self.assertRaises(Exception) as exc_info:
            orchestrator.generate_with_fallback("test prompt")

        self.assertIn("Safety block triggered", str(exc_info.exception))
        orchestrator._providers["gemini"].generate.assert_called_once()
        orchestrator._providers["qwen"].generate.assert_not_called()

    @patch("app.services.llm_service.settings")
    def test_strip_thinking_tags(self, mock_settings):
        mock_settings.gemini_api_key = "gemini-key"
        mock_settings.groq_api_key = "groq-key"

        orchestrator = LLMOrchestrator()
        orchestrator._providers["gemini"] = MagicMock(spec=GeminiProvider)

        # Gemini returns response with <think> tag
        orchestrator._providers["gemini"].generate.return_value = (
            "<think> Some deep reasoning trace here\nwith newlines </think>\n\nThis is the actual answer."
        )

        ans, model = orchestrator.generate_with_fallback("test prompt")
        self.assertEqual(ans, "This is the actual answer.")
        self.assertEqual(model, "gemini")


