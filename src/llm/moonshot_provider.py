"""Moonshot AI (Kimi) LLM provider — OpenAI-compatible wire format.

Dedicated class (not an APIProvider alias) so Kimi-specific features
(builtin $web_search tool, "thinking" mode for K2.5/K2.6, vision input,
file context) can land here without touching Anthropic/OpenAI plumbing.

Default base URL: https://api.moonshot.ai/v1 (international).
For China region: https://api.moonshot.cn/v1 (override via base_url).

Auth: Bearer token from MOONSHOT_API_KEY env var (resolved by factory).

Cost tracking: every generate*/ generate_with_search captures usage
(via OpenAI's `stream_options={"include_usage": True}` for streams, and
`response.usage` for non-stream tool-calling rounds) and computes USD
from the KIMI_PRICING table below. The provider then sets
`last_input_tokens`, `last_output_tokens`, `last_cost_usd` — the same
attributes APIProvider exposes — so the existing BatchTracer cost
aggregator picks Kimi calls up automatically.

References:
  https://platform.kimi.ai/docs/overview
  https://platform.kimi.ai/docs/api/chat#thinking
  https://platform.kimi.ai/docs/api/chat#web-search
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


# ── Pricing (USD per million tokens; input, output) ──────────────────────────
#
# Source: https://platform.kimi.ai/docs/overview (consult page for latest).
# Values are deliberately conservative; if Moonshot bumps prices and we lag,
# our cost tracking under-reports rather than over-reports.
KIMI_PRICING: dict[str, tuple[float, float]] = {
    # K2 lineup (latest reasoning + non-reasoning chat)
    "kimi-k2.6":                 (0.50, 2.00),
    "kimi-k2.5":                 (0.40, 1.60),
    "kimi-k2.5-thinking":        (0.50, 2.00),
    "kimi-k2.5-thinking-turbo":  (0.45, 1.80),
    "kimi-k2-turbo-preview":     (0.45, 1.80),
    "kimi-k2-0905-preview":      (0.60, 2.50),
    "kimi-k2-instruct":          (0.60, 2.50),
    "kimi-latest":               (0.50, 2.00),
    # Legacy moonshot-v1 line (context-tiered)
    "moonshot-v1-8k":            (0.12, 0.36),
    "moonshot-v1-32k":           (0.50, 1.50),
    "moonshot-v1-128k":          (1.20, 1.20),
}

# Models that support extra_body={"thinking": {"type": "enabled"}}.
# Used to decide whether to plumb the thinking kwarg from session.
_THINKING_CAPABLE = {
    "kimi-k2.6",
    "kimi-k2.5",
    "kimi-k2.5-thinking",
    "kimi-k2.5-thinking-turbo",
    "kimi-latest",
}

# Models that accept OpenAI-style image_url content blocks.
_VISION_CAPABLE = {
    "kimi-k2.6",
    "kimi-k2.5",
    "kimi-latest",
}

# Models that REJECT any temperature other than the listed value.
# Moonshot's K2.x reasoning models lock temperature server-side. If we send
# anything else we get a 400 "invalid temperature" before any tokens stream.
# We silently override the temperature and warn once per (model, requested) pair.
_FIXED_TEMPERATURE: dict[str, float] = {
    "kimi-k2.6":                0.6,
    "kimi-k2.5":                0.6,
    "kimi-k2.5-thinking":       0.6,
    "kimi-k2.5-thinking-turbo": 0.6,
    "kimi-latest":              0.6,
}


def _coerce_temperature(model: str, requested: float) -> float:
    """Return the temperature actually safe to send to `model`. Warn-once on override."""
    locked = _FIXED_TEMPERATURE.get(model)
    if locked is None:
        return requested
    if abs(float(requested) - locked) < 1e-6:
        return locked
    seen_key = (model, round(float(requested), 4))
    seen = getattr(_coerce_temperature, "_warned", set())
    if seen_key not in seen:
        logger.warning(
            "[moonshot] %s only accepts temperature=%s; overriding requested %.3f",
            model, locked, requested,
        )
        seen.add(seen_key)
        _coerce_temperature._warned = seen  # type: ignore[attr-defined]
    return locked


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = KIMI_PRICING.get(model)
    if not prices:
        # Warn once per unknown model — keep it noisy enough that drift is
        # visible, but not on every call.
        if not getattr(_estimate_cost, "_warned", set()).__contains__(model):
            logger.warning("[moonshot] no pricing entry for model %r — cost reported as 0", model)
            _estimate_cost._warned = (getattr(_estimate_cost, "_warned", set()) | {model})  # type: ignore[attr-defined]
        return 0.0
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000


class MoonshotProvider(LLMProvider):
    def __init__(
        self,
        model: str = "kimi-k2.6",
        api_key: str = "",
        base_url: str = "https://api.moonshot.ai/v1",
        enable_thinking: bool = False,
        effort: str = "medium",
    ):
        from openai import OpenAI  # Moonshot ships an OpenAI-compatible API.

        self.model = model
        self._provider_name = "kimi"
        self._model_name = model
        self.last_thinking = ""
        # Cost tracker — read by BatchTracer.accumulate_cost.
        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self.last_cost_usd = 0.0
        self.enable_thinking = enable_thinking
        self.effort = effort
        self.on_token = None       # callback(text: str) for streaming text tokens
        self.on_thinking = None    # callback(text: str) — Moonshot doesn't surface thinking tokens mid-stream yet

        if not api_key:
            logger.warning("[moonshot] no api_key passed — calls will 401 unless MOONSHOT_API_KEY is in env")

        self.client = OpenAI(base_url=base_url, api_key=api_key or "missing")

    # ── Internal helpers ──────────────────────────────────────────────────

    def _supports_thinking(self) -> bool:
        return self.model in _THINKING_CAPABLE

    def _thinking_extra_body(
        self,
        *,
        force_disabled: bool = False,
        thinking_budget: int | None = None,
        effort: str | None = None,
    ) -> dict | None:
        """Build the `extra_body={"thinking": ...}` dict per Moonshot's API.

        force_disabled=True is for paths Moonshot says don't compose with
        thinking — notably $web_search on K2.5/K2.6.
        """
        if force_disabled:
            return {"thinking": {"type": "disabled"}}
        if not self._supports_thinking():
            return None
        want_thinking = self.enable_thinking
        # Per-call overrides (rare): if explicit thinking_budget>0 or effort
        # signals "thinking", flip on. effort='low' implies thinking off.
        if thinking_budget is not None and thinking_budget > 0:
            want_thinking = True
        if effort is not None:
            want_thinking = effort.lower() in {"medium", "high"} and self.enable_thinking
        if want_thinking:
            return {"thinking": {"type": "enabled"}}
        return {"thinking": {"type": "disabled"}}

    def _record_usage(self, input_tokens: int, output_tokens: int) -> float:
        """Update last_*_tokens/last_cost_usd and return the cost."""
        self.last_input_tokens = int(input_tokens or 0)
        self.last_output_tokens = int(output_tokens or 0)
        self.last_cost_usd = _estimate_cost(self.model, self.last_input_tokens, self.last_output_tokens)
        return self.last_cost_usd

    def _build_user_content(self, prompt: str, images: list[str] | None) -> list | str:
        """Return either a plain string (text-only) or an OpenAI content-block list
        (text + image_url) for vision-capable models.
        """
        if not images:
            return prompt
        if self.model not in _VISION_CAPABLE:
            logger.warning(
                "[moonshot] model %r is not vision-capable; ignoring %d image(s)",
                self.model, len(images),
            )
            return prompt
        blocks: list[dict] = [{"type": "text", "text": prompt}]
        for img in images:
            blocks.append({"type": "image_url", "image_url": {"url": img}})
        return blocks

    # ── Public API ────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        thinking_budget: int | None = None,
        effort: str | None = None,
        images: list[str] | None = None,
    ) -> str:
        print(
            f"\033[36m[LLM:kimi/{self.model}]\033[0m generate() prompt={len(prompt)} chars, "
            f"temp={temperature}, max_tokens={max_tokens}, thinking={self._supports_thinking() and self.enable_thinking}",
            file=sys.stderr, flush=True,
        )
        result = "".join(self.generate_stream(
            prompt, system_prompt, temperature, max_tokens,
            thinking_budget=thinking_budget, effort=effort, images=images,
        ))
        cost_str = f"~${self.last_cost_usd:.4f}" if self.last_cost_usd else "~$0"
        print(
            f"\033[36m[LLM:kimi/{self.model}]\033[0m \033[32m→ {len(result)} chars generated\033[0m │ "
            f"tokens: {self.last_input_tokens:,} → {self.last_output_tokens:,} │ {cost_str}",
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
        images: list[str] | None = None,
    ) -> Generator[str, None, None]:
        self._wait_for_rate_limit()
        t0 = time.time()
        text_len = 0

        # Reset usage so a partial / failed call doesn't leak last run's numbers.
        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self.last_cost_usd = 0.0

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": self._build_user_content(prompt, images)})

        extra_body = self._thinking_extra_body(thinking_budget=thinking_budget, effort=effort)
        safe_temp = _coerce_temperature(self.model, temperature)
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": safe_temp,
            "max_tokens": max_tokens,
            "stream": True,
            # Asks Moonshot to emit a final chunk carrying token usage stats.
            "stream_options": {"include_usage": True},
        }
        if extra_body:
            kwargs["extra_body"] = extra_body

        try:
            stream = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                self._report_429()
            raise

        usage_input = 0
        usage_output = 0
        for chunk in stream:
            # Usage chunks come last and carry no choices.
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage:
                usage_input = getattr(chunk_usage, "prompt_tokens", 0) or getattr(chunk_usage, "input_tokens", 0) or 0
                usage_output = getattr(chunk_usage, "completion_tokens", 0) or getattr(chunk_usage, "output_tokens", 0) or 0
            if not getattr(chunk, "choices", None):
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

        cost = self._record_usage(usage_input, usage_output)
        elapsed = time.time() - t0
        print(
            f"\033[36m[LLM:kimi/{self.model}]\033[0m \033[32m✓ done in {elapsed:.1f}s\033[0m │ "
            f"tokens: {self.last_input_tokens:,} → {self.last_output_tokens:,} │ "
            f"~${cost:.4f} │ text: {text_len:,} chars",
            file=sys.stderr, flush=True,
        )
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

    def _reformat_search_prose_as_json(self, prose: str) -> str | None:
        """Coerce Kimi's web-search prose output into the standard JSON envelope.

        Callers like `_web_search_enrich` expect:
          {trending_topics: [...], facts: [{fact, source, relevance}], ...}

        Kimi K2.x typically returns prose with markdown bullets. This method
        does ONE follow-up generate() call asking it to reshape what it just
        wrote into JSON. Returns the JSON string on success, None on failure
        (caller falls back to the original prose).
        """
        if not prose or len(prose) < 30:
            return None
        try:
            reformat_prompt = (
                "Reformat the search findings below as a strict JSON object with "
                "this exact shape — no other commentary, no markdown fences in your output:\n\n"
                "{\n"
                '  "trending_topics": ["topic1", "topic2"],\n'
                '  "facts": [{"fact": "...", "source": "...", "relevance": "..."}],\n'
                '  "contrarian_angles": ["angle1"],\n'
                '  "founder_news": [{"headline": "...", "source": "...", "date": "..."}]\n'
                "}\n\n"
                "Use empty arrays for sections with nothing to report. Extract from this prose:\n\n"
                f"---\n{prose[:8000]}\n---"
            )
            # Short call, low max_tokens; cheap on Kimi.
            json_out = self.generate(
                reformat_prompt,
                temperature=0.2,
                max_tokens=2000,
            )
            return json_out
        except Exception as e:
            logger.warning("[moonshot] web-search prose-to-JSON reformat failed: %s", e)
            return None

    def generate_with_search(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        max_searches: int = 3,
        allowed_domains: list[str] | None = None,
    ) -> dict:
        """Generate with Kimi's built-in $web_search tool. Returns {text, searches[]}.

        Per Moonshot: `$web_search` is incompatible with thinking on K2.5/K2.6,
        so this path forces `thinking.type=disabled`.
        """
        self._wait_for_rate_limit()
        t0 = time.time()
        print(
            f"\033[36m[LLM:kimi/{self.model}]\033[0m generate_with_search() "
            f"prompt={len(prompt)} chars, max_searches={max_searches}",
            file=sys.stderr, flush=True,
        )

        # Reset usage tracker for this call.
        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self.last_cost_usd = 0.0

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        tools = [{"type": "builtin_function", "function": {"name": "$web_search"}}]
        searches: list[dict] = []
        rounds = 0
        cum_input = 0
        cum_output = 0

        safe_temp = _coerce_temperature(self.model, temperature)
        while rounds < max_searches + 2:
            rounds += 1
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=safe_temp,
                    max_tokens=max_tokens,
                    tools=tools,
                    extra_body=self._thinking_extra_body(force_disabled=True),
                )
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    self._report_429()
                raise

            usage = getattr(response, "usage", None)
            if usage:
                cum_input += getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0) or 0
                cum_output += getattr(usage, "completion_tokens", 0) or getattr(usage, "output_tokens", 0) or 0

            choice = response.choices[0]
            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message)
                for tc in choice.message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception:
                        args = {}
                    # Store ONLY the user-readable query, never the raw tool
                    # arguments blob (which Moonshot sometimes returns as a
                    # JSON-encoded tool RESULT, not the query the model issued).
                    query_text = ""
                    if isinstance(args, dict):
                        query_text = args.get("query") or args.get("q") or ""
                    searches.append({"query": str(query_text), "tool_call_id": tc.id})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "content": json.dumps(args),
                    })
                continue

            text = choice.message.content or ""

            # Kimi K2.x typically returns prose from the tool loop (markdown
            # bullets, headers) rather than the JSON shape that callers like
            # _web_search_enrich expect. Do one synchronous reformat pass to
            # coerce into the standard {trending_topics, facts, contrarian_angles,
            # founder_news} envelope. Kimi cost is negligible — worth the
            # ~1-2s extra over shipping unparseable prose.
            reformatted = self._reformat_search_prose_as_json(text)
            final_text = reformatted if reformatted else text

            cost = self._record_usage(cum_input, cum_output)
            elapsed = time.time() - t0
            print(
                f"\033[36m[LLM:kimi/{self.model}]\033[0m \033[32m✓ done in {elapsed:.1f}s\033[0m │ "
                f"tokens: {self.last_input_tokens:,} → {self.last_output_tokens:,} │ "
                f"~${cost:.4f} │ {len(final_text)} chars + {len(searches)} web searches",
                file=sys.stderr, flush=True,
            )
            self._report_success()
            return {"text": final_text, "searches": searches}

        cost = self._record_usage(cum_input, cum_output)
        elapsed = time.time() - t0
        logger.warning("[moonshot] web search exhausted %d rounds without final answer", rounds)
        print(
            f"\033[36m[LLM:kimi/{self.model}]\033[0m \033[33m⚠ exhausted rounds in {elapsed:.1f}s\033[0m │ "
            f"tokens: {self.last_input_tokens:,} → {self.last_output_tokens:,} │ ~${cost:.4f} │ "
            f"{len(searches)} searches, no final answer",
            file=sys.stderr, flush=True,
        )
        self._report_success()
        return {"text": "", "searches": searches}
