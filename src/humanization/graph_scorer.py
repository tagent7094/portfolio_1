"""Score a generated post based on how much it was influenced by the knowledge graph.

Traces which beliefs, stories, style rules, and vocabulary from the graph
appear in (or inspired) the final post. Also scores viral graph alignment
and penalizes repetition and AI-tell patterns.
"""

from __future__ import annotations

import re
import logging
from collections import Counter
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# FUZZY MATCHING
# ─────────────────────────────────────────────────────────

def _fuzzy_present(needle: str, haystack: str, threshold: float = 0.55) -> float:
    """Check if needle appears (possibly paraphrased) in haystack.

    Uses a sliding-window approach so short phrases aren't diluted
    by the full post length. Returns similarity score 0-1.
    """
    if not isinstance(needle, str) or not isinstance(haystack, str):
        return 0.0
    if not needle or not haystack:
        return 0.0

    needle_lower = needle.lower().strip()
    haystack_lower = haystack.lower()

    if needle_lower in haystack_lower:
        return 1.0

    words_n = needle_lower.split()
    words_h = haystack_lower.split()
    window = len(words_n) + 4

    best = 0.0
    for i in range(max(1, len(words_h) - window + 1)):
        fragment = " ".join(words_h[i : i + window])
        ratio = SequenceMatcher(None, needle_lower, fragment).ratio()
        if ratio > best:
            best = ratio
    return best


# ─────────────────────────────────────────────────────────
# REPETITION PENALTY
# ─────────────────────────────────────────────────────────

def _repetition_penalty(post: str) -> tuple[int, list[str]]:
    """Return a 0-20 penalty score and list of detected repetitions.

    Higher penalty = more repeated phrases = lower final score.
    """
    words = re.findall(r"\b\w+\b", post.lower())
    issues: list[str] = []
    penalty = 0

    for n in (4, 5, 6):
        ngrams = [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]
        for phrase, count in Counter(ngrams).items():
            if count >= 2:
                issues.append(f"repeated {n}-gram ({count}x): '{phrase}'")
                penalty += 4 * (count - 1)

    sentences = re.split(r"(?<=[.!?])\s+", post.strip())
    openers = [s.split()[0].lower() for s in sentences if s.split()]
    for word, count in Counter(openers).items():
        if count >= 3:
            issues.append(f"opener '{word}' used {count}x")
            penalty += 3

    return min(penalty, 20), issues


# ─────────────────────────────────────────────────────────
# AI-TELL PENALTY
# ─────────────────────────────────────────────────────────

AI_TELL_PATTERNS = [
    r"\u2014",           # em dash
    r"\u2013",           # en dash
    r"\bin today's\b",
    r"\blandscape\b",
    r"\bleverage\b",
    r"\bfoster\b",
    r"\bdelve\b",
    r"\btapestry\b",
    r"\bsynergy\b",
    r"\brobust\b",
    r"\bseamless\b",
    r"\bempower\b",
    r"\bparadigm\b",
    r"\bholistic\b",
    r"\bunprecedented\b",
    r"\bgroundbreaking\b",
    r"\binnovative solution",
    r"it is important to note",
    r"it is worth mentioning",
    r"in order to",
    r"the fact that",
    # Parallel triplet pattern
    r"(is not about .{5,60}it.s about .{5,60}){3,}",
]


def _ai_tell_penalty(post: str) -> tuple[int, list[str]]:
    """Return a 0-25 penalty and list of detected AI tells."""
    post_lower = post.lower()
    issues: list[str] = []
    penalty = 0

    for pattern in AI_TELL_PATTERNS:
        matches = re.findall(pattern, post_lower, re.IGNORECASE)
        if matches:
            issues.append(f"AI tell '{pattern}' found {len(matches)}x")
            penalty += 3 * len(matches)

    return min(penalty, 25), issues


# ─────────────────────────────────────────────────────────
# VIRAL GRAPH SCORING
# ─────────────────────────────────────────────────────────

