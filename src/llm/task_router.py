"""Per-task LLM resolution.

The router consults founder override → admin default → hardcoded fallback
to decide which provider/model handles each pipeline task. Caches built
LLMProvider instances by (provider, model, max_tokens) so we don't
re-instantiate clients per call.

Pipeline usage:
    router = LLMRouter(config_path="config/llm-config.yaml", founder_slug="sharath")
    llm = router.for_task("dissect")
    response = llm.generate(prompt, temperature=0.2, max_tokens=2000)

The router also tracks which source ("founder" / "admin" / "default") each
resolution came from so the tracer can surface that in run logs.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import yaml

from .base import LLMProvider
from .config_io import load_admin_config, load_founder_override
from .factory import PROVIDER_DEFAULTS, _find_config, _resolve_api_key, _resolve_base_url, create_llm
from .task_catalog import TASK_CATALOG, validate_task_id

logger = logging.getLogger(__name__)


def _import_provider_class(provider: str):
    """Lazy import to avoid pulling every provider's SDK at module load."""
    if provider == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider
    if provider == "lmstudio":
        from .lmstudio_provider import LMStudioProvider
        return LMStudioProvider
    if provider == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider
    if provider == "nvidia":
        from .nvidia_provider import NvidiaProvider
        return NvidiaProvider
    if provider == "openrouter":
        from .openrouter_provider import OpenRouterProvider
        return OpenRouterProvider
    if provider == "kimi":
        from .moonshot_provider import MoonshotProvider
        return MoonshotProvider
    if provider in ("anthropic", "openai"):
        from .api_provider import APIProvider
        return APIProvider
    raise ValueError(f"unknown provider: {provider!r}")


