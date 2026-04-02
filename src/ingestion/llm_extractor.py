"""LLM-based structured extraction of beliefs, stories, and style rules."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from ..llm.base import LLMProvider
from ..utils.text_utils import load_prompt, fill_prompt

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def extract_beliefs(text: str, llm: LLMProvider) -> list[dict]:
    """Extract beliefs/opinions/stances from text."""
    print(f"\033[35m[Extractor]\033[0m extract_beliefs() — input={len(text)} chars", file=sys.stderr, flush=True)
    template = load_prompt(PROMPTS_DIR / "extract_beliefs.txt")
    prompt = fill_prompt(template, text=text)
    result = llm.generate_json(prompt)
    if isinstance(result, list):
        print(f"\033[35m[Extractor]\033[0m \033[32m→ {len(result)} beliefs extracted\033[0m", file=sys.stderr, flush=True)
        return result
    beliefs = result.get("beliefs", []) if isinstance(result, dict) else []
    print(f"\033[35m[Extractor]\033[0m \033[32m→ {len(beliefs)} beliefs extracted\033[0m", file=sys.stderr, flush=True)
    return beliefs


def extract_stories(text: str, llm: LLMProvider) -> list[dict]:
    """Extract personal anecdotes and experiences from text."""
    print(f"\033[35m[Extractor]\033[0m extract_stories() — input={len(text)} chars", file=sys.stderr, flush=True)
    template = load_prompt(PROMPTS_DIR / "extract_stories.txt")
    prompt = fill_prompt(template, text=text)
    result = llm.generate_json(prompt)
    if isinstance(result, list):
        print(f"\033[35m[Extractor]\033[0m \033[32m→ {len(result)} stories extracted\033[0m", file=sys.stderr, flush=True)
        return result
    stories = result.get("stories", []) if isinstance(result, dict) else []
    print(f"\033[35m[Extractor]\033[0m \033[32m→ {len(stories)} stories extracted\033[0m", file=sys.stderr, flush=True)
    return stories


def extract_style_rules(text: str, llm: LLMProvider) -> list[dict]:
    """Extract writing patterns and rhetorical moves from text."""
    print(f"\033[35m[Extractor]\033[0m extract_style_rules() — input={len(text)} chars", file=sys.stderr, flush=True)
    template = load_prompt(PROMPTS_DIR / "extract_style.txt")
    prompt = fill_prompt(template, text=text)
    result = llm.generate_json(prompt)
    if isinstance(result, list):
        print(f"\033[35m[Extractor]\033[0m \033[32m→ {len(result)} style rules extracted\033[0m", file=sys.stderr, flush=True)
        return result
    rules = result.get("style_rules", []) if isinstance(result, dict) else []
    print(f"\033[35m[Extractor]\033[0m \033[32m→ {len(rules)} style rules extracted\033[0m", file=sys.stderr, flush=True)
    return rules


def extract_thinking_models(text: str, llm: LLMProvider) -> list[dict]:
    """Extract mental models and thinking frameworks from text."""
    print(f"\033[35m[Extractor]\033[0m extract_thinking_models() — input={len(text)} chars", file=sys.stderr, flush=True)
    template = load_prompt(PROMPTS_DIR / "extract_thinking_models.txt")
    prompt = fill_prompt(template, text=text)
    result = llm.generate_json(prompt)
    if isinstance(result, list):
        print(f"\033[35m[Extractor]\033[0m \033[32m→ {len(result)} thinking models extracted\033[0m", file=sys.stderr, flush=True)
        return result
    models = result.get("thinking_models", []) if isinstance(result, dict) else []
    print(f"\033[35m[Extractor]\033[0m \033[32m→ {len(models)} thinking models extracted\033[0m", file=sys.stderr, flush=True)
    return models


def extract_vocabulary(full_text: str, llm: LLMProvider) -> dict:
    """Extract vocabulary fingerprint — signature phrases, banned words, pronoun rules.

    Unlike other extractors, this runs ONCE on the full concatenated text (not per-chunk)
    to capture patterns that only emerge across the whole corpus.
    """
    print(f"\033[35m[Extractor]\033[0m \033[1mextract_vocabulary()\033[0m — input={len(full_text)} chars", file=sys.stderr, flush=True)
    template = load_prompt(PROMPTS_DIR / "extract_vocabulary.txt")
    # Use first 15K chars to stay within context window
    prompt = fill_prompt(template, text=full_text[:15000])
    result = llm.generate_json(prompt)

    if not isinstance(result, dict):
        print(f"\033[35m[Extractor]\033[0m \033[31m→ Vocabulary extraction failed, using defaults\033[0m", file=sys.stderr, flush=True)
        return {"phrases_used": [], "phrases_never": [], "pronoun_rules": {}, "punctuation_rules": []}

    # Ensure required keys
    result.setdefault("phrases_used", [])
    result.setdefault("phrases_never", [])
    result.setdefault("pronoun_rules", {})
    result.setdefault("punctuation_rules", [])

    print(f"\033[35m[Extractor]\033[0m \033[32m→ Vocabulary: {len(result['phrases_used'])} used, {len(result['phrases_never'])} banned\033[0m", file=sys.stderr, flush=True)
    return result


def generate_personality_card(all_data: dict, llm: LLMProvider) -> str:
    """Generate a natural language personality summary from all extracted data."""
    print(f"\033[35m[Extractor]\033[0m \033[1mgenerate_personality_card()\033[0m — beliefs={len(all_data.get('beliefs', []))}, stories={len(all_data.get('stories', []))}, style_rules={len(all_data.get('style_rules', []))}, thinking_models={len(all_data.get('thinking_models', []))}", file=sys.stderr, flush=True)
    template = load_prompt(PROMPTS_DIR / "generate_personality_card.txt")

    beliefs_summary = "\n".join(
        f"- {b.get('topic', '?')}: {b.get('stance', '?')}" for b in all_data.get("beliefs", [])[:20]
    )
    stories_summary = "\n".join(
        f"- {s.get('title', '?')}: {s.get('summary', '?')}" for s in all_data.get("stories", [])[:15]
    )
    style_summary = "\n".join(
        f"- {r.get('rule_type', '?')}: {r.get('description', '?')}" for r in all_data.get("style_rules", [])[:15]
    )
    models_summary = "\n".join(
        f"- {m.get('name', '?')}: {m.get('description', '?')}" for m in all_data.get("thinking_models", [])[:10]
    )

    prompt = fill_prompt(
        template,
        beliefs=beliefs_summary,
        stories=stories_summary,
        style_rules=style_summary,
        thinking_models=models_summary,
    )
    return llm.generate(prompt, temperature=0.5, max_tokens=1500)
