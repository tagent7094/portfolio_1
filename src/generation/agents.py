"""Agent swarm for narrative extraction, scoring, and post generation.

Enhanced to use the full scoring pipeline:
- 5-dimension narrative scoring (including groundedness)
- 5-dimension post scoring (including ai_slop_detection)
- Verdict-based filtering (kill/needs_work/publish/strong_publish)
- Weighted composites instead of raw sums
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from ..llm.base import LLMProvider
from ..graph.query import get_personality_card
from ..utils.text_utils import load_prompt, fill_prompt
from .narrative_extractor import extract_narratives, score_narrative
from .post_generator import generate_post_variants
from .voting import (
    aggregate_narrative_scores,
    aggregate_post_scores,
    pick_winner,
    pick_top_n,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_personas(config_path: str = "config/agent-personas.yaml") -> list[dict]:
    """Load agent personas from config."""
    path = Path(config_path)
    if not path.exists():
        path = Path(__file__).parent.parent.parent / config_path
    with open(path) as f:
        config = yaml.safe_load(f)
    return config.get("personas", [])


class AgentSwarm:
    def __init__(self, llm: LLMProvider, graph, personas: list[dict] | None = None):
        self.llm = llm
        self.graph = graph
        self.personas = personas or _load_personas()

    def _beliefs_context(self) -> str:
        """Get beliefs summary for agent context."""
        beliefs = [
            d for _, d in self.graph.nodes(data=True) if d.get("node_type") == "belief"
        ]
        return "\n".join(
            f"- {b.get('topic', '?')}: {b.get('stance', '?')}" for b in beliefs[:20]
        )

    def extract_and_vote_narrative(self, transcript: str) -> tuple[dict, dict]:
        """Phase 1-2: Each agent extracts narratives, then cross-scores them.

        Returns (winning_narrative, all_scores).
        Narratives that score 'kill' verdict are filtered out.
        """
        beliefs_ctx = self._beliefs_context()

        # ── Phase 1: Each agent extracts narratives ──
        all_narratives = []
        for persona in self.personas:
            logger.info("Agent %s extracting narratives...", persona["name"])
            narrs = extract_narratives(transcript, self.llm, persona, beliefs_ctx)
            for n in narrs:
                n["proposed_by"] = persona["id"]
            all_narratives.extend(narrs)

        if not all_narratives:
            logger.warning("No narratives extracted by any agent")
            return {}, {}

        # Deduplicate by ID
        unique = {}
        for n in all_narratives:
            nid = n.get("id", str(len(unique)))
            if nid not in unique:
                unique[nid] = n
            else:
                # If duplicate, keep the one with higher quality tier
                existing_tier = unique[nid].get("quality_tier", "C")
                new_tier = n.get("quality_tier", "C")
                if new_tier < existing_tier:  # A < B < C in string comparison
                    unique[nid] = n
        narratives = list(unique.values())

        logger.info(
            "Extracted %d total narratives, %d unique after dedup",
            len(all_narratives), len(narratives),
        )

        # ── Phase 2: Cross-evaluation ──
        scores = {}
        for narr in narratives:
            nid = narr.get("id", "unknown")
            agent_scores = []
            for persona in self.personas:
                logger.info("Agent %s scoring narrative %s...", persona["name"], nid)
                s = score_narrative(narr, self.llm, persona, beliefs_ctx)
                agent_scores.append(s)
            scores[nid] = aggregate_narrative_scores(agent_scores)

        # ── Filter out 'kill' verdicts ──
        viable_ids = [
            nid for nid, s in scores.items()
            if s.get("verdict") not in ("kill",)
        ]

        if not viable_ids:
            logger.warning("All narratives received 'kill' verdict")
            # Fall back to the least-bad option
            viable_ids = list(scores.keys())

        viable_scores = {nid: scores[nid] for nid in viable_ids}

        # ── Pick winner ──
        winner_id = pick_winner(viable_scores)
        winner = next((n for n in narratives if n.get("id") == winner_id), narratives[0])

        agg = scores.get(winner_id, {})
        logger.info(
            "Winning narrative: %s (composite=%.2f, verdict=%s, weakest=%s)",
            winner_id,
            agg.get("composite", 0),
            agg.get("verdict", "?"),
            agg.get("weakest_dimension", "?"),
        )

        return winner, scores

    def generate_and_vote_posts(
        self, narrative: dict, platform: str, topic: str = ""
    ) -> tuple[dict, dict]:
        """Phase 3: Generate post variants and vote on best.

        Uses the enhanced score_post prompt with 5 dimensions
        including ai_slop_detection.
        """
        posts = generate_post_variants(narrative, platform, self.graph, self.llm, topic)

        if not posts:
            return {}, {}

        # Score each post with each agent
        personality_card = get_personality_card(self.graph)
        scores = {}

        for post in posts:
            pid = post["id"]
            agent_scores = []

            for persona in self.personas:
                logger.info("Agent %s scoring post %s...", persona["name"], pid)
                template = load_prompt(PROMPTS_DIR / "score_post.txt")
                prompt = fill_prompt(
                    template,
                    persona_name=persona["name"],
                    persona_description=persona["description"],
                    post=post["text"],
                    personality_card=personality_card or "Not available.",
                )
                s = self.llm.generate_json(prompt)
                if isinstance(s, dict):
                    agent_scores.append(s)
                else:
                    agent_scores.append({})

            scores[pid] = aggregate_post_scores(agent_scores)

        # Pick winner with humanness tiebreaker
        winner_id = pick_winner(scores, prefer_human=True)
        winner = next((p for p in posts if p["id"] == winner_id), posts[0])

        agg = scores.get(winner_id, {})
        logger.info(
            "Winning post: %s (composite=%.2f, publish_ready=%s, "
            "weakest=%s, slop_flags=%d)",
            winner_id,
            agg.get("composite", 0),
            agg.get("publish_ready", False),
            agg.get("weakest_dimension", "?"),
            len(agg.get("ai_slop_flags", [])),
        )

        return winner, scores
