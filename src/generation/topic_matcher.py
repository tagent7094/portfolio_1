"""Match viral topics to the founder's knowledge graph.

Enhanced to handle the richer output from the upgraded match_topic.txt prompt:
- Credibility anchor validation
- Stress test result gating (2+ fails = auto no_match)
- Angle expiration tracking
- Register reasoning
- Risk notes for medium/high risk angles
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..llm.base import LLMProvider
from ..graph.query import get_beliefs_for_topic, get_personality_card
from ..utils.text_utils import load_prompt, fill_prompt

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

VALID_REGISTERS = {
    "controlled_anger",
    "quiet_authority",
    "earned_vulnerability",
    "generosity",
    "playful_provocation",
    "paranoid_optimist",
}


def _validate_match_result(result: dict) -> dict:
    """Validate and normalize the match result from the LLM.

    Applies programmatic checks on top of the LLM's own stress test.
    """
    if not isinstance(result, dict):
        return {"no_match": True, "reason": "LLM returned invalid format."}

    # Explicit no_match from LLM
    if result.get("no_match"):
        return result

    # Must have a suggested angle
    if not result.get("suggested_angle"):
        return {"no_match": True, "reason": "No angle was generated."}

    # Must have a credibility anchor
    if not result.get("credibility_anchor") and not result.get("why_only_them"):
        logger.warning("Match result has no credibility anchor — angle may be generic.")

    # Validate register
    register = result.get("recommended_register", "quiet_authority")
    if register not in VALID_REGISTERS:
        logger.warning("Unknown register '%s' — defaulting to quiet_authority", register)
        result["recommended_register"] = "quiet_authority"

    # Validate risk level
    risk = result.get("risk_level", "low")
    if risk not in ("low", "medium", "high"):
        result["risk_level"] = "medium"

    # Check stress test results if present
    stress = result.get("stress_test_results", {})
    if stress:
        fails = sum(1 for v in stress.values() if isinstance(v, str) and v.startswith("fail"))
        if fails >= 2:
            logger.info("Stress test produced %d fails — converting to no_match", fails)
            return {
                "no_match": True,
                "reason": f"Angle failed {fails} stress tests: {json.dumps(stress)}",
                "original_angle": result.get("suggested_angle"),
            }

    # Defaults for new fields
    result.setdefault("credibility_anchor", result.get("why_only_them", ""))
    result.setdefault("register_reasoning", "")
    result.setdefault("risk_note", None)
    result.setdefault("angle_expiration", "days")
    result.setdefault("mainstream_takes_to_avoid", [])
    result.setdefault("stress_test_results", {})
    result.setdefault("matched_beliefs", [])
    result.setdefault("supporting_stories", [])
    result.setdefault("hook_seed", "")
    result.setdefault("contrast_pair", "")

    return result


def match_topic_to_graph(
    topic: str,
    graph,
    vector_store,
    llm: LLMProvider,
) -> dict:
    """Given a viral topic, find the founder's unique angle on it.

    Pipeline:
    1. Search vector store for similar past content (avoid repeating ourselves)
    2. Query graph for related beliefs, stories, and mental models
    3. Use LLM with the enhanced match_topic prompt to find the best angle
    4. Validate the result (stress test gating, credibility check)
    """
    # ── Step 1: Vector search for similar past content ──
    similar_content = []
    if vector_store and vector_store.count() > 0:
        from ..vectors.embedder import Embedder
        embedder = Embedder()
        query_emb = embedder.embed([topic])[0]
        results = vector_store.search(query_embedding=query_emb, n_results=5)
        if results and results.get("documents"):
            similar_content = results["documents"][0]

    # ── Step 2: Graph queries ──
    beliefs = get_beliefs_for_topic(graph, topic)

    stories = [
        d for _, d in graph.nodes(data=True) if d.get("node_type") == "story"
    ][:10]

    models = [
        d for _, d in graph.nodes(data=True) if d.get("node_type") == "thinking_model"
    ][:5]

    # Also get contrast pairs if available
    contrast_pairs = [
        d for _, d in graph.nodes(data=True) if d.get("node_type") == "contrast_pair"
    ][:5]

    # ── Step 3: LLM matching ──
    template = load_prompt(PROMPTS_DIR / "match_topic.txt")

    # Build models text — include contrast pairs
    models_text_parts = [
        f"- {m.get('name', '?')}: {m.get('description', '?')}" for m in models
    ]
    for cp in contrast_pairs:
        models_text_parts.append(
            f"- Contrast: {cp.get('left', '?')} vs {cp.get('right', '?')}: {cp.get('description', '')}"
        )

    prompt = fill_prompt(
        template,
        topic=topic,
        beliefs="\n".join(
            f"- [{b.get('id', '?')}] {b.get('topic', '?')}: {b.get('stance', '?')}"
            for b in beliefs[:15]
        ) or "No related beliefs found.",
        stories="\n".join(
            f"- [{s.get('id', '?')}] {s.get('title', '?')}: {s.get('summary', '?')}"
            for s in stories
        ) or "No stories available.",
        models="\n".join(models_text_parts) or "No thinking models found.",
    )

    result = llm.generate_json(prompt)
    if not isinstance(result, dict):
        result = {"no_match": True, "reason": "LLM returned invalid format."}

    # ── Step 4: Validate ──
    result = _validate_match_result(result)

    # Attach similar content for deduplication awareness
    result["similar_past_content"] = similar_content[:3]

    # Log outcome
    if result.get("no_match"):
        logger.info("Topic '%s' — no match: %s", topic[:60], result.get("reason", "?"))
    else:
        logger.info(
            "Topic '%s' — matched with register=%s, risk=%s, expiration=%s",
            topic[:60],
            result.get("recommended_register"),
            result.get("risk_level"),
            result.get("angle_expiration"),
        )

    return result
