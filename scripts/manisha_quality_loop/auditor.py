"""10-parameter hybrid auditor for Batch A posts.

Programmatic checks for objective parameters (P1, P2, P5, P7, P8, P9, P10).
Haiku LLM judge for subjective parameters (P3 coherence, P4 anchor quality,
P6 voice fit) — saves reasoning to artifacts.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.batch.state import AmplifiedPost, BatchState
from src.batch.amplifier import _mechanic_matches_door, _normalize_mechanic
from src.batch.pack_generator import (
    _extract_forbidden_tokens,
    _scan_batch_a_for_token_leaks,
)
from src.batch.voice_validator import check_anchor_specificity, check_closer_shape
from src.utils.json_parser import parse_llm_json

logger = logging.getLogger(__name__)


# Manisha voice markers (regex patterns observed in the audit's high-scoring posts).
MANISHA_VOICE_PATTERNS = [
    re.compile(r"\bI've watched\b|\bI've sat through\b|\bI keep hearing\b|\bI keep seeing\b", re.I),
    re.compile(r"\bNot because\b.{1,40}\bBecause\b", re.I),
    re.compile(r"(?:\n|^)And\b", re.I),
    re.compile(r"\b[A-Z]{2,}\b"),  # capitalized emphasis on a single word
    re.compile(r"\bThe real\b.{1,40}\bis\b", re.I),
    re.compile(r"(?:\n|^).{1,80}[.!?]\s*$\n\n", re.MULTILINE),  # short standalone paragraph
    re.compile(r"^-\s|^\d+\.\s", re.MULTILINE),  # bullet or numbered
    re.compile(r"^(?:CROs?|SEs?|AEs?|Founders?|PMs?|VPs?):\s", re.MULTILINE | re.I),
]

BANNED_PHRASES = [
    "you're already behind",
    "let that sink in",
    "here's the thing",
    "hot take",
    "in today's",
    "leveraging",
    "synergy",
    "game-changing",
    "groundbreaking",
    "cutting-edge",
]


def _to_pass_dict(score: int, reason: str) -> dict:
    return {"score": score, "pass": score >= 9, "reason": reason}


# ---------------------------------------------------------------------------
# Programmatic parameter checks
# ---------------------------------------------------------------------------

def _audit_p1_mechanic(post: AmplifiedPost, dissection: dict) -> dict:
    source_mech = dissection.get("hook_mechanic_primary", "")
    post_mech = post.actual_mechanic or _normalize_mechanic(post.mechanic)
    if not source_mech:
        return _to_pass_dict(7, "no source mechanic to compare")
    if _normalize_mechanic(post_mech) == _normalize_mechanic(source_mech):
        return _to_pass_dict(10, f"exact match ({post_mech})")
    if _mechanic_matches_door(post_mech, source_mech):
        return _to_pass_dict(7, f"same family (post={post_mech}, source={source_mech})")
    return _to_pass_dict(3, f"different mechanic (post={post_mech}, source={source_mech})")


def _audit_p2_substitution(post: AmplifiedPost, dissection: dict, source_post: str) -> dict:
    forbidden = _extract_forbidden_tokens(dissection, source_post)
    leaks = _scan_batch_a_for_token_leaks(post, forbidden)
    if not leaks:
        return _to_pass_dict(10, "no source tokens in opener")
    if len(leaks) == 1:
        return _to_pass_dict(5, f"1 leak: {leaks[0]}")
    return _to_pass_dict(0, f"{len(leaks)} leaks: {leaks}")


def _audit_p4_anchor(post: AmplifiedPost) -> dict:
    result = check_anchor_specificity(post)
    if result.get("tier") == 1:
        return _to_pass_dict(10, "tier1_operating_rule")
    if result.get("tier") == 2:
        return _to_pass_dict(9, "tier2_named_scene")
    return _to_pass_dict(4, f"no_tier ({result.get('reason', '')})")


def _audit_p5_closer(post: AmplifiedPost) -> dict:
    result = check_closer_shape(post)
    score = min(10, max(0, int(result.get("score", 0) * 2.5)))
    return _to_pass_dict(score, result.get("reason", ""))


def _audit_p7_source_mirror(post: AmplifiedPost, dissection: dict) -> dict:
    sentences = re.split(r"(?<=[.!?])\s+", post.text.split("\n\n")[0].strip())
    post_sent_count = len([s for s in sentences if s.strip()])
    source_sent_count = dissection.get("sentence_count", 1) or 1

    sent_match = abs(post_sent_count - source_sent_count) <= 1

    source_body = (dissection.get("body_format") or "").lower()
    if source_body == "numbered_list":
        post_has_numbered = bool(re.search(r"^\d+[\.\)]\s", post.text, re.MULTILINE))
        body_match = post_has_numbered
    elif source_body == "bullet_list":
        post_has_bullets = bool(re.search(r"^[-•]\s", post.text, re.MULTILINE))
        body_match = post_has_bullets
    else:
        body_match = True

    if sent_match and body_match:
        return _to_pass_dict(10, f"sentences={post_sent_count}/{source_sent_count}, body_match={body_match}")
    if sent_match or body_match:
        return _to_pass_dict(7, f"partial (sent={sent_match}, body={body_match})")
    return _to_pass_dict(4, f"sentences={post_sent_count}/{source_sent_count}, body_fmt mismatch")


def _audit_p8_variant_application(post: AmplifiedPost) -> dict:
    gates = post.gates or {}
    critical_failed = (
        not gates.get("source_mirror", True)
        or not gates.get("coherence", True)
        or not gates.get("voice_fit", True)
    )
    replaced = (post.original_opening or "").strip() != (post.final_opening or "").strip()

    if not critical_failed:
        return _to_pass_dict(10, "all_gates_pass_preservation_correct")
    if replaced:
        return _to_pass_dict(10, "critical_fail_variant_applied")
    return _to_pass_dict(0, "critical_fail_but_original_kept")


def _audit_p9_word_count(post: AmplifiedPost) -> dict:
    wc = post.word_count or len((post.text or "").split())
    if 180 <= wc <= 280:
        return _to_pass_dict(10, f"{wc} words (in 180-280 band)")
    if 160 <= wc < 180 or 280 < wc <= 320:
        return _to_pass_dict(7, f"{wc} words (near band)")
    return _to_pass_dict(4, f"{wc} words (outside band)")


def _audit_p10_exclusion(post: AmplifiedPost, sibling_posts: list[AmplifiedPost]) -> dict:
    text_lower = (post.text or "").lower()
    hits = [phrase for phrase in BANNED_PHRASES if phrase in text_lower]

    # Cross-post closer uniqueness across the 3 A posts.
    my_closer = " ".join((post.text or "").strip().split()[-15:]).lower()
    duplicate_closers = sum(
        1 for sibling in sibling_posts
        if sibling.label != post.label
        and " ".join((sibling.text or "").strip().split()[-15:]).lower() == my_closer
    )

    if hits:
        return _to_pass_dict(2, f"banned_phrases: {hits}")
    if duplicate_closers:
        return _to_pass_dict(6, f"closer matches {duplicate_closers} sibling post(s)")
    return _to_pass_dict(10, "no_banned_phrases, unique closer")


# ---------------------------------------------------------------------------
# LLM-judge parameters (Haiku)
# ---------------------------------------------------------------------------

def _llm_judge(llm_judge, prompt: str, label: str, stage: str) -> dict:
    """Single Haiku call returning {score 0-10, reason}."""
    try:
        response = llm_judge.generate(prompt, temperature=0.2, max_tokens=400, thinking_budget=0)
    except Exception as e:
        logger.warning("[auditor] %s %s: LLM judge error %s — defaulting score=5", label, stage, e)
        return {"score": 5, "reason": f"judge_error: {e}"}

    result = parse_llm_json(response)
    if not isinstance(result, dict):
        return {"score": 5, "reason": f"parse_failed: {response[:120]}"}
    score = int(result.get("score", 5))
    score = max(0, min(10, score))
    return {"score": score, "reason": result.get("reason", "")[:300]}


def _audit_p3_coherence(post: AmplifiedPost, llm_judge) -> dict:
    """Does the opener accurately set up what the body delivers?"""
    prompt = f"""You are a content quality auditor. Score this LinkedIn post on ONE dimension only: COHERENCE between opener and body.

