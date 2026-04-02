"""Automated quality gate — rule-based fidelity checks with per-check reasoning."""

from __future__ import annotations

import re
import logging
from collections import Counter
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────

GENERIC_OPENINGS = [
    "everyone", "we've all", "have you ever", "in today's", "i believe",
    "i'm excited", "i'm thrilled", "i'm proud", "i'm happy to share",
    "let me tell you", "here's the thing", "hot take", "unpopular opinion",
    "real talk", "hard truth", "let that sink in", "read that again",
    "what if i told you", "imagine this", "picture this", "buckle up",
    "a thread", "story time", "the truth is", "nobody talks about",
    "most people don't", "game changer", "this changed everything",
    "in the world of",
]

HEAVY_WORDS = [
    "utilize", "leverage", "facilitate", "implement", "demonstrate",
    "encounter", "subsequently", "consequently", "nevertheless", "furthermore",
    "landscape", "navigate", "foster", "harness", "unlock", "delve",
    "tapestry", "synergy", "robust", "multifaceted", "revolutionary",
    "game-changing", "transformative", "cutting-edge", "holistic",
    "innovative", "groundbreaking", "unprecedented", "empower", "seamless",
    "paradigm", "thought leader", "best practices",
]

AI_SPECIAL_CHARS = {
    "\u2014": "em dash (—)",
    "\u2013": "en dash (–)",
}

CLICHÉ_PHRASES = [
    "rome wasn't built in a day",
    "fall seven times stand up eight",
    "journey of a thousand miles",
    "fail fast",
    "move fast and break things",
    "it takes a village",
    "two sides to every coin",
    "end of the day",
    "at the end of the day",
    "think outside the box",
    "low-hanging fruit",
    "move the needle",
    "drink the kool-aid",
    "boil the ocean",
    "bandwidth to",
]

BANNED_CLOSING_CTAs = [
    "comment", "what do you think", "share your", "let me know",
    "thoughts?", "agree?", "follow for more", "like this post",
    "drop a", "tag someone",
]


# ─────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────

