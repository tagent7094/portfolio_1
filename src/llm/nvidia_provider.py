"""NVIDIA NIM LLM provider (OpenAI-compatible API with reasoning support) with streaming."""

import logging
import sys
from typing import Generator

from .base import LLMProvider
from ..utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)


class NvidiaProvider(LLMProvider):
    """Provider for NVIDIA NIM endpoints (integrate.api.nvidia.com).

    Uses the OpenAI SDK since NVIDIA NIM exposes an OpenAI-compatible API.
    Supports models like nvidia/nemotron-3-super-120b-a12b with optional
    reasoning/thinking mode.
    """

    def __init__(
        self,
        model: str = "nvidia/nemotron-3-super-120b-a12b",
        api_key: str = "",
        base_url: str = "https://integrate.api.nvidia.com/v1",
        enable_thinking: bool = True,
        reasoning_budget: int = 16384,
    ):
        from openai import OpenAI

        self.model = model
        self._provider_name = "nvidia"
        self._model_name = model
        self.enable_thinking = enable_thinking
        self.reasoning_budget = reasoning_budget
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        print(f"\033[36m[LLM:{self.model}]\033[0m generate() prompt={len(prompt)} chars, temp={temperature}, max_tokens={max_tokens}, thinking={self.enable_thinking}", file=sys.stderr, flush=True)
        result = "".join(self.generate_stream(prompt, system_prompt, temperature, max_tokens))
        print(f"\033[36m[LLM:{self.model}]\033[0m \033[32m→ {len(result)} chars generated\033[0m", file=sys.stderr, flush=True)
        return result

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Generator[str, None, None]:
        """Stream tokens from NVIDIA NIM. Prints content to terminal, skips reasoning."""
        print(f"\033[36m[LLM:{self.model}]\033[0m generate_stream() prompt={len(prompt)} chars, temp={temperature}, max_tokens={max_tokens}, thinking={self.enable_thinking}", file=sys.stderr, flush=True)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.95,
            "stream": True,
        }

        if self.enable_thinking:
            kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": True},
                "reasoning_budget": self.reasoning_budget,
            }

        completion = self.client.chat.completions.create(**kwargs)

        for chunk in completion:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # Print reasoning to terminal (dimmed) but don't yield it
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                print(f"\033[2m{reasoning}\033[0m", end="", flush=True, file=sys.stderr)
            # Yield and print actual content
            if delta.content is not None:
                print(delta.content, end="", flush=True, file=sys.stderr)
                yield delta.content

        print("", file=sys.stderr)

    def generate_json(self, prompt: str, system_prompt: str = None) -> dict:
        max_tok = self.max_output_tokens
        print(f"\033[36m[LLM:{self.model}]\033[0m generate_json() prompt={len(prompt)} chars, max_output={max_tok}", file=sys.stderr, flush=True)
        for attempt in range(3):
            if attempt > 0:
                print(f"\033[36m[LLM:{self.model}]\033[0m JSON parse retry attempt {attempt + 1}/3", file=sys.stderr, flush=True)
                prompt_to_use = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No explanatory text."
            else:
                prompt_to_use = prompt
            response = self.generate(prompt_to_use, system_prompt, temperature=0.3, max_tokens=max_tok)
            result = parse_llm_json(response)
            if result is not None and result != {}:
                print(f"\033[36m[LLM:{self.model}]\033[0m \033[32m→ JSON parsed successfully ({len(str(result))} chars)\033[0m", file=sys.stderr, flush=True)
                return result
            logger.warning("JSON parse attempt %d failed, retrying...", attempt + 1)
        print(f"\033[36m[LLM:{self.model}]\033[0m \033[31m→ JSON parse failed after 3 attempts\033[0m", file=sys.stderr, flush=True)
        return {}
