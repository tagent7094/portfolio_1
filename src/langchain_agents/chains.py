"""LangChain chains for extraction, generation, and humanization."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt

logger = logging.getLogger(__name__)

INGESTION_PROMPTS = Path(__file__).parent.parent / "ingestion" / "prompts"
GENERATION_PROMPTS = Path(__file__).parent.parent / "generation" / "prompts"
HUMANIZATION_PROMPTS = Path(__file__).parent.parent / "humanization" / "prompts"


def extract_beliefs_chain(llm, text: str) -> list[dict]:
    """Extract beliefs using LangChain."""
    template = load_prompt(INGESTION_PROMPTS / "extract_beliefs.txt")
    prompt = fill_prompt(template, text=text)
    response = llm.invoke([HumanMessage(content=prompt)])
    return parse_llm_json(response.content) if isinstance(parse_llm_json(response.content), list) else []


def extract_stories_chain(llm, text: str) -> list[dict]:
    """Extract stories using LangChain."""
    template = load_prompt(INGESTION_PROMPTS / "extract_stories.txt")
    prompt = fill_prompt(template, text=text)
    response = llm.invoke([HumanMessage(content=prompt)])
    result = parse_llm_json(response.content)
    return result if isinstance(result, list) else []


def extract_style_chain(llm, text: str) -> list[dict]:
    """Extract style rules using LangChain."""
    template = load_prompt(INGESTION_PROMPTS / "extract_style.txt")
    prompt = fill_prompt(template, text=text)
    response = llm.invoke([HumanMessage(content=prompt)])
    result = parse_llm_json(response.content)
    return result if isinstance(result, list) else []


def generate_post_chain(
    llm,
    narrative: str,
    strategy: str,
    platform: str,
    personality_card: str,
    beliefs: str,
    stories: str,
    style_rules: list[dict],
    vocabulary: dict,
) -> str:
    """Generate a post using LangChain."""
    template = load_prompt(GENERATION_PROMPTS / "generate_post.txt")

    def _format_rules(rules, rule_type):
        matching = [r for r in rules if r.get("rule_type") == rule_type]
        return "\n".join(f"- {r.get('description', '')}" for r in matching) or "No specific rules."

    anti_patterns = "\n".join(
        f"- NEVER: {r['anti_pattern']}" for r in style_rules if r.get("anti_pattern")
    ) or "None specified."

    prompt = fill_prompt(
        template,
        platform=platform,
        personality_card=personality_card or "Not available.",
        narrative=narrative,
        beliefs=beliefs or "No specific beliefs.",
        stories=stories or "No specific stories.",
        strategy=strategy,
        opening_rules=_format_rules(style_rules, "opening"),
        closing_rules=_format_rules(style_rules, "closing"),
        rhythm_rules=_format_rules(style_rules, "rhythm"),
        phrases_used=", ".join(vocabulary.get("phrases_used", [])) or "None.",
        phrases_never=", ".join(vocabulary.get("phrases_never", [])) or "None.",
        punctuation_rules=_format_rules(style_rules, "punctuation"),
        pronoun_rules=json.dumps(vocabulary.get("pronoun_rules", {})),
        platform_rules=f"Platform: {platform}",
        anti_patterns=anti_patterns,
    )

    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content.strip()


def score_with_persona(llm, persona_prompt: str, scoring_instruction: str, content: str, context: str = "") -> dict:
    """Score content using an agent persona."""
    messages = [
        SystemMessage(content=persona_prompt),
        HumanMessage(content=f"{scoring_instruction}\n\nCONTENT:\n{content}\n\nCONTEXT:\n{context}"),
    ]
    response = llm.invoke(messages)
    result = parse_llm_json(response.content)
    return result if isinstance(result, dict) else {}


def match_topic_chain(llm, topic: str, beliefs: str, stories: str, models: str) -> dict:
    """Match a topic to the graph using LangChain."""
    template = load_prompt(GENERATION_PROMPTS / "match_topic.txt")
    prompt = fill_prompt(template, topic=topic, beliefs=beliefs, stories=stories, models=models)
    response = llm.invoke([HumanMessage(content=prompt)])
    result = parse_llm_json(response.content)
    return result if isinstance(result, dict) else {}


def score_with_audience_agent(llm, agent_system_prompt: str, post_text: str, personality_card: str) -> dict:
    """Score a post using an audience sub-agent. Returns {score, feedback}."""
    scoring_prompt = (
        "Score this post from 1-10 based on how well it resonates with you as a reader.\n"
        "Provide 2-3 sentences of specific feedback from your perspective.\n\n"
        f"POST:\n{post_text}\n\n"
        f"AUTHOR CONTEXT:\n{personality_card}\n\n"
        'Respond in JSON: {"score": <1-10>, "feedback": "<critique>"}'
    )
    messages = [
        SystemMessage(content=agent_system_prompt),
        HumanMessage(content=scoring_prompt),
    ]
    response = llm.invoke(messages)
    result = parse_llm_json(response.content)
    if not isinstance(result, dict):
        return {"score": 5, "feedback": "Could not parse response."}
    return {
        "score": max(1, min(10, int(result.get("score", 5)))),
        "feedback": result.get("feedback", "No feedback."),
    }


def refine_post_chain(llm, post_text: str, feedback_summary: str, personality_card: str, platform: str) -> str:
    """Rewrite a post incorporating audience feedback."""
    template = load_prompt(GENERATION_PROMPTS / "refine_post.txt")
    prompt = fill_prompt(
        template,
        platform=platform,
        original_post=post_text,
        feedback_summary=feedback_summary,
        personality_card=personality_card or "Not available.",
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content.strip()
