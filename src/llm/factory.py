"""Factory to create the correct LLM provider from config + .env."""

import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .base import LLMProvider
from .ollama_provider import OllamaProvider
from .lmstudio_provider import LMStudioProvider
from .api_provider import APIProvider
from .nvidia_provider import NvidiaProvider
from .gemini_provider import GeminiProvider
from .openrouter_provider import OpenRouterProvider

# Load .env from project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

# Pre-built provider defaults (read from .env)
PROVIDER_DEFAULTS = {
    "anthropic": {
        "base_url": os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-6",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    },
    "openai": {
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o3-mini"],
    },
    "gemini": {
        "base_url": os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
        "api_key_env": "GEMINI_API_KEY",
        "default_model": "gemini-2.5-flash",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    },
    "nvidia": {
        "base_url": os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        "api_key_env": "NVIDIA_API_KEY",
        "default_model": "nvidia/nemotron-3-super-120b-a12b",
        "models": ["nvidia/nemotron-3-super-120b-a12b"],
    },
    "lmstudio": {
        "base_url": os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"),
        "api_key_env": "",
        "default_model": "local-model",
        "models": [],
    },
    "openrouter": {
        "base_url": os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        "api_key_env": "OPENROUTER_API_KEY",
        "default_model": "z-ai/glm-4.5-air:free",
        "models": ["z-ai/glm-4.5-air:free", "google/gemini-2.5-flash-preview", "anthropic/claude-sonnet-4", "openai/gpt-4o-mini", "meta-llama/llama-4-maverick:free", "deepseek/deepseek-chat-v3-0324:free"],
    },
    "ollama": {
        "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        "api_key_env": "",
        "default_model": "llama3.1:8b",
        "models": [],
    },
}


def get_provider_defaults() -> dict:
    """Return provider defaults for the frontend dropdowns."""
    return {
        provider: {
            "base_url": info["base_url"],
            "default_model": info["default_model"],
            "models": info["models"],
            "has_api_key": bool(os.environ.get(info["api_key_env"], "")),
        }
        for provider, info in PROVIDER_DEFAULTS.items()
    }


def _find_config(config_path: str = "config/llm-config.yaml") -> Path:
    path = Path(config_path)
    if path.is_absolute() and path.exists():
        return path
    if path.exists():
        return path
    candidate = _PROJECT_ROOT / config_path
    if candidate.exists():
        return candidate
    return path


def _resolve_api_key(llm_cfg: dict, provider: str) -> str:
    """Get API key from config, then fall back to .env."""
    key = llm_cfg.get("api_key", "")
    if key:
        return key
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    env_var = defaults.get("api_key_env", "")
    if env_var:
        return os.environ.get(env_var, "")
    return ""


def _resolve_base_url(llm_cfg: dict, provider: str) -> str:
    """Get base URL for the provider.

    Uses the provider's default URL unless the config explicitly overrides it.
    Ignores stale base_url values left over from a different provider
    (e.g. localhost:1234 when provider switched from lmstudio to nvidia).
    """
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    default_url = defaults.get("base_url", "")

    config_url = llm_cfg.get("base_url", "")
    if not config_url:
        return default_url

    # Check if config_url looks like it belongs to a DIFFERENT provider
    # (e.g. localhost when using a cloud provider, or a cloud URL when using local)
    is_local_url = "localhost" in config_url or "127.0.0.1" in config_url
    is_local_provider = provider in ("lmstudio", "ollama")

    if is_local_url and not is_local_provider:
        # Stale local URL for a cloud provider — use provider default instead
        print(f"\033[36m[LLM Factory]\033[0m Ignoring stale base_url={config_url} for cloud provider {provider}, using default={default_url}", file=sys.stderr, flush=True)
        return default_url
    if not is_local_url and is_local_provider:
        # Cloud URL for a local provider — use provider default instead
        print(f"\033[36m[LLM Factory]\033[0m Ignoring stale base_url={config_url} for local provider {provider}, using default={default_url}", file=sys.stderr, flush=True)
        return default_url

    return config_url


def create_llm(config_path: str = "config/llm-config.yaml", purpose: str = "generation") -> LLMProvider:
    """Create an LLM provider from config + .env.

    Args:
        config_path: Path to YAML config
        purpose: "generation" uses llm section, "ingestion" uses llm_ingestion section
    """
    resolved = _find_config(config_path)
    print(f"\033[36m[LLM Factory]\033[0m Loading config from {resolved} (purpose={purpose})", file=sys.stderr, flush=True)
    with open(resolved, "r") as f:
        config = yaml.safe_load(f)

    if purpose == "ingestion" and "llm_ingestion" in config:
        llm_cfg = config["llm_ingestion"]
        print(f"\033[36m[LLM Factory]\033[0m Using ingestion LLM config", file=sys.stderr, flush=True)
    else:
        llm_cfg = config["llm"]

    provider = llm_cfg["provider"]
    model = llm_cfg.get("model", "unknown")
    api_key = _resolve_api_key(llm_cfg, provider)
    base_url = _resolve_base_url(llm_cfg, provider)

    configured_max_tokens = llm_cfg.get("max_tokens", 2000)
    print(f"\033[36m[LLM Factory]\033[0m \033[1mCreating provider={provider!r}, model={model!r}, max_tokens={configured_max_tokens}, base_url={base_url[:40]}...\033[0m", file=sys.stderr, flush=True)

    instance: LLMProvider
    if provider == "ollama":
        instance = OllamaProvider(model=model, base_url=base_url)
    elif provider == "lmstudio":
        instance = LMStudioProvider(model=model, base_url=base_url)
    elif provider == "gemini":
        instance = GeminiProvider(model=model, api_key=api_key, base_url=base_url)
    elif provider == "nvidia":
        instance = NvidiaProvider(
            model=model, api_key=api_key, base_url=base_url,
            enable_thinking=llm_cfg.get("enable_thinking", False),
            reasoning_budget=llm_cfg.get("reasoning_budget", 16384),
        )
    elif provider == "openrouter":
        instance = OpenRouterProvider(model=model, api_key=api_key, base_url=base_url)
    elif provider in ("anthropic", "openai"):
        instance = APIProvider(
            provider=provider, model=model, api_key=api_key,
            enable_thinking=llm_cfg.get("enable_thinking", True),
            effort=llm_cfg.get("effort", "high"),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")

    # Set configured max tokens so generate_json uses the right limit
    instance._configured_max_tokens = configured_max_tokens
    return instance