def _sentences(post: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", post.strip()) if s.strip()]


def _paragraphs(post: str) -> list[str]:
    return [p.strip() for p in post.strip().split("\n\n") if p.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _check(name: str, passed: bool, reason: str) -> dict:
    """Build a single check result with reasoning."""
    return {"name": name, "passed": passed, "reason": reason}


def _repeated_ngrams(post: str, n: int = 4, threshold: int = 2) -> list[str]:
    words = re.findall(r"\b\w+\b", post.lower())
    ngrams = [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]
    return [phrase for phrase, count in Counter(ngrams).items() if count >= threshold]


def _sentence_length_variance(sentences: list[str]) -> float:
    """Coefficient of variation of sentence word counts. Low = AI-uniform."""
    if len(sentences) < 3:
        return 1.0
    lengths = [_word_count(s) for s in sentences]
    avg = sum(lengths) / len(lengths)
    if avg == 0:
        return 1.0
    variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
    return (variance ** 0.5) / avg


def _opener_word_repetition(sentences: list[str]) -> list[str]:
    openers = [s.split()[0].lower() for s in sentences if s.split()]
    return [w for w, c in Counter(openers).items() if c >= 3]


# ─────────────────────────────────────────────────────────
# INDIVIDUAL CHECKS
# ─────────────────────────────────────────────────────────

def _check_opening(post: str) -> dict:
    first = _sentences(post)[0].lower() if _sentences(post) else ""
    for bad in GENERIC_OPENINGS:
        if first.startswith(bad) or bad in first[:80]:
            return _check(
                "strong_opening", False,
                f"Opening matches generic AI/LinkedIn pattern: '{bad}'. "
                "Rewrite with a specific detail, number, or mid-scene drop."
            )
    if first.endswith("?"):
        return _check(
            "strong_opening", False,
            "Opening ends with a question — likely a rhetorical bait opener. "
            "State something instead."
        )
    return _check("strong_opening", True, "Opening avoids generic patterns.")


def _check_heavy_words(post: str) -> dict:
    found = [w for w in HEAVY_WORDS if w.lower() in post.lower()]
    if found:
        return _check(
            "no_heavy_english", False,
            f"Heavy/AI-fingerprint words found: {', '.join(found)}. "
            "Replace with simpler alternatives."
        )
    return _check("no_heavy_english", True, "No heavy English vocabulary detected.")


def _check_special_chars(post: str) -> dict:
    found = {name for char, name in AI_SPECIAL_CHARS.items() if char in post}
    if found:
        return _check(
            "no_ai_special_chars", False,
            f"AI-signature special characters found: {', '.join(found)}. "
            "Replace em/en dashes with periods or line breaks."
        )
    return _check("no_ai_special_chars", True, "No AI-signature special characters.")


def _check_banned_phrases(post: str, banned: list[str]) -> dict:
    found = [p for p in banned if p.lower() in post.lower()]
    if found:
        return _check(
            "no_banned_phrases", False,
            f"Founder's banned phrases present: {', '.join(found)}. "
            "These are hard failures — remove every instance."
        )
    return _check("no_banned_phrases", True, "No banned phrases found.")


def _check_clichés(post: str) -> dict:
    found = [c for c in CLICHÉ_PHRASES if c.lower() in post.lower()]
    if found:
        return _check(
            "no_clichés", False,
            f"Clichéd phrases found: {', '.join(found)}. "
            "Replace with the founder's own experience or cut."
        )
    return _check("no_clichés", True, "No cliché phrases detected.")


def _check_repetition(post: str) -> dict:
    repeated = _repeated_ngrams(post, n=4, threshold=2)
    opener_reps = _opener_word_repetition(_sentences(post))
    issues = []
    if repeated:
        issues.append(f"repeated 4-word phrases: {', '.join(repeated[:3])}")
    if opener_reps:
        issues.append(f"sentence openers used 3+ times: {', '.join(opener_reps)}")
    if issues:
        return _check(
            "no_repetition", False,
            f"Repetition detected — {'; '.join(issues)}. "
            "Rewrite one instance of each repeated phrase entirely."
        )
    return _check("no_repetition", True, "No phrase repetition detected.")


def _check_sentence_variety(post: str) -> dict:
    sents = _sentences(post)
    if len(sents) < 4:
        return _check("sentence_variety", True, "Too few sentences to evaluate variety.")
    cv = _sentence_length_variance(sents)
    if cv < 0.35:
        lengths = [_word_count(s) for s in sents]
        return _check(
            "sentence_variety", False,
            f"Sentence lengths are too uniform (CV={cv:.2f}). "
            f"Lengths: {lengths[:8]}. "
            "Break a long sentence into a fragment or combine two short ones."
        )
    return _check("sentence_variety", True, f"Good sentence length variation (CV={cv:.2f}).")


def _check_paragraph_variety(post: str) -> dict:
    paras = _paragraphs(post)
    if len(paras) < 3:
        return _check("paragraph_variety", True, "Not enough paragraphs to evaluate variety.")
    lengths = [_word_count(p) for p in paras]
    diffs = [abs(lengths[i] - lengths[i + 1]) for i in range(len(lengths) - 1)]
    if all(d < 10 for d in diffs):
        return _check(
            "paragraph_variety", False,
            f"All paragraphs are near-identical length: {lengths}. "
            "Mix a long paragraph with a one-liner or fragment paragraph."
        )
    return _check("paragraph_variety", True, "Paragraph lengths vary naturally.")


def _check_specifics(post: str) -> dict:
    # Numbers, percentages, dollar amounts, named entities (heuristic)
    specifics = re.findall(
        r"\$[\d,.]+[MBK%]?|\d+[%+]|\d+\+|\d{1,3}(,\d{3})+|\b\d{2,}\b days|\b\d+ (weeks|months|years)\b",
        post,
        flags=re.IGNORECASE,
    )
    if not specifics:
        return _check(
            "has_specifics", False,
            "No specific numbers, figures, or concrete data points found. "
            "Add at least one real number from the founder's experience — vague claims are skippable."
        )
    return _check("has_specifics", True, f"Specific data points present ({len(specifics)} found).")


def _check_closing(post: str) -> dict:
    lines = [l.strip() for l in post.strip().split("\n") if l.strip()]
    last = lines[-1] if lines else ""
    last_lower = last.lower()

    if last_lower.endswith("?"):
        return _check(
            "strong_closing", False,
            "Post ends with a question. Questions as closings signal weak conviction. "
            "Replace with a statement that reframes the opening tension."
        )
    for cta in BANNED_CLOSING_CTAs:
        if cta in last_lower:
            return _check(
                "strong_closing", False,
                f"Generic CTA in closing: '{cta}'. "
                "Replace with a founder-specific close — a belief, a decision, or an open loop."
            )
    return _check("strong_closing", True, "Closing avoids generic CTAs and weak question endings.")


def _check_length(post: str) -> dict:
    length = len(post)
    wc = _word_count(post)
    if length < 600:
        return _check(
            "good_length", False,
            f"Post is too short ({length} chars, {wc} words). "
            "LinkedIn posts under ~150 words rarely have enough substance to earn engagement."
        )
    if length > 2800:
        return _check(
            "good_length", False,
            f"Post is too long ({length} chars, {wc} words). "
            "Over ~600 words loses mobile readers. Cut the weakest paragraph."
        )
    return _check("good_length", True, f"Post length is good ({length} chars, {wc} words).")


def _check_founder_voice(post: str, personality_card: str, phrases_used: list[str]) -> dict:
    """Heuristic check that the post contains founder-specific signals."""
    if not personality_card and not phrases_used:
        return _check("founder_voice", True, "No founder data to check against — skipped.")

    # Check if any founder phrases appear
    phrases_present = [p for p in phrases_used if p.lower() in post.lower()]
    if not phrases_present and phrases_used:
        return _check(
            "founder_voice", False,
            f"None of the founder's signature phrases appear in the post. "
            f"Expected 1-3 of: {', '.join(phrases_used[:5])}. "
            "The post may sound generic — add one phrase that is unmistakably theirs."
        )

    # Keyword overlap with personality card (rough proxy for voice alignment)
    if personality_card:
        card_words = set(re.findall(r"\b\w{5,}\b", personality_card.lower()))
        post_words = set(re.findall(r"\b\w{5,}\b", post.lower()))
        overlap = len(card_words & post_words) / max(len(card_words), 1)
        if overlap < 0.04:
            return _check(
                "founder_voice", False,
                f"Low vocabulary overlap with founder personality card ({overlap:.1%}). "
                "The post may not sound like this specific founder. "
                "Review voice lock pass in humanizer."
            )

    return _check(
        "founder_voice", True,
        f"Founder voice signals present: {', '.join(phrases_present) if phrases_present else 'vocabulary overlap OK'}."
    )


def _check_viral_structure(post: str, viral_context: dict | None) -> dict:
    """Check if post structure aligns with viral patterns from the graph."""
    if not viral_context:
        return _check("viral_structure", True, "No viral context provided — skipped.")

    paras = _paragraphs(post)
    issues = []

    # Check hook patterns
    hooks = viral_context.get("hooks", [])
    if hooks:
        first_para = paras[0].lower() if paras else ""
        # At least one hook pattern should be loosely present in opener
        hook_match = any(
            any(kw in first_para for kw in h.get("keywords", []))
            for h in hooks
        )
        if not hook_match:
            issues.append(
                "Opening does not match any known viral hook pattern for this topic. "
                "Consider a specificity bomb, mid-story drop, or earned contradiction."
            )

    # Check pacing
    pacing = viral_context.get("pacing", {})
    if pacing:
        avg_target = pacing.get("avg_paragraph_words", 0)
        if avg_target:
            avg_actual = sum(_word_count(p) for p in paras) / max(len(paras), 1)
            if abs(avg_actual - avg_target) > 25:
                issues.append(
                    f"Paragraph pacing off: avg {avg_actual:.0f} words/paragraph vs "
                    f"viral target {avg_target} words/paragraph."
                )

    if issues:
        return _check("viral_structure", False, " | ".join(issues))
    return _check("viral_structure", True, "Post structure aligns with viral patterns.")


def _check_parallel_overuse(post: str) -> dict:
    """Detect AI's favourite pattern: 'X is not A, it's B' used 3+ times."""
    pattern = re.compile(
        r"(is not about|it'?s not about|not a .+ but a|not .+ it'?s)",
        re.IGNORECASE,
    )
    matches = pattern.findall(post)
    if len(matches) >= 3:
        return _check(
            "no_parallel_overuse", False,
            f"'X is not A, it's B' pattern used {len(matches)} times — strong AI tell. "
            "Collapse at least one instance or break the parallel."
        )
    return _check("no_parallel_overuse", True, "Parallel contrast structure not overused.")


# ─────────────────────────────────────────────────────────
# MAIN GATE
# ─────────────────────────────────────────────────────────

def quality_gate(
    post: str,
    graph,
    personality_card: str = "",
    viral_context: dict | None = None,
) -> dict:
    """Run all quality checks on a generated post.

    Args:
        post: The post text to evaluate.
        graph: Loaded founder knowledge graph.
        personality_card: Founder's personality description for voice checks.
        viral_context: Optional viral graph data for structural checks.

    Returns:
        {
            "score": int (0-100),
            "passed": bool,
            "checks": list[dict],       # each check with name, passed, reason
            "failures": list[str],      # names of failed checks
            "critical_failures": list,  # checks that alone should block publishing
            "reasoning": str,           # overall summary of what needs fixing
        }
    """
    from ..graph.query import get_vocabulary_rules

    vocab = get_vocabulary_rules(graph)
    banned_phrases = vocab.get("phrases_never", [])
    phrases_used = vocab.get("phrases_used", [])

    checks = [
        _check_opening(post),
        _check_heavy_words(post),
        _check_special_chars(post),
        _check_banned_phrases(post, banned_phrases),
        _check_clichés(post),
        _check_repetition(post),
        _check_sentence_variety(post),
        _check_paragraph_variety(post),
        _check_specifics(post),
        _check_closing(post),
        _check_length(post),
        _check_founder_voice(post, personality_card, phrases_used),
        _check_viral_structure(post, viral_context),
        _check_parallel_overuse(post),
    ]

    # Critical checks — failure on any of these should block publishing regardless of overall score
    CRITICAL = {"no_banned_phrases", "no_heavy_english", "no_ai_special_chars"}

    failures = [c["name"] for c in checks if not c["passed"]]
    critical_failures = [c for c in checks if not c["passed"] and c["name"] in CRITICAL]

    score = round(sum(c["passed"] for c in checks) / max(len(checks), 1) * 100)

    # Build reasoning summary
    if not failures:
        reasoning = "All checks passed. Post is ready."
    else:
        fail_lines = [
            f"[{c['name']}] {c['reason']}"
            for c in checks if not c["passed"]
        ]
        reasoning = f"{len(failures)} check(s) failed:\n" + "\n".join(fail_lines)

    if critical_failures:
        critical_names = [c["name"] for c in critical_failures]
        reasoning = f"CRITICAL FAILURES — publishing blocked: {', '.join(critical_names)}\n\n" + reasoning

    passed = score >= 75 and not critical_failures

    logger.info(
        "[QualityGate] score=%d passed=%s failures=%s",
        score, passed, failures
    )

    return {
        "score": score,
        "passed": passed,
        "checks": checks,
        "failures": failures,
        "critical_failures": [c["name"] for c in critical_failures],
        "reasoning": reasoning,
    }