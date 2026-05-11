"""Exclusion scanner — prevents reuse of retired stories, scenes, or phrases."""

from __future__ import annotations

import logging
from pathlib import Path

from .state import AmplifiedPost

logger = logging.getLogger(__name__)

FOUNDERS_DIR = Path(__file__).parent.parent.parent / "data" / "founders"


def load_exclusions(founder_slug: str) -> list[str]:
    """Load exclusion phrases from the founder's exclusions.md file.

    Format: one phrase per line, # for comments, blank lines ignored.
    """
    path = FOUNDERS_DIR / founder_slug / "exclusions.md"
    if not path.exists():
        return []

    exclusions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        exclusions.append(line.lower())

    if exclusions:
        logger.info("[exclusions] Loaded %d exclusion phrases for %s", len(exclusions), founder_slug)
    return exclusions


def scan_for_exclusions(post: AmplifiedPost, exclusions: list[str]) -> list[str]:
    """Scan a post's text against exclusion phrases. Returns list of matched phrases."""
    if not exclusions:
        return []
    lower = post.text.lower()
    return [phrase for phrase in exclusions if phrase in lower]
