"""Curated provider + model catalog for the Models & Providers UI dropdowns.

Hardcoded lists keep the UX clean — users rarely want all 200+ OpenRouter
models in a dropdown. "Custom…" is always available for any provider so an
operator can type a model ID that isn't in the curated list.

The frontend reads this via `GET /api/admin/models/providers`.
"""

from __future__ import annotations

import os
from typing import TypedDict


class ModelEntry(TypedDict):
    id: str
    label: str
    tier: str


class ProviderEntry(TypedDict, total=False):
    label: str
    models: list[ModelEntry]
    supports: list[str]
    base_url: str
    api_key_env: str
    custom_models_allowed: bool


PROVIDER_CATALOG: dict[str, ProviderEntry] = {
    "anthropic": {
        "label": "Anthropic (Claude)",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com",
        "models": [
            {"id": "claude-opus-4-7",              "label": "Opus 4.7 (latest, best)",        "tier": "heavy"},
            {"id": "claude-opus-4-6",              "label": "Opus 4.6 (best quality)",        "tier": "heavy"},
            {"id": "claude-sonnet-4-6",            "label": "Sonnet 4.6 (balanced)",          "tier": "medium"},
            {"id": "claude-haiku-4-5-20251001",    "label": "Haiku 4.5 (fast, cheap)",        "tier": "light"},
        ],
        "supports": ["streaming", "web_search", "thinking", "json"],
        "custom_models_allowed": True,
    },
    "kimi": {
        "label": "Kimi (Moonshot AI)",
        "api_key_env": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.ai/v1",
        "models": [
            {"id": "kimi-k2-instruct",   "label": "Kimi K2 (best quality)",       "tier": "heavy"},
            {"id": "moonshot-v1-128k",   "label": "Moonshot v1 (128k context)",   "tier": "medium"},
            {"id": "moonshot-v1-32k",    "label": "Moonshot v1 (32k context)",    "tier": "medium"},
            {"id": "moonshot-v1-8k",     "label": "Moonshot v1 (8k, cheap)",      "tier": "light"},
        ],
        "supports": ["streaming", "json"],
        "custom_models_allowed": True,
    },
    "openai": {
        "label": "OpenAI",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "models": [
            {"id": "gpt-4o",         "label": "GPT-4o (balanced)",        "tier": "heavy"},
            {"id": "gpt-4o-mini",    "label": "GPT-4o mini (fast)",       "tier": "medium"},
            {"id": "gpt-4-turbo",    "label": "GPT-4 Turbo",              "tier": "heavy"},
            {"id": "o1",             "label": "o1 (reasoning)",           "tier": "heavy"},
            {"id": "o3-mini",        "label": "o3-mini (reasoning, fast)", "tier": "medium"},
        ],
        "supports": ["streaming", "json"],
        "custom_models_allowed": True,
    },
    "gemini": {
        "label": "Google Gemini",
        "api_key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": [
            {"id": "gemini-2.5-pro",     "label": "Gemini 2.5 Pro",     "tier": "heavy"},
            {"id": "gemini-2.5-flash",   "label": "Gemini 2.5 Flash",   "tier": "medium"},
            {"id": "gemini-2.0-flash",   "label": "Gemini 2.0 Flash",   "tier": "light"},
        ],
        "supports": ["streaming", "json"],
        "custom_models_allowed": True,
    },
    "nvidia": {
        "label": "NVIDIA",
        "api_key_env": "NVIDIA_API_KEY",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "models": [
            {"id": "nvidia/nemotron-3-super-120b-a12b", "label": "Nemotron-3 Super 120B", "tier": "heavy"},
        ],
        "supports": ["streaming", "json", "thinking"],
        "custom_models_allowed": True,
    },
    "openrouter": {
        "label": "OpenRouter (aggregator)",
        "api_key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            {"id": "z-ai/glm-4.5-air:free",                 "label": "GLM 4.5 Air (free)",          "tier": "light"},
            {"id": "anthropic/claude-sonnet-4",             "label": "Claude Sonnet 4 (via OR)",    "tier": "heavy"},
            {"id": "openai/gpt-4o-mini",                    "label": "GPT-4o mini (via OR)",        "tier": "medium"},
            {"id": "google/gemini-2.5-flash-preview",       "label": "Gemini 2.5 Flash (via OR)",   "tier": "medium"},
            {"id": "meta-llama/llama-4-maverick:free",      "label": "Llama 4 Maverick (free)",     "tier": "light"},
            {"id": "deepseek/deepseek-chat-v3-0324:free",   "label": "DeepSeek v3 (free)",          "tier": "medium"},
        ],
        "supports": ["streaming", "json"],
        "custom_models_allowed": True,
    },
    "ollama": {
        "label": "Ollama (local)",
        "api_key_env": "",
        "base_url": "http://localhost:11434",
        "models": [
            {"id": "llama3.1:8b",   "label": "Llama 3.1 8B",   "tier": "light"},
            {"id": "qwen2.5:32b",   "label": "Qwen 2.5 32B",   "tier": "medium"},
        ],
        "supports": ["streaming", "json"],
        "custom_models_allowed": True,
    },
    "lmstudio": {
        "label": "LM Studio (local)",
        "api_key_env": "",
        "base_url": "http://localhost:1234/v1",
        "models": [
            {"id": "local-model",   "label": "(whatever's loaded in LM Studio)",   "tier": "medium"},
        ],
        "supports": ["streaming", "json"],
        "custom_models_allowed": True,
    },
}


def provider_catalog_with_env_status(stored_keys: dict | None = None) -> dict[str, dict]:
    """Same as PROVIDER_CATALOG but with ``key_present`` and ``key_source``.

    The frontend uses these to render status badges.  Keys themselves are
    never returned over the wire.  ``stored_keys`` is an optional dict of
    provider-name → API-key from the admin (or founder) config file.
    """
    out: dict[str, dict] = {}
    sk = stored_keys or {}
    for name, entry in PROVIDER_CATALOG.items():
        env_var = entry.get("api_key_env", "")
        has_env = bool(os.environ.get(env_var)) if env_var else False
        has_stored = bool(sk.get(name))
        is_local = name in ("ollama", "lmstudio")
        if is_local:
            key_present, key_source = True, "local"
        elif has_stored:
            key_present, key_source = True, "saved"
        elif has_env:
            key_present, key_source = True, "env"
        else:
            key_present, key_source = False, "none"
        out[name] = {
            "label": entry.get("label", name),
            "models": entry.get("models", []),
            "supports": entry.get("supports", []),
            "base_url": entry.get("base_url", ""),
            "api_key_env": env_var,
            "custom_models_allowed": entry.get("custom_models_allowed", True),
            "key_present": key_present,
            "key_source": key_source,
        }
    return out