A 10/10 post: the opener accurately previews what the body delivers — no bait-and-switch, no broken promise.
A 0/10 post: the opener teases X (e.g. a named person's story), the body delivers Y (an unrelated thesis).

Post:
---
{(post.text or "")[:1500]}
---

Return JSON only:
{{"score": <0-10 integer>, "reason": "<one sentence explaining the score>"}}"""
    result = _llm_judge(llm_judge, prompt, post.label, "P3_coherence")
    return _to_pass_dict(result["score"], result["reason"])


def _audit_p6_voice_fit(post: AmplifiedPost, state: BatchState, llm_judge) -> dict:
    """Hybrid: count documented Manisha markers (regex floor) + LLM judge for register match."""
    text = post.text or ""
    marker_count = sum(1 for pat in MANISHA_VOICE_PATTERNS if pat.search(text))

    programmatic_floor = min(10, marker_count * 2)  # 5 markers = 10/10 floor

    calibration = (state.calibration_paragraph or "")[:600]
    prompt = f"""You are a voice auditor. The founder's voice is best captured by this calibration paragraph:

CALIBRATION (this is exactly how the founder sounds):
{calibration}

Score how well the post below matches that voice's register, posture, and rhythm.
10/10 = indistinguishable from founder's documented voice.
0/10 = corporate / generic thought-leader / AI-slop register.

Post:
---
{text[:1500]}
---

Return JSON only:
{{"score": <0-10 integer>, "reason": "<one sentence>"}}"""
    judge = _llm_judge(llm_judge, prompt, post.label, "P6_voice_fit")

    final_score = min(10, max(programmatic_floor, judge["score"]))
    return _to_pass_dict(
        final_score,
        f"markers={marker_count}, judge={judge['score']} ({judge['reason']})",
    )


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------

def audit_post(
    post: AmplifiedPost,
    sibling_posts: list[AmplifiedPost],
    source_post: str,
    dissection: dict,
    state: BatchState,
    llm_judge,
) -> dict:
    """Score one post against all 10 parameters. Returns:

    {
        "label": "A1",
        "P1": {...}, "P2": {...}, ..., "P10": {...},
        "avg": float,
        "all_pass": bool,
        "failing": ["P3", "P4"],
    }
    """
    scores = {
        "P1": _audit_p1_mechanic(post, dissection),
        "P2": _audit_p2_substitution(post, dissection, source_post),
        "P3": _audit_p3_coherence(post, llm_judge),
        "P4": _audit_p4_anchor(post),
        "P5": _audit_p5_closer(post),
        "P6": _audit_p6_voice_fit(post, state, llm_judge),
        "P7": _audit_p7_source_mirror(post, dissection),
        "P8": _audit_p8_variant_application(post),
        "P9": _audit_p9_word_count(post),
        "P10": _audit_p10_exclusion(post, sibling_posts),
    }
    score_values = [s["score"] for s in scores.values()]
    avg = sum(score_values) / len(score_values)
    failing = [k for k, v in scores.items() if not v["pass"]]
    return {
        "label": post.label,
        **scores,
        "avg": avg,
        "all_pass": len(failing) == 0,
        "failing": failing,
    }


def audit_pack(
    posts: list[AmplifiedPost],
    source_post: str,
    dissection: dict,
    state: BatchState,
    llm_judge,
) -> dict:
    """Audit all 3 posts. Returns dict with per-post + pack-level stats."""
    audits = [audit_post(p, posts, source_post, dissection, state, llm_judge) for p in posts]
    pack_avg = sum(a["avg"] for a in audits) / len(audits) if audits else 0.0
    all_pass = all(a["all_pass"] for a in audits)
    unique_texts = len({p.text for p in posts if p.text})
    return {
        "pack_avg": pack_avg,
        "all_pass": all_pass,
        "unique_post_count": unique_texts,
        "per_post": audits,
    }


def serialize_audit(audit: dict) -> str:
    """Compact JSON serialization for scores.json."""
    return json.dumps(audit, indent=2, default=str)
