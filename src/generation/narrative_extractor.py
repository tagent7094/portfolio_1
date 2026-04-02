"""Extract narratives from podcast transcripts.

Enhanced to handle the richer output from the upgraded narrative_extract.txt
and narrative_score.txt prompts, including:
- Quality tier filtering (only A and B tier pass)
- Grounding validation
- Evidence type tracking
- Post architecture hints for downstream generation
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..llm.base import LLMProvider
from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def extract_narratives(
    transcript: str,
    llm: LLMProvider,
    persona: dict,
    beliefs_context: str = "",
) -> list[dict]:
    """Extract narrative angles from a podcast transcript using a specific agent persona.

    Returns only A-tier and B-tier angles with grounding evidence.
    """
    template = load_prompt(PROMPTS_DIR / "narrative_extract.txt")
    prompt = fill_prompt(
        template,
        persona_name=persona.get("name", "Agent"),
        persona_description=persona.get("description", ""),
        persona_bias=persona.get("bias", ""),
        transcript=transcript[:8000],  # Limit transcript length
        beliefs_context=beliefs_context,
    )

    result = llm.generate_json(prompt)

    # Normalize to list
    if isinstance(result, dict):
        result = [result]
    if not isinstance(result, list):
        return []

    # Validate and filter
    validated = []
    for narr in result:
        if not isinstance(narr, dict):
            continue

        # Must have core fields
        if not narr.get("narrative") or not narr.get("hook"):
            logger.debug("Skipping narrative without core fields: %s", narr.get("id", "?"))
            continue

        # Quality tier filter — only A and B pass
        tier = narr.get("quality_tier", "C").upper()
        if tier not in ("A", "B"):
            logger.info(
                "Filtering out C-tier narrative from %s: %s",
                persona.get("name", "?"),
                narr.get("id", "?"),
            )
            continue

        # Grounding check — must have supporting_evidence
        if not narr.get("supporting_evidence"):
            logger.info(
                "Filtering out ungrounded narrative from %s: %s",
                persona.get("name", "?"),
                narr.get("id", "?"),
            )
            continue

        # Ensure defaults for new fields
        narr.setdefault("id", f"narr_{len(validated)}")
        narr.setdefault("angle", "")
        narr.setdefault("evidence_type", "unknown")
        narr.setdefault("relevant_topics", [])
        narr.setdefault("risk_level", "low")
        narr.setdefault("risk_note", None)
        narr.setdefault("tier_justification", "")
        narr.setdefault("post_architecture_hint", "")

        validated.append(narr)

    logger.info(
        "Agent %s extracted %d narratives (%d passed quality/grounding filter)",
        persona.get("name", "?"),
        len(result),
        len(validated),
    )
    return validated


def score_narrative(
    narrative: dict,
    llm: LLMProvider,
    persona: dict,
    beliefs_context: str = "",
) -> dict:
    """Score a narrative angle using a specific agent persona.

    Uses the enhanced narrative_score.txt with 5 dimensions
    (safety, traction, alignment, freshness, groundedness).
    """
    template = load_prompt(PROMPTS_DIR / "narrative_score.txt")

    # Build a richer narrative representation for scoring
    narrative_text_parts = [
        f"Narrative: {narrative.get('narrative', '')}",
        f"Angle: {narrative.get('angle', '')}",
        f"Hook: {narrative.get('hook', '')}",
    ]
    if narrative.get("supporting_evidence"):
        narrative_text_parts.append(f"Evidence: {narrative['supporting_evidence']}")
    if narrative.get("evidence_type"):
        narrative_text_parts.append(f"Evidence type: {narrative['evidence_type']}")
    if narrative.get("quality_tier"):
        narrative_text_parts.append(f"Proposed tier: {narrative['quality_tier']}")

    prompt = fill_prompt(
        template,
        persona_name=persona.get("name", "Agent"),
        persona_description=persona.get("description", ""),
        narrative="\n".join(narrative_text_parts),
        beliefs_context=beliefs_context,
    )

    result = llm.generate_json(prompt)
    if not isinstance(result, dict):
        return {}

    # Ensure all expected dimensions exist
    for dim in ("safety", "traction", "alignment", "freshness", "groundedness"):
        result.setdefault(dim, 5)
        result[dim] = max(0, min(10, result[dim]))

    # Compute composite if not present
    if "composite" not in result:
        result["composite"] = round(
            result["safety"] * 0.15
            + result["traction"] * 0.25
            + result["alignment"] * 0.25
            + result["freshness"] * 0.20
            + result["groundedness"] * 0.15,
            2,
        )

    result.setdefault("verdict", "needs_work")
    result.setdefault("one_line_reason", "")
    result.setdefault("interaction_flag", None)
    result.setdefault("upgrade_path", None)

    return result
