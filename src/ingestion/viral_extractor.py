"""Extract viral patterns from parsed LinkedIn posts — statistical + LLM."""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from statistics import mean, median

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Phase A: Statistical Analysis (zero LLM cost)
# ═══════════════════════════════════════════════════════════════════

def analyze_engagement_brackets(records: list[dict]) -> dict:
    """Bucket posts by engagement percentiles."""
    if not records:
        return {"mega_viral": [], "strong": [], "moderate": []}

    sorted_r = sorted(records, key=lambda r: r["engagement_score"], reverse=True)
    n = len(sorted_r)
    cutoff_mega = max(1, int(n * 0.05))
    cutoff_strong = max(1, int(n * 0.20))

    mega = sorted_r[:cutoff_mega]
    strong = sorted_r[cutoff_mega:cutoff_strong]
    moderate = sorted_r[cutoff_strong:]

    def bracket_stats(posts, name):
        if not posts:
            return {"bracket": name, "count": 0}
        engs = [p["engagement_score"] for p in posts]
        likes = [p["likes"] for p in posts]
        comments = [p["comments"] for p in posts]
        return {
            "bracket": name,
            "count": len(posts),
            "engagement_range": f"{min(engs)}-{max(engs)}",
            "avg_engagement": round(mean(engs)),
            "median_engagement": round(median(engs)),
            "avg_likes": round(mean(likes)),
            "avg_comments": round(mean(comments)),
        }

    return {
        "mega_viral": bracket_stats(mega, "mega_viral"),
        "strong": bracket_stats(strong, "strong"),
        "moderate": bracket_stats(moderate, "moderate"),
        "brackets_data": {"mega_viral": mega, "strong": strong, "moderate": moderate},
    }


def analyze_structure_patterns(records: list[dict]) -> list[dict]:
    """Analyze post structure patterns statistically."""
    patterns = Counter()
    pattern_examples = {}
    pattern_engagement = {}

    for r in records:
        content = r["content"]
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        para_count = len(paragraphs)
        word_count = len(content.split())
        has_list = bool(re.search(r"^\d+[.)]", content, re.MULTILINE))
        has_question = "?" in content[:200]
        first_line_short = len(paragraphs[0].split()) < 15 if paragraphs else False
        ends_with_question = content.rstrip().endswith("?")

        # Build a structure fingerprint
        parts = []
        if first_line_short:
            parts.append("short_opener")
        if has_question:
            parts.append("question_hook")
        if has_list:
            parts.append("listicle")
        if ends_with_question:
            parts.append("question_close")
        if para_count <= 3:
            parts.append("compact")
        elif para_count >= 8:
            parts.append("long_form")
        else:
            parts.append("medium")

        key = "+".join(sorted(parts)) if parts else "generic"
        patterns[key] += 1

        if key not in pattern_examples:
            pattern_examples[key] = []
        if len(pattern_examples[key]) < 3:
            pattern_examples[key].append(r["post_id"])

        if key not in pattern_engagement:
            pattern_engagement[key] = []
        pattern_engagement[key].append(r["engagement_score"])

    result = []
    for pattern_key, count in patterns.most_common(20):
        engs = pattern_engagement.get(pattern_key, [0])
        result.append({
            "id": f"struct_{hashlib.md5(pattern_key.encode()).hexdigest()[:8]}",
            "template_name": pattern_key.replace("+", " + ").title(),
            "structure_description": pattern_key,
            "count": count,
            "avg_engagement": round(mean(engs)),
            "example_post_ids": pattern_examples.get(pattern_key, []),
        })

    return result


