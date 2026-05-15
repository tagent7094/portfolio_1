"""One-shot provider/model connectivity test used by the admin/founder UI.

The Test button fires `POST /api/admin/models/test` (or the founder variant)
which calls into `quick_test()` here. We spin up the provider with the
requested config and ask it for a 5-token "OK" reply — that confirms both
the API key and the model identifier work without burning much budget.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .factory import PROVIDER_DEFAULTS

logger = logging.getLogger(__name__)


_TEST_PROMPT = "Reply with exactly the two characters: OK"


def _build_provider(provider: str, model: str, api_key: str, base_url: str):
    """Mirror task_router._instance_for but without caching."""
    if provider == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider(model=model, base_url=base_url)
    if provider == "lmstudio":
        from .lmstudio_provider import LMStudioProvider
        return LMStudioProvider(model=model, base_url=base_url)
    if provider == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider(model=model, api_key=api_key, base_url=base_url)
    if provider == "nvidia":
        from .nvidia_provider import NvidiaProvider
        return NvidiaProvider(model=model, api_key=api_key, base_url=base_url)
    if provider == "openrouter":
        from .openrouter_provider import OpenRouterProvider
        return OpenRouterProvider(model=model, api_key=api_key, base_url=base_url)
    if provider == "kimi":
        from .moonshot_provider import MoonshotProvider
        return MoonshotProvider(model=model, api_key=api_key, base_url=base_url)
    if provider in ("anthropic", "openai"):
        from .api_provider import APIProvider
        return APIProvider(provider=provider, model=model, api_key=api_key, enable_thinking=False, effort="low")
    raise ValueError(f"unknown provider: {provider!r}")


def quick_test(
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_seconds: float = 15.0,
) -> dict:
    """Issue a tiny "respond with OK" prompt against the provider/model.

    Returns `{ok, latency_ms, sample_output, provider, model, error?}`. Never
    raises — failures populate `error` so the UI can show inline diagnostics
    without unwinding the request handler.
    """
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    if not api_key:
        env_var = defaults.get("api_key_env", "")
        if env_var:
            api_key = os.environ.get(env_var, "")
    if not base_url:
        base_url = defaults.get("base_url", "")

    started = time.time()
    try:
        instance = _build_provider(provider, model, api_key or "", base_url or "")
    except Exception as e:
        return {
            "ok": False,
            "latency_ms": int((time.time() - started) * 1000),
            "sample_output": "",
            "provider": provider,
            "model": model,
            "error": f"init failed: {type(e).__name__}: {e}",
        }

    try:
        out = instance.generate(_TEST_PROMPT, temperature=0.0, max_tokens=10)
        latency_ms = int((time.time() - started) * 1000)
        out_stripped = (out or "").strip()
        return {
            "ok": bool(out_stripped),
            "latency_ms": latency_ms,
            "sample_output": out_stripped[:200],
            "provider": provider,
            "model": model,
        }
    except Exception as e:
        return {
            "ok": False,
            "latency_ms": int((time.time() - started) * 1000),
            "sample_output": "",
            "provider": provider,
            "model": model,
            "error": f"call failed: {type(e).__name__}: {e}",
        }
