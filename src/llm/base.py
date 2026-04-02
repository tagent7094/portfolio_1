"""Abstract base class for LLM providers with rate limiting."""

from abc import ABC, abstractmethod
from typing import Generator


class LLMProvider(ABC):

    # Subclasses set these for rate limiting and adaptive sizing
    _provider_name: str = "unknown"
    _model_name: str = "unknown"
    _rate_limiter = None
    _configured_max_tokens: int = 2000  # Set from config in factory

    @property
    def max_output_tokens(self) -> int:
        """Max output tokens this provider supports. Used by generate_json."""
        try:
            from .rate_limiter import get_spec
            spec = get_spec(self._provider_name, self._model_name)
            # Use min of configured max_tokens and provider's hard limit
            return min(self._configured_max_tokens, spec.max_output_tokens)
        except Exception:
            return self._configured_max_tokens

    def _ensure_rate_limiter(self):
        """Lazily create rate limiter on first use."""
        if self._rate_limiter is None:
            from .rate_limiter import get_rate_limiter
            self._rate_limiter = get_rate_limiter(self._provider_name, self._model_name)

    def _wait_for_rate_limit(self):
        """Wait if RPM limit would be exceeded."""
        self._ensure_rate_limiter()
        self._rate_limiter.wait_if_needed()

    def _report_success(self):
        """Report successful request to rate limiter."""
        if self._rate_limiter:
            self._rate_limiter.report_success()

    def _report_429(self):
        """Report 429 error to rate limiter."""
        if self._rate_limiter:
            self._rate_limiter.report_429()

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """Generate text from a prompt. Returns raw string."""
        pass

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Generator[str, None, None]:
        """Stream tokens from a prompt. Yields individual token strings."""
        result = self.generate(prompt, system_prompt, temperature, max_tokens)
        yield result

    @abstractmethod
    def generate_json(self, prompt: str, system_prompt: str = None) -> dict:
        """Generate and parse JSON from a prompt. Handles retries."""
        pass