def _score_viral_alignment(post: str, viral_context: dict | None) -> tuple[int, dict]:
    """Score how well the post aligns with viral graph patterns.

    Returns (score 0-100, breakdown dict).
    """
    if not viral_context:
        return 50, {"note": "No viral context provided — score defaulted to neutral 50."}

    score = 50  # start neutral
    breakdown: dict = {}

    paragraphs = [p.strip() for p in post.strip().split("\n\n") if p.strip()]
    first_para = paragraphs[0].lower() if paragraphs else ""

    # Hook alignment
    hooks = viral_context.get("hooks", [])
    if hooks:
        hook_scores: list[float] = []
        for h in hooks[:6]:
            template = h.get("template", "")
            kw = h.get("keywords", [])
            sim = _fuzzy_present(template, first_para, threshold=0.3)
            kw_match = sum(1 for k in kw if k.lower() in first_para) / max(len(kw), 1)
            hook_scores.append(max(sim, kw_match))
        best_hook = max(hook_scores) if hook_scores else 0
        hook_contribution = int(best_hook * 30)
        score += hook_contribution - 15  # neutral at 0.5 match
        breakdown["hook_alignment"] = {
            "best_match": round(best_hook, 2),
            "contribution": hook_contribution,
        }

    # Structural pattern alignment
    patterns = viral_context.get("patterns", [])
    if patterns:
        pattern_hits = 0
        for p in patterns[:4]:
            desc = p.get("description", "")
            structure = p.get("structure", "")
            if desc and _fuzzy_present(desc, post, threshold=0.35) >= 0.35:
                pattern_hits += 1
            if structure and _fuzzy_present(structure, post, threshold=0.35) >= 0.35:
                pattern_hits += 1
        pattern_contribution = min(20, pattern_hits * 5)
        score += pattern_contribution
        breakdown["structure_patterns"] = {"hits": pattern_hits, "contribution": pattern_contribution}

    # Pacing alignment
    pacing = viral_context.get("pacing", {})
    if pacing:
        target_avg = pacing.get("avg_paragraph_words", 0)
        if target_avg and paragraphs:
            words_per_para = [len(re.findall(r"\b\w+\b", p)) for p in paragraphs]
            actual_avg = sum(words_per_para) / len(words_per_para)
            diff_ratio = abs(actual_avg - target_avg) / max(target_avg, 1)
            pacing_contribution = max(-10, int((1 - diff_ratio) * 10))
            score += pacing_contribution
            breakdown["pacing"] = {
                "target_avg_words": target_avg,
                "actual_avg_words": round(actual_avg, 1),
                "contribution": pacing_contribution,
            }

    score = max(0, min(100, score))
    breakdown["final_viral_score"] = score
    return score, breakdown


# ─────────────────────────────────────────────────────────
# MAIN SCORER
# ─────────────────────────────────────────────────────────