class LLMRouter:
    """Resolves and caches an LLMProvider per pipeline task.

    Resolution order for each task:
      1. Founder override (data/founders/<slug>/config/models-override.json)
      2. Admin default     (config/models-config.json)
      3. Catalog fallback  (task_catalog.TASK_CATALOG default_purpose → llm-config.yaml section)
    """

    def __init__(
        self,
        config_path: str = "config/llm-config.yaml",
        founder_slug: Optional[str] = None,
    ):
        self.config_path = config_path
        self.founder_slug = founder_slug
        self._admin_cfg = load_admin_config()
        self._founder_cfg = load_founder_override(founder_slug) if founder_slug else {"tasks": {}}
        self._yaml_cfg: dict | None = None
        self._instance_cache: dict[tuple, LLMProvider] = {}
        self._on_token_callback = None

    # ----- public API -----

    def set_on_token(self, callback) -> None:
        """Wire a token-streaming callback onto every cached + future provider instance."""
        self._on_token_callback = callback
        for inst in self._instance_cache.values():
            if hasattr(inst, "on_token"):
                inst.on_token = callback

    def resolve(self, task_id: str) -> dict:
        """Return the resolved config for a task, including `_source` label.

        Always returns a dict with at least provider, model, max_tokens, temperature.
        """
        if not validate_task_id(task_id):
            raise ValueError(f"unknown task_id: {task_id!r}")

        spec = TASK_CATALOG[task_id]
        founder_tasks = (self._founder_cfg or {}).get("tasks") or {}
        admin_tasks = (self._admin_cfg or {}).get("tasks") or {}

        admin_synthesized = bool((self._admin_cfg or {}).get("_synthesized"))

        if task_id in founder_tasks:
            resolved = dict(founder_tasks[task_id])
            resolved["_source"] = "founder"
        elif task_id in admin_tasks:
            resolved = dict(admin_tasks[task_id])
            resolved["_source"] = "default" if admin_synthesized else "admin"
        else:
            yaml_cfg = self._load_yaml()
            section = {
                "generation": yaml_cfg.get("llm", {}),
                "prep":       yaml_cfg.get("llm_prep", yaml_cfg.get("llm", {})),
                "ingestion":  yaml_cfg.get("llm_ingestion", yaml_cfg.get("llm", {})),
            }.get(spec.default_purpose, yaml_cfg.get("llm", {}))
            resolved = {
                "provider": section.get("provider", "anthropic"),
                "model": section.get("model", "claude-opus-4-6"),
                "max_tokens": section.get("max_tokens", spec.default_max_tokens),
                "temperature": section.get("temperature", spec.default_temperature),
                "enable_thinking": section.get("enable_thinking", False),
                "effort": section.get("effort", "high"),
                "_source": "default",
            }

        resolved.setdefault("max_tokens", spec.default_max_tokens)
        resolved.setdefault("temperature", spec.default_temperature)
        resolved.setdefault("enable_thinking", False)
        resolved.setdefault("effort", "high")
        resolved.setdefault("thinking_budget", spec.default_thinking_budget)
        if resolved["enable_thinking"] and not resolved.get("thinking_budget"):
            resolved["thinking_budget"] = 10000
        resolved["task_id"] = task_id
        return resolved

    def for_task(self, task_id: str) -> LLMProvider:
        """Return (and cache) an LLMProvider for the named task."""
        resolved = self.resolve(task_id)
        return self._instance_for(resolved)

    def for_purpose(self, purpose: str) -> LLMProvider:
        """Back-compat: resolve via the legacy purpose buckets in llm-config.yaml.

        Used by code that hasn't been migrated to task-aware calls yet.
        """
        yaml_cfg = self._load_yaml()
        section = {
            "generation": yaml_cfg.get("llm", {}),
            "prep":       yaml_cfg.get("llm_prep", yaml_cfg.get("llm", {})),
            "ingestion":  yaml_cfg.get("llm_ingestion", yaml_cfg.get("llm", {})),
        }.get(purpose, yaml_cfg.get("llm", {}))
        resolved = {
            "provider": section.get("provider", "anthropic"),
            "model": section.get("model", "claude-opus-4-6"),
            "max_tokens": section.get("max_tokens", 4000),
            "temperature": section.get("temperature", 0.5),
            "enable_thinking": section.get("enable_thinking", False),
            "effort": section.get("effort", "high"),
            "_source": "default",
            "task_id": f"_purpose:{purpose}",
        }
        return self._instance_for(resolved)

    def task_sources(self) -> dict[str, str]:
        """Map of task_id → source ('founder'/'admin'/'default') for UI badges."""
        return {tid: self.resolve(tid)["_source"] for tid in TASK_CATALOG.keys()}

    # ----- internals -----

    def _load_yaml(self) -> dict:
        if self._yaml_cfg is None:
            try:
                resolved = _find_config(self.config_path)
                with open(resolved, "r") as f:
                    self._yaml_cfg = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning("[task_router] failed to load %s: %s — using empty config", self.config_path, e)
                self._yaml_cfg = {}
        return self._yaml_cfg

    def _instance_for(self, resolved: dict) -> LLMProvider:
        provider = resolved["provider"]
        model = resolved["model"]
        max_tokens = resolved.get("max_tokens", 4000)
        thinking_budget = resolved.get("thinking_budget", 0)
        key = (provider, model, max_tokens, resolved.get("enable_thinking", False), resolved.get("effort", "high"), thinking_budget)
        cached = self._instance_cache.get(key)
        if cached is not None:
            if self._on_token_callback and hasattr(cached, "on_token"):
                cached.on_token = self._on_token_callback
            return cached

        api_key = self._resolve_key(provider, resolved)
        base_url = self._resolve_url(provider, resolved)

        ProviderCls = _import_provider_class(provider)
        if provider == "ollama":
            instance = ProviderCls(model=model, base_url=base_url)
        elif provider == "lmstudio":
            instance = ProviderCls(model=model, base_url=base_url)
        elif provider == "gemini":
            instance = ProviderCls(model=model, api_key=api_key, base_url=base_url)
        elif provider == "nvidia":
            instance = ProviderCls(
                model=model, api_key=api_key, base_url=base_url,
                enable_thinking=resolved.get("enable_thinking", False),
                reasoning_budget=resolved.get("reasoning_budget", 16384),
            )
        elif provider == "openrouter":
            instance = ProviderCls(model=model, api_key=api_key, base_url=base_url)
        elif provider == "kimi":
            instance = ProviderCls(model=model, api_key=api_key, base_url=base_url)
        elif provider in ("anthropic", "openai"):
            instance = ProviderCls(
                provider=provider, model=model, api_key=api_key,
                enable_thinking=resolved.get("enable_thinking", True),
                effort=resolved.get("effort", "high"),
            )
        else:
            raise ValueError(f"unknown provider in resolved config: {provider!r}")

        instance._configured_max_tokens = max_tokens
        instance._configured_thinking_budget = thinking_budget
        if self._on_token_callback and hasattr(instance, "on_token"):
            instance.on_token = self._on_token_callback
        self._instance_cache[key] = instance

        thinking_info = f", thinking_budget={thinking_budget}" if thinking_budget else ""
        print(
            f"\033[36m[LLM Router]\033[0m built provider={provider!r}, model={model!r}, "
            f"max_tokens={max_tokens}{thinking_info}, source={resolved.get('_source')!r}, task={resolved.get('task_id')!r}",
            file=sys.stderr, flush=True,
        )
        return instance

    def _resolve_key(self, provider: str, resolved: dict) -> str:
        # Resolution: task-level key → founder stored key → admin stored key → env var
        key = resolved.get("api_key") or ""
        if key:
            return key
        founder_keys = (self._founder_cfg or {}).get("provider_keys", {})
        if founder_keys.get(provider):
            return founder_keys[provider]
        admin_keys = (self._admin_cfg or {}).get("provider_keys", {})
        if admin_keys.get(provider):
            return admin_keys[provider]
        defaults = PROVIDER_DEFAULTS.get(provider, {})
        env_var = defaults.get("api_key_env", "")
        if env_var:
            return os.environ.get(env_var, "")
        return ""

    def _resolve_url(self, provider: str, resolved: dict) -> str:
        explicit = resolved.get("base_url") or ""
        defaults = PROVIDER_DEFAULTS.get(provider, {})
        default_url = defaults.get("base_url", "")
        if not explicit:
            return default_url
        # Guard against stale localhost URLs in cloud configs (mirrors factory._resolve_base_url).
        is_local_url = "localhost" in explicit or "127.0.0.1" in explicit
        is_local_provider = provider in ("lmstudio", "ollama")
        if is_local_url and not is_local_provider:
            return default_url
        if not is_local_url and is_local_provider:
            return default_url
        return explicit
