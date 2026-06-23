"""
LLM Service Layer for CampusGPT.
Defines abstract LLM providers, concrete provider classes, and a fallback orchestrator.
"""
import time
import logging
import httpx
from abc import ABC, abstractmethod
from typing import Optional
from google import genai
from google.genai import types

from app.config import get_settings
from app.rag.errors import RagPipelineError

logger = logging.getLogger(__name__)
settings = get_settings()


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    def generate(
        self, prompt: str, temperature: float = 0.3, max_tokens: int = 2048, response_mime_type: Optional[str] = None
    ) -> str:
        """
        Generate content from a text prompt.
        Raises an exception if the provider call fails.
        """
        pass


class GeminiProvider(BaseLLMProvider):
    """Primary LLM provider using Google Gemini 2.5 Flash."""

    def __init__(self):
        self.client = None
        self.model = settings.gemini_model

    def _get_client(self) -> genai.Client:
        if self.client is None:
            self.client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(attempts=1)
                )
            )
        return self.client

    def generate(
        self, prompt: str, temperature: float = 0.3, max_tokens: int = 2048, response_mime_type: Optional[str] = None
    ) -> str:
        client = self._get_client()
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type=response_mime_type,
        )
        # Using generate_content directly since retries/orchestration are managed at the orchestration level
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        if not response.text:
            raise ValueError("Gemini returned an empty response.")
        return response.text.strip()


class GroqProvider(BaseLLMProvider):
    """Fallback LLM provider using Qwen 3 (via Groq API — model: qwen/qwen3-32b)."""

    def __init__(self):
        self.api_key = settings.groq_api_key
        self.model = settings.groq_model
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    def generate(
        self, prompt: str, temperature: float = 0.3, max_tokens: int = 2048, response_mime_type: Optional[str] = None
    ) -> str:
        if not self.api_key:
            raise ValueError("Groq API key is not configured.")

        # Estimate input token count conservatively (3.5 chars per token is a safe heuristic for English/code)
        estimated_input_tokens = int(len(prompt) / 3.5)
        
        # Max TPM budget on Groq free/on-demand tier is 6000.
        # We target 5800 to leave a safe margin for rate limit updates or minor token calculations.
        tpm_budget = 5800
        
        # Allocate a minimum of 256 tokens for model response
        min_response_tokens = 256
        max_allowed_input_tokens = tpm_budget - min_response_tokens
        
        if estimated_input_tokens > max_allowed_input_tokens:
            # Truncate by keeping instructions (first ~40% of allowed characters) 
            # and actual student question/latest conversation context (last ~50% of allowed characters)
            target_chars = int(max_allowed_input_tokens * 3.5)
            keep_start = int(target_chars * 0.4)
            keep_end = int(target_chars * 0.5)
            prompt = (
                prompt[:keep_start]
                + "\n\n... [Context truncated to fit model rate limits] ...\n\n"
                + prompt[-keep_end:]
            )
            estimated_input_tokens = int(len(prompt) / 3.5)
            logger.warning(
                f"Groq prompt truncated to {len(prompt)} characters ({estimated_input_tokens} est. tokens) to stay under TPM rate limit."
            )

        # Adjust max_tokens to ensure payload is within TPM limits
        adjusted_max_tokens = min(max_tokens, tpm_budget - estimated_input_tokens)
        adjusted_max_tokens = max(min_response_tokens, adjusted_max_tokens)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": adjusted_max_tokens,
        }
        if response_mime_type == "application/json":
            payload["response_format"] = {"type": "json_object"}

        # 30-second timeout for fallback APIs
        with httpx.Client(timeout=30.0) as client:
            response = client.post(self.api_url, headers=headers, json=payload)
            if response.status_code >= 400:
                error_body = response.text
                if response.status_code == 400 and "decommissioned" in error_body:
                    raise ValueError(
                        f"Groq model '{self.model}' has been decommissioned. "
                        f"Update GROQ_MODEL in .env to an active model. Response: {error_body}"
                    )
                logger.error(
                    f"Groq API error {response.status_code} for model '{self.model}': {error_body}"
                )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()


def _is_fallback_eligible_error(exc: Exception) -> bool:
    """
    Classify whether an exception from Gemini is eligible for fallback.
    Excludes safety filter blocks.
    Allows fallback on transient errors, quotas, timeouts, and authentication/invalid key errors.
    """
    raw = str(exc).lower()
    
    # Non-eligible exceptions: safety blocks
    if "safety" in raw or "blocked" in raw or "harm" in raw:
        return False

    return True


import re

def _clean_think_tags(text: str) -> str:
    """Removes `<think>...</think>` tags and everything inside them from the model output."""
    # Use re.DOTALL to match across newlines
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip leading/trailing whitespace left over after removal
    return cleaned.strip()


class LLMOrchestrator:
    """Orchestrates LLM generation with fallback policies and structured logging."""

    def __init__(self):
        # Providers are lazily initialized or referenced
        self._providers = {
            "gemini": GeminiProvider(),
            "qwen": GroqProvider(),
        }

    def generate_with_fallback(
        self, prompt: str, temperature: float = 0.3, max_tokens: int = 2048, response_mime_type: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Generate content using the primary model, automatically falling back to Qwen/Groq as needed.
        Returns:
            (answer_text, model_used)
        """
        # --- Step 1: Primary Model (Gemini 2.5 Flash) ---
        try:
            logger.info("Attempting LLM generation with primary model: gemini")
            t0 = time.monotonic()
            answer = self._providers["gemini"].generate(
                prompt, temperature, max_tokens, response_mime_type=response_mime_type
            )
            duration_ms = (time.monotonic() - t0) * 1000
            
            logger.info(
                f"LLM generation successful with gemini in {duration_ms:.1f}ms",
                extra={"model_used": "gemini", "duration_ms": duration_ms}
            )
            return _clean_think_tags(answer), "gemini"
        except Exception as e:
            if not _is_fallback_eligible_error(e):
                logger.error(
                    f"Gemini generation failed with non-fallback error: {e}",
                    extra={"failed_model": "gemini", "error": str(e)}
                )
                raise e

            logger.warning(
                "LLM fallback triggered: Model 'gemini' failed due to transient/quota error. Attempting fallback to model='qwen' via Groq.",
                extra={"failed_model": "gemini", "next_model": "qwen", "reason": str(e)},
                exc_info=True
            )

        # --- Step 2: First Fallback (Qwen 3 via Groq) ---
        try:
            # Check key configuration
            if not settings.groq_api_key:
                logger.warning("Groq API key not configured. Skipping Qwen fallback step.")
                raise ValueError("Groq API key is missing.")

            logger.info("Attempting LLM generation with fallback model: qwen")
            t0 = time.monotonic()
            answer = self._providers["qwen"].generate(
                prompt, temperature, max_tokens, response_mime_type=response_mime_type
            )
            duration_ms = (time.monotonic() - t0) * 1000
            
            logger.info(
                f"LLM generation successful with qwen in {duration_ms:.1f}ms",
                extra={"model_used": "qwen", "duration_ms": duration_ms}
            )
            return _clean_think_tags(answer), "qwen"
        except Exception as e:
            logger.error(
                f"Groq fallback generation failed: {e}. All models in the fallback chain have exhausted attempts.",
                extra={"failed_model": "qwen", "error": str(e)},
                exc_info=True
            )
            # Wrap in clean, user-friendly exception to avoid leaking vendor error details
            raise RagPipelineError(
                "All AI models are currently experiencing high load. Please try again in a few moments.",
                status_code=503,
            )


# Global orchestrator instance
llm_orchestrator = LLMOrchestrator()