def score_graph_influence(
    post: str,
    graph,
    topic: str,
    platform: str,
    viral_context: dict | None = None,
) -> dict:
    """Analyse how much of post was shaped by the knowledge graph, viral patterns, and founder voice.

    Args:
        post: The final post text.
        graph: Loaded founder knowledge graph.
        topic: Extracted topic string (used to query graph).
        platform: Target platform.
        viral_context: Optional viral graph context dict.

    Returns a detailed breakdown dict including overall_score (0-100).
    """
    from ..graph.query import (
        get_full_context,
        get_style_rules_for_platform,
        get_vocabulary_rules,
    )

    context = get_full_context(graph, topic, platform)
    beliefs = [d for _, d in graph.nodes(data=True) if d.get("node_type") == "belief"]
    stories = [d for _, d in graph.nodes(data=True) if d.get("node_type") == "story"]
    style_rules = context["style_rules"]
    vocab = context["vocabulary"]
    personality_card = context["personality_card"]

    # ── 1. Belief alignment ──
    belief_matched: list[dict] = []
    for b in beliefs:
        stance = b.get("stance", "")
        if not stance:
            continue
        sim = _fuzzy_present(stance, post)
        if sim >= 0.45:
            belief_matched.append({
                "id": b.get("id", "?"),
                "topic": b.get("topic", "?"),
                "stance": stance[:80],
                "confidence": b.get("confidence", 0),
                "similarity": round(sim, 2),
            })
    belief_score = min(100, int((len(belief_matched) / max(len(beliefs), 1)) * 100 * 1.5))

    # ── 2. Story influence ──
    story_matched: list[dict] = []
    for s in stories:
        title = s.get("title", "")
        summary = s.get("summary", "")
        key_quotes = s.get("key_quotes", [])
        best_sim = max(
            _fuzzy_present(title, post),
            _fuzzy_present(summary[:120], post) if summary else 0.0,
            max((_fuzzy_present(q[:80], post) for q in key_quotes), default=0.0) if key_quotes else 0.0,
        )
        if best_sim >= 0.4:
            story_matched.append({
                "id": s.get("id", "?"),
                "title": title[:60],
                "register": s.get("emotional_register", "?"),
                "similarity": round(best_sim, 2),
            })
    story_score = min(100, int((len(story_matched) / max(len(stories), 1)) * 100 * 2))

    # ── 3. Style rule adherence ──
    style_matched: list[dict] = []
    style_violated: list[dict] = []
    for r in style_rules:
        desc = r.get("description", "")
        anti = r.get("anti_pattern", "")
        rule_type = r.get("rule_type", "")

        if anti and _fuzzy_present(anti, post) >= 0.6:
            style_violated.append({
                "rule_type": rule_type,
                "description": desc[:60],
                "anti_pattern": anti[:60],
            })
            continue

        followed = rule_type in {"rhythm", "punctuation", "rhetorical_move"} or True
        if rule_type == "opening":
            first_line = post.split("\n")[0] if post else ""
            followed = len(first_line) > 10
        elif rule_type == "closing":
            last_line = post.strip().split("\n")[-1] if post else ""
            followed = len(last_line) > 10

        if followed:
            style_matched.append({"rule_type": rule_type, "description": desc[:60]})

    style_total = max(len(style_rules), 1)
    style_score = max(0, min(100, int(
        ((len(style_matched) - len(style_violated)) / style_total) * 100
    )))

    # ── 4. Vocabulary adherence ──
    phrases_used_present = [p for p in vocab.get("phrases_used", []) if p.lower() in post.lower()]
    phrases_never_violations = [p for p in vocab.get("phrases_never", []) if p.lower() in post.lower()]
    vocab_total = max(len(vocab.get("phrases_used", [])) + len(vocab.get("phrases_never", [])), 1)
    vocab_good = len(phrases_used_present) + (len(vocab.get("phrases_never", [])) - len(phrases_never_violations))
    vocab_score = min(100, int((vocab_good / vocab_total) * 100))

    # ── 5. Personality alignment ──
    if personality_card:
        card_words = set(re.findall(r"\b\w{4,}\b", personality_card.lower()))
        post_words = set(re.findall(r"\b\w{4,}\b", post.lower()))
        overlap = len(card_words & post_words) / max(len(card_words), 1)
        personality_alignment = min(100, int(overlap * 300))
    else:
        personality_alignment = 50

    # ── 6. Viral graph alignment ──
    viral_score, viral_breakdown = _score_viral_alignment(post, viral_context)

    # ── 7. Repetition penalty ──
    rep_penalty, rep_issues = _repetition_penalty(post)

    # ── 8. AI-tell penalty ──
    ai_penalty, ai_issues = _ai_tell_penalty(post)

    # ── Overall (weighted, with penalties applied after) ──
    raw_overall = int(
        belief_score * 0.20
        + story_score * 0.15
        + style_score * 0.20
        + vocab_score * 0.15
        + personality_alignment * 0.15
        + viral_score * 0.15
    )
    overall = max(0, min(100, raw_overall - rep_penalty - ai_penalty))

    # ── Human-readable breakdown ──
    lines = [
        f"Overall Graph Influence Score: {overall}/100  "
        f"(raw={raw_overall}, rep_penalty=-{rep_penalty}, ai_penalty=-{ai_penalty})",
        "",
        f"Belief Alignment    : {belief_score}/100 ({len(belief_matched)}/{len(beliefs)} beliefs reflected)",
    ]
    for bm in belief_matched:
        lines.append(f"  [{bm['topic']}] \"{bm['stance']}\" (sim={bm['similarity']})")

    lines.append(f"\nStory Influence     : {story_score}/100 ({len(story_matched)}/{len(stories)} stories used)")
    for sm in story_matched:
        lines.append(f"  \"{sm['title']}\" [{sm['register']}] (sim={sm['similarity']})")

    lines.append(f"\nStyle Adherence     : {style_score}/100 ({len(style_matched)} followed, {len(style_violated)} violated)")
    for sv in style_violated:
        lines.append(f"  VIOLATION [{sv['rule_type']}]: {sv['anti_pattern']}")

    lines.append(f"\nVocabulary          : {vocab_score}/100")
    if phrases_used_present:
        lines.append(f"  Used: {', '.join(phrases_used_present)}")
    if phrases_never_violations:
        lines.append(f"  VIOLATIONS: {', '.join(phrases_never_violations)}")

    lines.append(f"\nPersonality Align.  : {personality_alignment}/100")
    lines.append(f"\nViral Alignment     : {viral_score}/100")
    for k, v in viral_breakdown.items():
        if k != "final_viral_score":
            lines.append(f"  {k}: {v}")

    if rep_issues:
        lines.append(f"\nRepetition Penalty  : -{rep_penalty}")
        for ri in rep_issues:
            lines.append(f"  {ri}")

    if ai_issues:
        lines.append(f"\nAI-Tell Penalty     : -{ai_penalty}")
        for ai in ai_issues[:5]:
            lines.append(f"  {ai}")

    return {
        "overall_score": overall,
        "raw_score": raw_overall,
        "belief_score": {"score": belief_score, "matched": belief_matched, "total": len(beliefs)},
        "story_score": {"score": story_score, "matched": story_matched, "total": len(stories)},
        "style_score": {"score": style_score, "matched": style_matched, "violated": style_violated, "total": len(style_rules)},
        "vocab_score": {"score": vocab_score, "used": phrases_used_present, "violations": phrases_never_violations},
        "personality_alignment": personality_alignment,
        "viral_score": {"score": viral_score, "breakdown": viral_breakdown},
        "penalties": {
            "repetition": {"penalty": rep_penalty, "issues": rep_issues},
            "ai_tells": {"penalty": ai_penalty, "issues": ai_issues},
        },
        "breakdown_text": "\n".join(lines),
    }