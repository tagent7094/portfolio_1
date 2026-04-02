"""Adapt existing LLM config to LangChain ChatModels."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from langchain_openai import ChatOpenAI


def _find_config(config_path: str = "config/llm-config.yaml") -> Path:
    path = Path(config_path)
    if path.exists():
        return path
    project_root = Path(__file__).parent.parent.parent
    candidate = project_root / config_path
    if candidate.exists():
        return candidate
    return path


def create_langchain_llm(config_path: str = "config/llm-config.yaml"):
    """Create a LangChain ChatModel from our config.

    Works with Ollama, LM Studio, NVIDIA, OpenAI, and Anthropic.
    """
    resolved = _find_config(config_path)
    with open(resolved) as f:
        config = yaml.safe_load(f)

    llm_cfg = config["llm"]
    provider = llm_cfg["provider"]
    model = llm_cfg.get("model", "llama3.1:8b")
    temperature = llm_cfg.get("temperature", 0.7)
    max_tokens = llm_cfg.get("max_tokens", 2000)

    if provider == "ollama":
        return ChatOpenAI(
            model=model,
            base_url=llm_cfg.get("base_url", "http://localhost:11434") + "/v1",
            api_key="ollama",
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif provider == "lmstudio":
        return ChatOpenAI(
            model=model,
            base_url=llm_cfg.get("base_url", "http://localhost:1234/v1"),
            api_key="not-needed",
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif provider == "nvidia":
        api_key = llm_cfg.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
        return ChatOpenAI(
            model=model,
            base_url=llm_cfg.get("base_url", "https://integrate.api.nvidia.com/v1"),
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            model_kwargs={
                "top_p": 0.95,
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": llm_cfg.get("enable_thinking", True)},
                    "reasoning_budget": llm_cfg.get("reasoning_budget", 16384),
                },
            },
        )
    elif provider == "gemini":
        api_key = llm_cfg.get("api_key") or os.environ.get("GEMINI_API_KEY", "")
        return ChatOpenAI(
            model=model,
            base_url=llm_cfg.get("base_url", os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")),
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif provider == "openai":
        return ChatOpenAI(
            model=model,
            api_key=llm_cfg.get("api_key") or os.environ.get("OPENAI_API_KEY", ""),
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif provider == "anthropic":
        api_key = llm_cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model,
                anthropic_api_key=api_key,
                anthropic_api_url="https://api.anthropic.com",
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except ImportError:
            raise ValueError(
                "Install langchain-anthropic: pip install langchain-anthropic"
            )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
