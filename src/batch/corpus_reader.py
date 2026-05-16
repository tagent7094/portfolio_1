"""Deep corpus reading — internalize founder voice for batch generation."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..customizer.founder_loader import load_raw_founder_data
from ..graph.store import load_graph
from ..graph.query import get_deep_founder_context, get_personality_card
from ..llm.base import LLMProvider
from .state import BatchState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def compute_word_count_stats(posts_text: str) -> dict:
    """Parse posts and compute word count statistics."""
    posts = _split_posts(posts_text)
    if not posts:
        return {"median": 230, "min": 130, "max": 400, "count": 0}

    counts = sorted(len(p.split()) for p in posts if len(p.split()) > 20)
    if not counts:
        return {"median": 230, "min": 130, "max": 400, "count": 0}

    mid = len(counts) // 2
    median = counts[mid] if len(counts) % 2 else (counts[mid - 1] + counts[mid]) // 2
    return {
        "median": median,
        "min": min(counts),
        "max": max(counts),
        "count": len(counts),
    }


def _split_posts(text: str) -> list[str]:
    """Split a text file of LinkedIn posts into individual posts."""
    if not text:
        return []
    separators = ["\n---\n", "\n===\n", "\n\n\n"]
    for sep in separators:
        if sep in text:
            return [p.strip() for p in text.split(sep) if p.strip() and len(p.strip()) > 50]
    paragraphs = text.split("\n\n")
    posts = []
    current = []
    for p in paragraphs:
        current.append(p)
        if len("\n\n".join(current).split()) > 80:
            posts.append("\n\n".join(current))
            current = []
    if current:
        posts.append("\n\n".join(current))
    return [p for p in posts if len(p.split()) > 20]


def compute_marker_rates(posts: list[str]) -> dict:
    """Compute per-post averages of formatting markers across the founder's corpus.

    Returns rates like {"em_dash": 1.8, "smiley": 0.4, "hashtag": 0.0} meaning
    the founder uses ~1.8 em-dashes per post on average.
    """
    if not posts:
        return {}

    em_dash_total = 0
    smiley_total = 0
    hashtag_total = 0

    for post in posts:
        em_dash_total += post.count("—")
        smiley_total += len(re.findall(r":\)|;\)|:D|:-\)", post))
        hashtag_total += len(re.findall(r"#\w+", post))

    n = len(posts)
    return {
        "em_dash": round(em_dash_total / n, 2),
        "smiley": round(smiley_total / n, 2),
        "hashtag": round(hashtag_total / n, 2),
    }


def _internalization_hash(state: BatchState) -> str:
    """Hash the inputs that determine internalization output.

    Includes the new bundle fields (identity, transcripts, top posts, cast, scenes,
    milestones) so the cache invalidates correctly when richer data arrives.
    """
    founder_ctx = state.founder_ctx
    raw = state.raw_data
    identity = raw.get("identity") or {}
    parts = [
        state.personality_card[:3000],
        str(founder_ctx.get("beliefs", [])[:30]),
        str(founder_ctx.get("stories", [])[:20]),
        str(founder_ctx.get("contrast_pairs", [])[:15]),
        str(founder_ctx.get("thinking_models", [])[:10]),
        str(founder_ctx.get("cast", [])[:10]),
        str(founder_ctx.get("scenes", [])[:5]),
        str(founder_ctx.get("milestones", [])[:10]),
        raw.get("raw_voice_dna", "")[:4000],
        raw.get("raw_story_bank", "")[:4000],
        raw.get("founder_posts_sample", "")[:8000],
        raw.get("transcripts", "")[:4000],
        identity.get("bio", "")[:2000],
        identity.get("tensions", "")[:2000],
    ]
    return hashlib.sha256("||".join(parts).encode()).hexdigest()


def _internalization_cache_path(slug: str) -> Path:
    return Path(__file__).parent.parent.parent / "data" / "founders" / slug / ".internalization_cache.json"


def internalize_corpus(llm: LLMProvider, state: BatchState) -> dict:
    """Run deep corpus internalization via LLM — extracts voice markers, formatting, scenes, tensions."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("internalize")
    input_hash = _internalization_hash(state)
    cache_file = _internalization_cache_path(state.founder_slug)
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("hash") == input_hash:
                logger.info("[batch] Using cached internalization (hash match)")
                return cached["result"]
        except Exception:
            pass

    founder_ctx = state.founder_ctx
    raw = state.raw_data
    identity = raw.get("identity") or {}

    # Select v2 prompt when identity assets are present (bio OR tensions OR
    # graph-supplied cast/scenes/milestones). Falls back to v1 for founders
    # not yet migrated to the new layout.
    has_identity_assets = bool(
        identity.get("bio") or identity.get("tensions")
        or founder_ctx.get("cast") or founder_ctx.get("scenes")
        or founder_ctx.get("milestones")
    )
    template_name = "corpus_internalize_v2.txt" if has_identity_assets else "corpus_internalize.txt"
    template = load_prompt(PROMPTS_DIR / template_name)

    beliefs_text = "\n".join(
        f"- {b.get('topic', '') or b.get('label', '')}: {b.get('stance', '') or b.get('description', '')}"
        for b in founder_ctx.get("beliefs", [])[:30]
    )
    stories_text = "\n".join(
        f"- {s.get('title', '') or s.get('label', '')}: {(s.get('content') or s.get('description') or s.get('summary', ''))[:200]}"
        for s in founder_ctx.get("stories", [])[:20]
    )
    contrast_text = "\n".join(
        f"- {c.get('left', '')} vs {c.get('right', '')}: {c.get('description', '')[:150]}"
        for c in founder_ctx.get("contrast_pairs", [])[:15]
    )
    models_text = "\n".join(
        f"- {m.get('name', '')}: {m.get('description', '')[:150]}"
        for m in founder_ctx.get("thinking_models", [])[:10]
    )

    posts_sample = raw.get("founder_posts_sample", "")[:8000]

    fill_kwargs = dict(
        personality_card=state.personality_card[:3000],
        beliefs=beliefs_text,
        stories=stories_text,
        contrast_pairs=contrast_text,
        thinking_models=models_text,
        raw_voice_dna=raw.get("raw_voice_dna", "")[:4000],
        raw_story_bank=raw.get("raw_story_bank", "")[:4000],
        founder_posts_sample=posts_sample,
    )

    if template_name == "corpus_internalize_v2.txt":
        cast_text = "\n".join(
            f"- {c.get('name', '') or c.get('label', '')}: {c.get('description', '')[:150]}"
            for c in founder_ctx.get("cast", [])[:10]
        ) or "(none — graph has no cast nodes)"
        scenes_text = "\n".join(
            f"- {s.get('name', '') or s.get('label', '')}: {s.get('description', '')[:200]}"
            for s in founder_ctx.get("scenes", [])[:5]
        ) or "(none — graph has no scene nodes)"
        milestones_text = "\n".join(
            f"- {m.get('label', '') or m.get('title', '')}: {m.get('description', '')[:200]}"
            for m in founder_ctx.get("milestones", [])[:10]
        ) or "(none — graph has no milestone nodes)"
        structured_posts = raw.get("founder_posts_structured") or []
        from ..ingestion.post_parser import top_by_engagement
        top_posts = top_by_engagement(structured_posts, k=5) if structured_posts else []
        top_posts_text = "\n\n".join(
            f"[likes={p.get('likes', 0)} comments={p.get('comments', 0)} reposts={p.get('reposts', 0)}]\n{p.get('text', '')[:1000]}"
            for p in top_posts
        ) or "(no engagement-ranked posts available)"
        fill_kwargs.update(
            bio=identity.get("bio", "") or "(no bio in identity/bio.md)",
            tensions_text=identity.get("tensions", "") or "(no tensions in identity/tensions.md)",
            transcripts_excerpt=raw.get("transcripts", "")[:3000] or "(no transcripts available)",
            top_posts_engagement=top_posts_text,
            cast=cast_text,
            scenes=scenes_text,
            milestones=milestones_text,
        )

    prompt = fill_prompt(template, **fill_kwargs)

    logger.info("[batch] Running deep corpus internalization...")
    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.3, max_tokens=16000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="internalize",
            template="corpus_internalize.txt",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=16000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
        )

    if not isinstance(result, dict):
        logger.warning("[batch] Internalization returned non-dict, using defaults")
        return {}

    try:
        from datetime import datetime
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({
            "hash": input_hash, "result": result,
            "cached_at": datetime.utcnow().isoformat(),
        }, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("[batch] Failed to write internalization cache: %s", e)

    return result


def calibration_check(llm: LLMProvider, state: BatchState) -> dict:
    """Write one test paragraph to verify voice calibration."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("calibration")
    template = load_prompt(PROMPTS_DIR / "calibration_check.txt")

    internalization = state.founder_internalization
    prompt = fill_prompt(
        template,
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        word_count_range=f"{state.word_count_range[0]}-{state.word_count_range[1]} words",
        formatting_habits=str(state.formatting_habits),
        argument_rhythm=internalization.get("argument_rhythm", "not analyzed"),
        founder_posts_sample=state.raw_data.get("founder_posts_sample", "")[:3000],
    )

    logger.info("[batch] Running calibration check...")
    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.5, max_tokens=1000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="calibration",
            template="calibration_check.txt",
            prompt=prompt,
            response=response,
            temperature=0.5,
            max_tokens=1000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
        )

    return result if isinstance(result, dict) else {}


class FounderIdentityMismatch(Exception):
    """Raised when the loaded founder data does not match the requested founder_slug."""


def _verify_founder_identity(
    founder_slug: str,
    display_name: str,
    personality_card: str,
    raw_data: dict,
    registry: dict | None = None,
) -> None:
    """Sanity check: the loaded data must reference the requested founder.

    Catches the failure mode where slug "sharath" pulls Cozmo AI / Liza / APE content
    (a different founder's products) because the data directory was mislabeled or the
    wrong files were copied in.

    Strategy: the founder's display_name (or a derivable token) must appear in the
    personality card. If it doesn't, AND a DIFFERENT registered founder's name appears
    instead, raise. If the slug appears at all in any source, pass. Override with env
    var TAGENT_SKIP_FOUNDER_VERIFY=1 for new founders with empty cards.
    """
    import os as _os
    if _os.environ.get("TAGENT_SKIP_FOUNDER_VERIFY"):
        return

    name_tokens: list[str] = []
    if display_name:
        for tok in display_name.replace("-", " ").replace("_", " ").split():
            if len(tok) >= 3:
                name_tokens.append(tok.lower())
    for tok in founder_slug.replace("-", " ").replace("_", " ").split():
        if len(tok) >= 3 and tok.lower() not in name_tokens:
            name_tokens.append(tok.lower())
    if not name_tokens:
        return

    card_lower = (personality_card or "").lower()
    voice_lower = (raw_data.get("raw_voice_dna") or "").lower()
    story_lower = (raw_data.get("raw_story_bank") or "").lower()
    combined = "\n".join([card_lower, voice_lower, story_lower])

    own_hits = sum(combined.count(tok) for tok in name_tokens)
    if own_hits >= 1:
        return

    foreign_hits: dict[str, int] = {}
    if registry:
        for other_slug, entry in registry.items():
            if other_slug == founder_slug:
                continue
            other_name = (entry.get("display_name") or other_slug).lower()
            for other_tok in other_name.replace("-", " ").replace("_", " ").split():
                if len(other_tok) < 4:
                    continue
                if other_tok in name_tokens:
                    continue
                hits = combined.count(other_tok)
                if hits >= 3:
                    foreign_hits[other_tok] = hits

    msg = (
        f"Founder identity mismatch for slug='{founder_slug}' (display_name='{display_name}'). "
        f"None of the expected name tokens {name_tokens} appear in the founder's personality card, "
        f"voice-dna, or story-bank."
    )
    if foreign_hits:
        msg += f" Foreign founder name tokens found in the data: {foreign_hits}."
    msg += " Refusing to run to prevent generating posts that fabricate first-degree specifics. "
    msg += "Set TAGENT_SKIP_FOUNDER_VERIFY=1 to bypass (only for brand-new founders with empty cards)."
    logger.error("[batch] %s", msg)
    raise FounderIdentityMismatch(msg)


def load_founder_state(founder_slug: str, platform: str = "linkedin") -> BatchState:
    """Initialize BatchState with all founder data loaded."""
    import yaml

    config_path = Path(__file__).parent.parent.parent / "config" / "llm-config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    from ..config.founders import get_founder_paths
    paths = get_founder_paths(config, founder_slug)

    graph_path = Path(paths["graph_path"])
    graph = load_graph(str(graph_path))
    founder_ctx = get_deep_founder_context(graph, platform)
    raw_data = load_raw_founder_data(founder_slug)

    # Prefer identity/personality-card.md from the bundle (new layout); fall back
    # to the graph-embedded personality_card; finally a separate .md on disk.
    identity = raw_data.get("identity") or {}
    personality_card = identity.get("personality_card") or get_personality_card(graph)

    registry = (config.get("founders") or {}).get("registry") or {}
    display_name = (registry.get(founder_slug) or {}).get("display_name") or founder_slug.replace("_", " ").title()
    _verify_founder_identity(founder_slug, display_name, personality_card, raw_data, registry=registry)

    # Word-count stats: prefer the structured post records (accurate per-post word counts)
    # over the heuristic splitter on the flat text blob.
    structured = raw_data.get("founder_posts_structured") or []
    if structured:
        word_counts = sorted(len((p.get("text") or "").split()) for p in structured if (p.get("text") or "").strip())
        word_counts = [w for w in word_counts if w > 20]
        if word_counts:
            mid = len(word_counts) // 2
            median = word_counts[mid] if len(word_counts) % 2 else (word_counts[mid - 1] + word_counts[mid]) // 2
        else:
            stats = compute_word_count_stats(raw_data.get("founder_posts_sample", ""))
            median = stats["median"]
    else:
        stats = compute_word_count_stats(raw_data.get("founder_posts_sample", ""))
        median = stats["median"]
    wc_range = (max(80, int(median * 0.7)), int(median * 1.3))

    freshness_warning = ""
    if graph_path.exists():
        import time
        age_days = (time.time() - graph_path.stat().st_mtime) / 86400
        if age_days > 14:
            freshness_warning = f"Graph last updated {int(age_days)} days ago"
            logger.warning("[batch] %s", freshness_warning)

    # Compute marker rates from published posts
    marker_posts = []
    if structured:
        marker_posts = [(p.get("text") or "") for p in structured if (p.get("text") or "").strip()]
    elif raw_data.get("founder_posts_sample"):
        marker_posts = _split_posts(raw_data["founder_posts_sample"])
    marker_rates = compute_marker_rates(marker_posts) if marker_posts else {}

    state = BatchState(
        founder_slug=founder_slug,
        platform=platform,
        founder_ctx=founder_ctx,
        raw_data=raw_data,
        personality_card=personality_card,
        median_word_count=median,
        word_count_range=wc_range,
        freshness_warning=freshness_warning,
        marker_rates=marker_rates,
    )
    return state
