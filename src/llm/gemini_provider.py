"""Google Gemini LLM provider with streaming."""

import logging
import sys
from typing import Generator

from .base import LLMProvider
from ..utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Provider for Google Gemini models via the OpenAI-compatible API."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        api_key: str = "",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/",
    ):
        from openai import OpenAI

        self.model = model
        self._provider_name = "gemini"
        self._model_name = model
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        print(f"\033[36m[Gemini]\033[0m Initialized model={model} base_url={base_url}", file=sys.stderr, flush=True)

    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        print(f"\033[36m[LLM:gemini/{self.model}]\033[0m generate() prompt={len(prompt)} chars, temp={temperature}, max_tokens={max_tokens}", file=sys.stderr, flush=True)
        result = "".join(self.generate_stream(prompt, system_prompt, temperature, max_tokens))
        print(f"\033[36m[LLM:gemini/{self.model}]\033[0m \033[32m→ {len(result)} chars generated\033[0m", file=sys.stderr, flush=True)
        return result

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Generator[str, None, None]:
        """Stream tokens from Gemini via OpenAI-compatible API."""
        self._wait_for_rate_limit()
        print(f"\033[36m[LLM:gemini/{self.model}]\033[0m generate_stream() prompt={len(prompt)} chars, temp={temperature}, max_tokens={max_tokens}", file=sys.stderr, flush=True)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                print(delta.content, end="", flush=True, file=sys.stderr)
                yield delta.content

        print("", file=sys.stderr)

    def generate_json(self, prompt: str, system_prompt: str = None) -> dict:
        max_tok = self.max_output_tokens
        print(f"\033[36m[LLM:gemini/{self.model}]\033[0m generate_json() prompt={len(prompt)} chars, max_output={max_tok}", file=sys.stderr, flush=True)
        for attempt in range(3):
            if attempt > 0:
                print(f"\033[36m[LLM:gemini/{self.model}]\033[0m JSON parse retry attempt {attempt + 1}/3", file=sys.stderr, flush=True)
                prompt_to_use = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No explanatory text."
            else:
                prompt_to_use = prompt
            response = self.generate(prompt_to_use, system_prompt, temperature=0.3, max_tokens=max_tok)
            result = parse_llm_json(response)
            if result is not None and result != {}:
                print(f"\033[36m[LLM:gemini/{self.model}]\033[0m \033[32m→ JSON parsed successfully ({len(str(result))} chars)\033[0m", file=sys.stderr, flush=True)
                return result
            logger.warning("JSON parse attempt %d failed, retrying...", attempt + 1)
        print(f"\033[36m[LLM:gemini/{self.model}]\033[0m \033[31m→ JSON parse failed after 3 attempts\033[0m", file=sys.stderr, flush=True)
        return {}
