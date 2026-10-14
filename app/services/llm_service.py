"""LLM provider abstraction and implementations for RAG answer generation."""

from abc import ABC, abstractmethod
import time
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings
from app.core.errors import AppException
from app.models.rag import LLMResponse
from app.services.base import BaseService


class BaseLLMProvider(ABC):
    """Abstract interface for LLM completions."""

    @abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate text completion from system and user prompts."""
        pass


class GeminiLLMProvider(BaseLLMProvider):
    """Google Gemini completion provider using the official REST endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.timeout = timeout or settings.LLM_REQUEST_TIMEOUT_SECONDS

        if not self.api_key:
            raise AppException(
                message="GEMINI_API_KEY is not configured.",
                error_code="CONFIG_ERROR",
            )

    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
            f"?key={self.api_key}"
        )

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)

            if response.status_code != 200:
                # Do not leak API key in error message
                error_detail = response.json().get("error", {}).get("message", response.text)
                raise AppException(
                    message=f"Gemini API error ({response.status_code}): {error_detail}",
                    error_code="LLM_API_ERROR",
                )

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise AppException(
                    message="Gemini API returned no completion candidates.",
                    error_code="LLM_EMPTY_RESPONSE",
                )

            candidate = candidates[0]
            parts = candidate.get("content", {}).get("parts", [])
            content_text = "".join(p.get("text", "") for p in parts if "text" in p).strip()

            usage_meta = data.get("usageMetadata", {})
            usage = {
                "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                "total_tokens": usage_meta.get("totalTokenCount", 0),
            }

            return LLMResponse(
                content=content_text,
                model=self.model_name,
                usage=usage,
            )

        except httpx.TimeoutException:
            raise AppException(
                message=f"Gemini API request timed out after {self.timeout}s.",
                error_code="LLM_TIMEOUT",
            )
        except httpx.RequestError as exc:
            raise AppException(
                message=f"Network error communicating with Gemini API: {str(exc)}",
                error_code="LLM_NETWORK_ERROR",
            )


class OpenAILLMProvider(BaseLLMProvider):
    """OpenAI or OpenAI-compatible completion provider (vLLM, Ollama, Groq)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model_name = model_name or settings.OPENAI_MODEL
        self.base_url = (base_url or settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout or settings.LLM_REQUEST_TIMEOUT_SECONDS

        if not self.api_key and not self.base_url.startswith("http://localhost"):
            raise AppException(
                message="OPENAI_API_KEY is not configured.",
                error_code="CONFIG_ERROR",
            )

    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key or 'no-key'}",
        }

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)

            if response.status_code != 200:
                error_detail = response.json().get("error", {}).get("message", response.text)
                raise AppException(
                    message=f"OpenAI API error ({response.status_code}): {error_detail}",
                    error_code="LLM_API_ERROR",
                )

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise AppException(
                    message="OpenAI API returned no completion choices.",
                    error_code="LLM_EMPTY_RESPONSE",
                )

            content_text = choices[0].get("message", {}).get("content", "").strip()
            usage_data = data.get("usage", {})

            return LLMResponse(
                content=content_text,
                model=self.model_name,
                usage={
                    "prompt_tokens": usage_data.get("prompt_tokens", 0),
                    "completion_tokens": usage_data.get("completion_tokens", 0),
                    "total_tokens": usage_data.get("total_tokens", 0),
                },
            )

        except httpx.TimeoutException:
            raise AppException(
                message=f"OpenAI API request timed out after {self.timeout}s.",
                error_code="LLM_TIMEOUT",
            )
        except httpx.RequestError as exc:
            raise AppException(
                message=f"Network error communicating with OpenAI API: {str(exc)}",
                error_code="LLM_NETWORK_ERROR",
            )


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM provider for unit tests, offline development, and zero-cost verification."""

    def __init__(self, fixed_response: Optional[str] = None, model_name: str = "mock-temple-llm") -> None:
        self.fixed_response = fixed_response
        self.model_name = model_name
        self.last_system_prompt: Optional[str] = None
        self.last_user_prompt: Optional[str] = None

    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt

        if self.fixed_response:
            content = self.fixed_response
        elif "NO RELEVANT CONTEXT" in user_prompt or "No matching temple records" in user_prompt:
            content = (
                "I apologize, but this information is not available in the current temple records. "
                "Please consult the temple administration office or the official inquiry counter for assistance."
            )
        else:
            # Deterministic, grounded mock generation based on context snippet
            content = (
                "Based on the temple records provided, here is the information regarding your inquiry. "
                "The rituals and timings follow traditional temple schedules as established."
            )

        return LLMResponse(
            content=content,
            model=self.model_name,
            usage={"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
        )


class LLMService(BaseService):
    """Service orchestrating LLM completions with swappable providers."""

    def __init__(self, provider: Optional[BaseLLMProvider] = None) -> None:
        super().__init__()
        self._provider = provider or self._create_configured_provider()

    @property
    def provider(self) -> BaseLLMProvider:
        """Active LLM provider instance."""
        return self._provider

    def set_provider(self, provider: BaseLLMProvider) -> None:
        """Dynamically replace LLM provider (useful for testing or multi-model routing)."""
        self._provider = provider

    async def generate_answer(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Generate completion using configured provider."""
        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        tokens = max_tokens if max_tokens is not None else settings.LLM_MAX_OUTPUT_TOKENS

        self.logger.debug("Generating LLM completion with model: %s", getattr(self._provider, "model_name", "unknown"))
        return await self._provider.generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temp,
            max_tokens=tokens,
        )

    def _create_configured_provider(self) -> BaseLLMProvider:
        """Instantiate configured provider based on settings."""
        provider_name = (settings.LLM_PROVIDER or "gemini").lower().strip()

        if provider_name == "gemini":
            if settings.GEMINI_API_KEY:
                return GeminiLLMProvider()
            elif settings.ENVIRONMENT in ("testing", "development"):
                self.logger.warning(
                    "GEMINI_API_KEY is not set. Defaulting to MockLLMProvider for %s environment.",
                    settings.ENVIRONMENT,
                )
                return MockLLMProvider()
            else:
                raise AppException(
                    message="GEMINI_API_KEY is required in production environment.",
                    error_code="CONFIG_ERROR",
                )

        elif provider_name == "openai":
            if settings.OPENAI_API_KEY or (settings.OPENAI_BASE_URL and "localhost" in settings.OPENAI_BASE_URL):
                return OpenAILLMProvider()
            elif settings.ENVIRONMENT in ("testing", "development"):
                self.logger.warning(
                    "OPENAI_API_KEY is not set. Defaulting to MockLLMProvider for %s environment.",
                    settings.ENVIRONMENT,
                )
                return MockLLMProvider()
            else:
                raise AppException(
                    message="OPENAI_API_KEY is required in production environment.",
                    error_code="CONFIG_ERROR",
                )

        elif provider_name == "mock":
            return MockLLMProvider()

        else:
            raise AppException(
                message=f"Unsupported LLM_PROVIDER: '{provider_name}'. Supported options are 'gemini', 'openai', 'mock'.",
                error_code="CONFIG_ERROR",
            )


# Global singleton instance
llm_service = LLMService()
