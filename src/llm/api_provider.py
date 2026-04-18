"""API-based LLM provider (Anthropic Claude / OpenAI GPT) with streaming + thinking."""

import logging
import sys
from typing import Generator

from .base import LLMProvider
from ..utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)


class APIProvider(LLMProvider):
    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        enable_thinking: bool = True,
        effort: str = "high",
    ):
        self.provider = provider  # "anthropic" or "openai"
        self.model = model
        self.enable_thinking = enable_thinking
        self.effort = effort
        self._provider_name = provider
        self._model_name = model

        if provider == "anthropic":
            import anthropic
            # Explicitly set base_url to override any env var (ANTHROPIC_BASE_URL)
            self.client = anthropic.Anthropic(
                api_key=api_key,
                base_url="https://api.anthropic.com",
            )
        else:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        thinking_budget: int | None = None,
        effort: str | None = None,
    ) -> str:
        # Resolve per-call overrides: thinking_budget=0 → force disable; None → instance default
        call_thinking = self.enable_thinking if thinking_budget is None else bool(thinking_budget)
        call_effort = effort if effort is not None else self.effort
        print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m generate() prompt={len(prompt)} chars, temp={temperature}, max_tokens={max_tokens}, thinking={call_thinking}, effort={call_effort}", file=sys.stderr, flush=True)
        result = "".join(self.generate_stream(prompt, system_prompt, temperature, max_tokens, thinking_budget, effort))
        print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m \033[32m→ {len(result)} chars generated\033[0m", file=sys.stderr, flush=True)
        return result

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        thinking_budget: int | None = None,
        effort: str | None = None,
    ) -> Generator[str, None, None]:
        """Stream tokens. Prints to terminal in real-time."""
        self._wait_for_rate_limit()
        print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m generate_stream() prompt={len(prompt)} chars, temp={temperature}, max_tokens={max_tokens}", file=sys.stderr, flush=True)
        if self.provider == "anthropic":
            yield from self._stream_anthropic(prompt, system_prompt, temperature, max_tokens, thinking_budget, effort)
        else:
            yield from self._stream_openai(prompt, system_prompt, temperature, max_tokens)

    def _stream_anthropic(self, prompt, system_prompt, temperature, max_tokens, thinking_budget=None, effort=None):
        """Stream from Anthropic with adaptive thinking support."""
        messages = [{"role": "user", "content": prompt}]

        # Per-call override: thinking_budget=0 → disable for this call
        call_thinking = self.enable_thinking if thinking_budget is None else bool(thinking_budget)
        call_effort = effort if effort is not None else self.effort

        # When thinking is enabled, max_tokens covers BOTH thinking + content.
        # Thinking can easily use 2000+ tokens, leaving nothing for content.
        # Solution: bump max_tokens to ensure enough room for actual output.
        if call_thinking:
            # Ensure at least 16K total so thinking gets ~12K and content gets ~4K
            effective_max = max(max_tokens, 16000)
        else:
            effective_max = max_tokens

        kwargs = {
            "model": self.model,
            "max_tokens": effective_max,
            "messages": messages,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if call_thinking:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": call_effort}
            # temperature must be 1 when thinking is enabled
            print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m thinking=adaptive, effort={call_effort}, effective_max_tokens={effective_max}", file=sys.stderr, flush=True)
        else:
            kwargs["temperature"] = temperature

        # Use streaming
        print(f"\033[2m[Anthropic {self.model}] base_url={self.client._base_url} api_key={str(self.client.api_key)[:20]}...\033[0m", file=sys.stderr, flush=True)
        print(f"\033[2m[Anthropic {self.model}] kwargs keys: {list(kwargs.keys())}\033[0m", file=sys.stderr, flush=True)

        with self.client.messages.stream(**kwargs) as stream:
            for event in stream:
                # Handle different event types
                if hasattr(event, 'type'):
                    if event.type == 'content_block_start':
                        block = event.content_block
                        if hasattr(block, 'type'):
                            if block.type == 'thinking':
                                print("\033[2m[thinking] ", end="", flush=True, file=sys.stderr)
                            elif block.type == 'text':
                                print("\033[0m", end="", flush=True, file=sys.stderr)

                    elif event.type == 'content_block_delta':
                        delta = event.delta
                        if hasattr(delta, 'type'):
                            if delta.type == 'thinking_delta':
                                # Print thinking to terminal (dimmed) but don't yield
                                print(f"\033[2m{delta.thinking}\033[0m", end="", flush=True, file=sys.stderr)
                            elif delta.type == 'text_delta':
                                # Yield actual content
                                print(delta.text, end="", flush=True, file=sys.stderr)
                                yield delta.text

                    elif event.type == 'content_block_stop':
                        print("", file=sys.stderr)

        print("", file=sys.stderr)

    def _stream_openai(self, prompt, system_prompt, temperature, max_tokens):
        """Stream from OpenAI-compatible APIs."""
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
        print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m generate_json() prompt={len(prompt)} chars, max_output={max_tok}", file=sys.stderr, flush=True)
        for attempt in range(3):
            if attempt > 0:
                print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m JSON parse retry attempt {attempt + 1}/3", file=sys.stderr, flush=True)
                prompt_to_use = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No explanatory text."
            else:
                prompt_to_use = prompt
            response = self.generate(prompt_to_use, system_prompt, temperature=0.3, max_tokens=max_tok)
            result = parse_llm_json(response)
            if result is not None and result != {}:
                print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m \033[32m→ JSON parsed successfully ({len(str(result))} chars)\033[0m", file=sys.stderr, flush=True)
                return result
            logger.warning("JSON parse attempt %d failed, retrying...", attempt + 1)
        print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m \033[31m→ JSON parse failed after 3 attempts\033[0m", file=sys.stderr, flush=True)
        return {}
