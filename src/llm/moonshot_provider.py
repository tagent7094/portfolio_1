"""Moonshot AI (Kimi) LLM provider — OpenAI-compatible wire format.

Dedicated class (not an APIProvider alias) so Kimi-specific features
(tool use, file context, 128k window handling) can land here without
touching Anthropic/OpenAI plumbing.

Models:
  kimi-k2-instruct       — best quality
  moonshot-v1-128k       — 128k context, balanced
  moonshot-v1-32k        — 32k context
  moonshot-v1-8k         — cheapest, short context

Default base URL: https://api.moonshot.ai/v1 (international).
For China region: https://api.moonshot.cn/v1 (override via base_url).

Auth: Bearer token from MOONSHOT_API_KEY env var (resolved by factory).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Generator

from .base import LLMProvider
from ..utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)


class MoonshotProvider(LLMProvider):
    def __init__(
        self,
        model: str = "kimi-k2-instruct",
        api_key: str = "",
        base_url: str = "https://api.moonshot.ai/v1",
    ):
        from openai import OpenAI  # Moonshot ships an OpenAI-compatible API.

        self.model = model
        self._provider_name = "kimi"
        self._model_name = model
        self.last_thinking = ""
        self.on_token = None       # callback(text: str) for streaming text tokens
        self.on_thinking = None    # callback(text: str) — Moonshot doesn't surface thinking yet

        if not api_key:
            logger.warning("[moonshot] no api_key passed — calls will 401 unless MOONSHOT_API_KEY is in env")

        self.client = OpenAI(base_url=base_url, api_key=api_key or "missing")

    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        thinking_budget: int | None = None,  # unsupported; signature parity
        effort: str | None = None,           # unsupported; signature parity
    ) -> str:
        print(
            f"\033[36m[LLM:kimi/{self.model}]\033[0m generate() prompt={len(prompt)} chars, "
            f"temp={temperature}, max_tokens={max_tokens}",
            file=sys.stderr, flush=True,
        )
        result = "".join(self.generate_stream(prompt, system_prompt, temperature, max_tokens))
        print(
            f"\033[36m[LLM:kimi/{self.model}]\033[0m \033[32m→ {len(result)} chars generated\033[0m",
            file=sys.stderr, flush=True,
        )
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
        self._wait_for_rate_limit()
        t0 = time.time()
        text_len = 0
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                self._report_429()
            raise

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                text_len += len(delta.content)
                if self.on_token:
                    try:
                        self.on_token(delta.content)
                    except Exception:
                        pass
                yield delta.content

        elapsed = time.time() - t0
        print(f"\033[36m[LLM:kimi/{self.model}]\033[0m \033[32m✓ done in {elapsed:.1f}s\033[0m │ text: {text_len:,} chars", file=sys.stderr, flush=True)
        self._report_success()

    def generate_json(self, prompt: str, system_prompt: str = None) -> dict:
        max_tok = self.max_output_tokens
        print(
            f"\033[36m[LLM:kimi/{self.model}]\033[0m generate_json() prompt={len(prompt)} chars, "
            f"max_output={max_tok}",
            file=sys.stderr, flush=True,
        )
        for attempt in range(3):
            prompt_to_use = (
                prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No explanatory text."
                if attempt > 0 else prompt
            )
            response = self.generate(prompt_to_use, system_prompt, temperature=0.3, max_tokens=max_tok)
            result = parse_llm_json(response)
            if result is not None and result != {}:
                return result
            logger.warning("[moonshot] JSON parse attempt %d failed, retrying", attempt + 1)
        return {}

    def generate_with_search(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        max_searches: int = 3,
        allowed_domains: list[str] | None = None,
    ) -> dict:
        """Generate with Kimi's built-in $web_search tool. Returns {text, searches[]}."""
        self._wait_for_rate_limit()
        t0 = time.time()
        print(
            f"\033[36m[LLM:kimi/{self.model}]\033[0m generate_with_search() "
            f"prompt={len(prompt)} chars, max_searches={max_searches}",
            file=sys.stderr, flush=True,
        )

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        tools = [{"type": "builtin_function", "function": {"name": "$web_search"}}]
        searches: list[dict] = []
        rounds = 0

        while rounds < max_searches + 2:
            rounds += 1
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    extra_body={"thinking": {"type": "disabled"}},
                )
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    self._report_429()
                raise

            choice = response.choices[0]
            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message)
                for tc in choice.message.tool_calls:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    searches.append({"query": args.get("query", tc.function.arguments or ""), "tool_call_id": tc.id})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "content": json.dumps(args),
                    })
                continue

            text = choice.message.content or ""
            elapsed = time.time() - t0
            print(
                f"\033[36m[LLM:kimi/{self.model}]\033[0m \033[32m✓ done in {elapsed:.1f}s\033[0m │ "
                f"{len(text)} chars + {len(searches)} web searches",
                file=sys.stderr, flush=True,
            )
            self._report_success()
            return {"text": text, "searches": searches}

        text = ""
        elapsed = time.time() - t0
        logger.warning("[moonshot] web search exhausted %d rounds without final answer", rounds)
        print(
            f"\033[36m[LLM:kimi/{self.model}]\033[0m \033[33m⚠ exhausted rounds in {elapsed:.1f}s\033[0m │ "
            f"{len(searches)} searches, no final answer",
            file=sys.stderr, flush=True,
        )
        self._report_success()
        return {"text": text, "searches": searches}
