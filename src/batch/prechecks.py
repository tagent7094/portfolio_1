"""Deterministic pre-checks for batch posts — zero LLM cost, runs before validation."""

from __future__ import annotations

import re
import logging

from .state import BatchState

logger = logging.getLogger(__name__)

VOICE_BLACKLIST = [
    "unveils", "ai-powered", "accessible communication",
    "the future of", "redefining", "excited to announce",
    "thrilled to share", "game-changing", "groundbreaking",
    "innovative solution", "cutting-edge", "revolutionizing",
    "leveraging", "synergy", "paradigm shift",
    "transformative", "best-in-class", "world-class",
    "disruptive", "seamless integration", "holistic approach",
    "in today's", "here's the thing", "let that sink in",
]


def banned_phrase_scan(text: str) -> list[str]:
    """Scan post text against corporate phrase blacklist."""
    lower = text.lower()
    return [phrase for phrase in VOICE_BLACKLIST if phrase in lower]


def word_count_check(text: str, word_count_range: tuple[int, int]) -> dict:
    """Check if post word count is within acceptable range."""
    words = len(text.split())
    lo, hi = word_count_range
    return {
        "pass": lo <= words <= hi,
        "actual": words,
        "range": (lo, hi),
    }


def marker_rate_check(text: str, expected_rates: dict) -> dict:
    """Check marker rates against founder's corpus rates.

    Expected rates are per-post averages from the founder's published corpus.
    Tolerance: ±50% of expected rate (or absolute minimum of 0.5 occurrences).
    """
    if not expected_rates:
        return {"pass": True, "violations": [], "actual_rates": {}}

    actual_rates = _compute_post_rates(text)
    violations = []

    for marker, expected in expected_rates.items():
        actual = actual_rates.get(marker, 0.0)
        if expected <= 0:
            continue
        tolerance = max(expected * 0.5, 0.5)
        if actual < expected - tolerance:
            violations.append(
                f"{marker}: expected ~{expected:.1f}/post, got {actual:.1f} (too low)"
            )

    return {
        "pass": len(violations) == 0,
        "violations": violations,
        "actual_rates": actual_rates,
    }


def _compute_post_rates(text: str) -> dict:
    """Compute formatting marker counts for a single post."""
    return {
        "em_dash": text.count("—"),
        "smiley": len(re.findall(r":\)|;\)|:D|:-\)", text)),
        "hashtag": len(re.findall(r"#\w+", text)),
    }


def story_usage_check(
    stories_declared: list[str],
    usage_counter: dict[str, int],
    max_uses: int = 3,
) -> dict:
    """Check if any declared stories exceed the usage cap."""
    overused = []
    for story in stories_declared:
        if not story:
            continue
        current = usage_counter.get(story, 0)
        if current >= max_uses:
            overused.append(f"{story} (used {current}x, max {max_uses})")
    return {
        "pass": len(overused) == 0,
        "overused": overused,
    }


def exclusion_scan(text: str, exclusions: list[str]) -> list[str]:
    """Scan post text against founder-specific exclusion phrases."""
    if not exclusions:
        return []
    lower = text.lower()
    return [phrase for phrase in exclusions if phrase in lower]


def run_all_prechecks(
    text: str,
    state: BatchState,
    stories_declared: list[str] | None = None,
) -> dict:
    """Orchestrate all deterministic pre-checks. Returns aggregate pass/fail."""
    failures = []
    details = {}

    # 1. Banned phrases
    banned = banned_phrase_scan(text)
    if banned:
        failures.append(f"Banned phrases: {', '.join(banned)}")
    details["banned_phrases"] = banned

    # 2. Word count
    wc = word_count_check(text, state.word_count_range)
    if not wc["pass"]:
        failures.append(f"Word count {wc['actual']} outside range {wc['range']}")
    details["word_count"] = wc

    # 3. Marker rates
    mr = marker_rate_check(text, getattr(state, "marker_rates", {}))
    if not mr["pass"]:
        failures.extend(mr["violations"])
    details["marker_rates"] = mr

    # 4. Story usage
    su = story_usage_check(
        stories_declared or [],
        getattr(state, "story_usage_counter", {}),
    )
    if not su["pass"]:
        failures.extend([f"Overused story: {s}" for s in su["overused"]])
    details["story_usage"] = su

    # 5. Exclusions
    exc = exclusion_scan(text, state.exclusions)
    if exc:
        failures.append(f"Exclusion hits: {', '.join(exc)}")
    details["exclusions"] = exc

    passed = len(failures) == 0
    if not passed:
        logger.info("[prechecks] FAIL: %s", "; ".join(failures[:3]))

    return {
        "pass": passed,
        "failures": failures,
        "details": details,
    }
