"""API-based LLM provider (Anthropic Claude / OpenAI GPT) with streaming + thinking."""

import logging
import os
import sys
import time
from typing import Generator

from .base import LLMProvider
from ..utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)

_STREAM_DEBUG = os.environ.get("DIGITALDNA_STREAM_DEBUG", "") == "1"

_COST_PER_MTK: dict[str, tuple[float, float]] = {
    "claude-opus-4-6": (15.0, 75.0),
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = _COST_PER_MTK.get(model)
    if not prices:
        return 0.0
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000


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
        self.last_thinking = ""
        self.on_token = None       # callback(text: str) for streaming text tokens
        self.on_thinking = None    # callback(text: str) for streaming thinking tokens

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

        call_thinking = self.enable_thinking if thinking_budget is None else bool(thinking_budget)
        call_effort = effort if effort is not None else self.effort

        thinking_tokens = self._configured_thinking_budget if call_thinking else 0
        effective_max = max_tokens + thinking_tokens

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
            print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m thinking=adaptive, effort={call_effort}, output={max_tokens}+thinking={thinking_tokens}={effective_max}", file=sys.stderr, flush=True)
        else:
            kwargs["temperature"] = temperature

        t0 = time.time()
        thinking_parts = []
        text_len = 0
        input_tokens = output_tokens = 0
        preview_parts = []
        preview_len = 0
        self.last_thinking = ""

        for _attempt in range(2):
            try:
                with self.client.messages.stream(**kwargs) as stream:
                    for event in stream:
                        if not hasattr(event, 'type'):
                            continue
                        if event.type == 'message_start':
                            msg = getattr(event, 'message', None)
                            if msg:
                                u = getattr(msg, 'usage', None)
                                if u:
                                    input_tokens = getattr(u, 'input_tokens', 0) or 0
                        elif event.type == 'content_block_start':
                            block = event.content_block
                            if _STREAM_DEBUG and hasattr(block, 'type'):
                                if block.type == 'thinking':
                                    print("\033[2m[thinking] ", end="", flush=True, file=sys.stderr)
                                elif block.type == 'text':
                                    print("\033[0m", end="", flush=True, file=sys.stderr)
                        elif event.type == 'content_block_delta':
                            delta = event.delta
                            if hasattr(delta, 'type'):
                                if delta.type == 'thinking_delta':
                                    thinking_parts.append(delta.thinking)
                                    if _STREAM_DEBUG:
                                        print(f"\033[2m{delta.thinking}\033[0m", end="", flush=True, file=sys.stderr)
                                    if self.on_thinking:
                                        self.on_thinking(delta.thinking)
                                elif delta.type == 'text_delta':
                                    text_len += len(delta.text)
                                    if preview_len < 200:
                                        preview_parts.append(delta.text)
                                        preview_len += len(delta.text)
                                    if _STREAM_DEBUG:
                                        print(delta.text, end="", flush=True, file=sys.stderr)
                                    if self.on_token:
                                        self.on_token(delta.text)
                                    yield delta.text
                        elif event.type == 'content_block_stop':
                            if _STREAM_DEBUG:
                                print("", file=sys.stderr)
                        elif event.type == 'message_delta':
                            u = getattr(event, 'usage', None)
                            if u:
                                output_tokens = getattr(u, 'output_tokens', 0) or 0
                break
            except Exception as e:
                if _attempt == 0 and call_thinking and getattr(e, 'status_code', None) == 400:
                    print(f"\033[33m[LLM:{self.provider}/{self.model}] thinking not supported, retrying without\033[0m", file=sys.stderr, flush=True)
                    kwargs.pop("thinking", None)
                    kwargs.pop("output_config", None)
                    kwargs["temperature"] = temperature
                    kwargs["max_tokens"] = max_tokens
                    call_thinking = False
                    thinking_parts = []
                    text_len = 0
                    input_tokens = output_tokens = 0
                    preview_parts = []
                    preview_len = 0
                    continue
                print(f"\033[31m[LLM:{self.provider}/{self.model}] API error: {e}\033[0m", file=sys.stderr, flush=True)
                if hasattr(e, 'body'):
                    print(f"\033[31m[LLM:{self.provider}/{self.model}] Error body: {e.body}\033[0m", file=sys.stderr, flush=True)
                raise

        elapsed = time.time() - t0
        self.last_thinking = "".join(thinking_parts)

        log = [f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m \033[32m✓ done in {elapsed:.1f}s\033[0m"]
        if input_tokens or output_tokens:
            log.append(f"tokens: {input_tokens:,} in → {output_tokens:,} out")
            cost = _estimate_cost(self.model, input_tokens, output_tokens)
            if cost > 0:
                log.append(f"~${cost:.3f}")
        log.append(f"thinking: {len(self.last_thinking):,} chars")
        log.append(f"text: {text_len:,} chars")
        print(" │ ".join(log), file=sys.stderr, flush=True)
        preview = "".join(preview_parts)[:200].replace("\n", " ").strip()
        if preview:
            print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m   ↳ {preview!r}{'…' if text_len > 200 else ''}", file=sys.stderr, flush=True)

    def _stream_openai(self, prompt, system_prompt, temperature, max_tokens):
        """Stream from OpenAI-compatible APIs."""
        t0 = time.time()
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

        text_len = 0
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                text_len += len(delta.content)
                if _STREAM_DEBUG:
                    print(delta.content, end="", flush=True, file=sys.stderr)
                if self.on_token:
                    self.on_token(delta.content)
                yield delta.content

        elapsed = time.time() - t0
        print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m \033[32m✓ done in {elapsed:.1f}s\033[0m │ text: {text_len:,} chars", file=sys.stderr, flush=True)

    def generate_with_search(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        max_searches: int = 3,
        allowed_domains: list[str] | None = None,
    ) -> dict:
        """Generate with Anthropic server-side web search. Returns {text, searches[]}."""
        if self.provider != "anthropic":
            return super().generate_with_search(prompt, system_prompt, temperature, max_tokens)

        self._wait_for_rate_limit()
        print(f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m generate_with_search() prompt={len(prompt)} chars, max_searches={max_searches}", file=sys.stderr, flush=True)

        messages = [{"role": "user", "content": prompt}]
        tools = [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": max_searches,
        }]
        if allowed_domains:
            tools[0]["allowed_domains"] = allowed_domains

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": tools,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        call_thinking = self.enable_thinking
        if call_thinking:
            thinking_tokens = self._configured_thinking_budget
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": self.effort}
            kwargs["max_tokens"] = max_tokens + thinking_tokens
        else:
            kwargs["temperature"] = temperature

        t0 = time.time()
        try:
            response = self.client.messages.create(**kwargs)
        except Exception as e:
            if call_thinking and getattr(e, 'status_code', None) == 400:
                print(f"\033[33m[LLM:{self.provider}/{self.model}] thinking not supported, retrying without\033[0m", file=sys.stderr, flush=True)
                kwargs.pop("thinking", None)
                kwargs.pop("output_config", None)
                kwargs["temperature"] = temperature
                kwargs["max_tokens"] = max_tokens
                response = self.client.messages.create(**kwargs)
            else:
                print(f"\033[31m[LLM:{self.provider}/{self.model}] API error: {e}\033[0m", file=sys.stderr, flush=True)
                if hasattr(e, 'body'):
                    print(f"\033[31m[LLM:{self.provider}/{self.model}] Error body: {e.body}\033[0m", file=sys.stderr, flush=True)
                raise

        text_parts = []
        searches = []

        for block in response.content:
            if hasattr(block, "type"):
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "server_tool_use" and block.name == "web_search":
                    searches.append({
                        "query": block.input.get("query", "") if isinstance(block.input, dict) else str(block.input),
                        "tool_use_id": block.id,
                    })
                elif block.type == "web_search_tool_result":
                    results = []
                    if hasattr(block, "content"):
                        for r in block.content:
                            if hasattr(r, "url"):
                                results.append({
                                    "url": getattr(r, "url", ""),
                                    "title": getattr(r, "title", ""),
                                    "page_age": getattr(r, "page_age", ""),
                                })
                    for s in searches:
                        if s.get("tool_use_id") == getattr(block, "tool_use_id", None):
                            s["results"] = results
                            break

        text = "\n".join(text_parts)
        elapsed = time.time() - t0
        usage = getattr(response, 'usage', None)
        in_tok = getattr(usage, 'input_tokens', 0) if usage else 0
        out_tok = getattr(usage, 'output_tokens', 0) if usage else 0
        log = [f"\033[36m[LLM:{self.provider}/{self.model}]\033[0m \033[32m✓ done in {elapsed:.1f}s\033[0m"]
        if in_tok or out_tok:
            log.append(f"tokens: {in_tok:,} in → {out_tok:,} out")
            cost = _estimate_cost(self.model, in_tok, out_tok)
            if cost > 0:
                log.append(f"~${cost:.3f}")
        log.append(f"{len(text)} chars + {len(searches)} web searches")
        print(" │ ".join(log), file=sys.stderr, flush=True)

        self._report_success()
        return {"text": text, "searches": searches}

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
