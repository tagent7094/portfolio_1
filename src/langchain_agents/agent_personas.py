"""Agent persona definitions as LangChain system prompts."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_personas(config_path: str = "config/agent-personas.yaml") -> list[dict]:
    """Load agent personas from config."""
    path = Path(config_path)
    if not path.exists():
        path = Path(__file__).parent.parent.parent / config_path
    with open(path) as f:
        config = yaml.safe_load(f)
    return config.get("personas", [])


def persona_system_prompt(persona: dict) -> str:
    """Build a system prompt for an agent persona."""
    return (
        f"You are {persona['name']}. {persona['description']}\n"
        f"Your analytical bias: {persona['bias']}\n\n"
        "When analyzing content, lean into your specific perspective. "
        "Be opinionated. Your unique viewpoint is your value."
    )


SCORING_NARRATIVE_INSTRUCTION = """Score this narrative on 4 dimensions (each 0-10):
1. Safety — will this get the founder in trouble? (10=safe, 0=risky)
2. Traction — will this get engagement? (10=viral, 0=ignored)
3. Alignment — does this match their beliefs/expertise? (10=core thesis, 0=off-brand)
4. Freshness — is this a take nobody else is making? (10=original, 0=cliche)

Return ONLY a JSON object: {"safety": N, "traction": N, "alignment": N, "freshness": N}"""


SCORING_POST_INSTRUCTION = """Score this post on 4 dimensions (each 0-10):
1. Voice fidelity — does this sound like the person? (10=indistinguishable, 0=generic AI)
2. Hook strength — would you stop scrolling? (10=irresistible, 0=boring)
3. Argument quality — is the logic sound? (10=airtight, 0=flawed)
4. Engagement prediction — will people share this? (10=highly shareable, 0=ignored)

Return ONLY a JSON object: {"voice_fidelity": N, "hook_strength": N, "argument_quality": N, "engagement_prediction": N}"""