def analyze_hooks(records: list[dict]) -> list[dict]:
    """Extract and categorize opening line patterns statistically."""
    hook_categories = {
        "bold_statement": {"pattern": r"^[A-Z].*\.$", "hooks": [], "engagements": []},
        "question_opener": {"pattern": r"^.*\?$", "hooks": [], "engagements": []},
        "number_stat": {"pattern": r"^\d+%|^\$?\d+", "hooks": [], "engagements": []},
        "personal_story": {"pattern": r"^(I |My |We |Last |Yesterday|Today)", "hooks": [], "engagements": []},
        "contrarian": {"pattern": r"^(Everyone|Nobody|Stop|Don't|Unpopular)", "hooks": [], "engagements": []},
        "dramatic_short": {"pattern": r"^.{1,30}$", "hooks": [], "engagements": []},
    }

    for r in records:
        lines = r["content"].strip().split("\n")
        first_line = lines[0].strip() if lines else ""
        if not first_line:
            continue

        for cat_name, cat in hook_categories.items():
            if re.match(cat["pattern"], first_line):
                if len(cat["hooks"]) < 10:
                    cat["hooks"].append(first_line[:100])
                cat["engagements"].append(r["engagement_score"])
                break

    result = []
    for cat_name, cat in hook_categories.items():
        if not cat["engagements"]:
            continue
        result.append({
            "id": f"hook_{cat_name}",
            "hook_name": cat_name.replace("_", " ").title(),
            "template": f"[{cat_name}] pattern",
            "avg_engagement": round(mean(cat["engagements"])),
            "example_hooks": cat["hooks"][:5],
            "count": len(cat["engagements"]),
        })

    return sorted(result, key=lambda x: x["avg_engagement"], reverse=True)


# ═══════════════════════════════════════════════════════════════════
# Phase B: LLM Extraction (sampled, ~batched)
# ═══════════════════════════════════════════════════════════════════

def extract_hook_types_with_llm(llm, top_posts: list[dict], batch_size: int = 5) -> list[dict]:
    """Use LLM to categorize and abstract opening line patterns."""
    from ..utils.json_parser import parse_llm_json

    hooks = []
    sample = top_posts[:100]  # Limit to keep costs manageable

    for i in range(0, len(sample), batch_size):
        batch = sample[i:i + batch_size]
        openers = []
        for p in batch:
            lines = p["content"].strip().split("\n")
            opener = lines[0].strip() if lines else ""
            openers.append(f"- [{p['engagement_score']} engagement] {opener[:150]}")

        prompt = (
            "Analyze these viral LinkedIn post opening lines and categorize them.\n\n"
            "OPENING LINES:\n" + "\n".join(openers) + "\n\n"
            "For each distinct hook TYPE you identify, provide:\n"
            '- hook_name: short category name\n'
            '- template: abstract format (e.g., "[Stat]% of [group] [surprising claim]")\n'
            '- why_it_works: 1 sentence\n\n'
            "Return JSON array of hook types (not one per line, group similar ones):\n"
            '[{"hook_name": "...", "template": "...", "why_it_works": "..."}]'
        )

        result = parse_llm_json(llm.generate(prompt, temperature=0.3, max_tokens=1000))
        if isinstance(result, list):
            for h in result:
                h["id"] = f"hook_llm_{hashlib.md5(h.get('hook_name', '').encode()).hexdigest()[:8]}"
                h["count"] = len(batch)
                hooks.append(h)

        logger.info("  Extracted hooks from batch %d/%d", i // batch_size + 1, len(sample) // batch_size + 1)

    return hooks


def extract_viral_patterns_with_llm(llm, posts_by_bracket: dict, batch_size: int = 3) -> list[dict]:
    """Use LLM to identify recurring viral patterns across engagement brackets."""
    from ..utils.json_parser import parse_llm_json

    patterns = []

    for bracket_name in ["mega_viral", "strong"]:
        bracket_posts = posts_by_bracket.get(bracket_name, [])
        sample = bracket_posts[:50]

        for i in range(0, len(sample), batch_size):
            batch = sample[i:i + batch_size]
            posts_text = "\n---\n".join(
                f"[{p['engagement_score']} engagement]\n{p['content'][:500]}"
                for p in batch
            )

            prompt = (
                f"Analyze these {bracket_name.replace('_', ' ')} LinkedIn posts.\n\n"
                f"POSTS:\n{posts_text}\n\n"
                "Identify recurring PATTERNS that make these posts viral:\n"
                "- Structural patterns (how content is organized)\n"
                "- Rhetorical devices (contrast, callback, escalation)\n"
                "- Engagement triggers (controversy, vulnerability, authority)\n\n"
                "Return JSON array:\n"
                '[{"pattern_name": "...", "description": "...", "effectiveness": "high/medium"}]'
            )

            result = parse_llm_json(llm.generate(prompt, temperature=0.3, max_tokens=1000))
            if isinstance(result, list):
                for p in result:
                    p["id"] = f"pattern_{hashlib.md5(p.get('pattern_name', '').encode()).hexdigest()[:8]}"
                    p["bracket"] = bracket_name
                    patterns.append(p)

    return patterns


def extract_writing_techniques_with_llm(llm, top_posts: list[dict]) -> list[dict]:
    """Use LLM to identify specific writing techniques."""
    from ..utils.json_parser import parse_llm_json

    sample = top_posts[:30]
    posts_text = "\n---\n".join(
        f"[{p['engagement_score']} engagement]\n{p['content'][:400]}"
        for p in sample
    )

    prompt = (
        "Analyze these top-performing LinkedIn posts for specific WRITING TECHNIQUES.\n\n"
        f"POSTS:\n{posts_text}\n\n"
        "Identify specific techniques like:\n"
        "- One-word drama lines, callback structure, parallel construction\n"
        "- Sentence length variation, strategic whitespace, power closers\n"
        "- Specificity tactics (names, numbers, dates, places)\n\n"
        "Return JSON array:\n"
        '[{"technique_name": "...", "description": "...", "impact": "high/medium/low", '
        '"example_snippet": "..."}]'
    )

    result = parse_llm_json(llm.generate(prompt, temperature=0.3, max_tokens=2000))
    if isinstance(result, list):
        for t in result:
            t["id"] = f"tech_{hashlib.md5(t.get('technique_name', '').encode()).hexdigest()[:8]}"
        return result
    return []


def run_full_viral_extraction(records: list[dict], llm=None) -> dict:
    """Run the complete viral extraction pipeline.

    Phase A: Statistical (always runs)
    Phase B: LLM extraction (only if llm provided)
    """
    logger.info("Phase A: Statistical analysis on %d posts...", len(records))

    brackets = analyze_engagement_brackets(records)
    logger.info("  Brackets: mega=%d, strong=%d, moderate=%d",
                brackets["mega_viral"]["count"],
                brackets["strong"]["count"],
                brackets["moderate"]["count"])

    structures = analyze_structure_patterns(records)
    logger.info("  Found %d structure patterns", len(structures))

    hooks_stat = analyze_hooks(records)
    logger.info("  Found %d hook categories (statistical)", len(hooks_stat))

    result = {
        "brackets": brackets,
        "structures": structures,
        "hooks": hooks_stat,
        "patterns": [],
        "techniques": [],
    }

    if llm:
        logger.info("Phase B: LLM extraction...")
        brackets_data = brackets.get("brackets_data", {})

        top_posts = brackets_data.get("mega_viral", []) + brackets_data.get("strong", [])[:100]

        hooks_llm = extract_hook_types_with_llm(llm, top_posts)
        logger.info("  Extracted %d hook types via LLM", len(hooks_llm))
        result["hooks"].extend(hooks_llm)

        patterns = extract_viral_patterns_with_llm(llm, brackets_data)
        logger.info("  Extracted %d viral patterns via LLM", len(patterns))
        result["patterns"] = patterns

        techniques = extract_writing_techniques_with_llm(llm, top_posts[:30])
        logger.info("  Extracted %d writing techniques via LLM", len(techniques))
        result["techniques"] = techniques

    return result
