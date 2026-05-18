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

    v5 cache key includes a version prefix so v4 caches don't get reused (v5
    output schema differs — calibration is merged in, corpus_filter block is
    new, voice markers are filtered through the third-person rule).
    """
    founder_ctx = state.founder_ctx
    raw = state.raw_data
    identity = raw.get("identity") or {}
    parts = [
        "v5_voice_load",  # bump on schema changes
        state.personality_card[:3000],
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


def _derive_founder_first_name(state: BatchState) -> str:
    """Derive a first-name token for the v5 third-person filter.

    Examples:
      "alok" -> "Alok"
      "anish_popli" -> "Anish"
      "manisha" -> "Manisha"
    """
    if state.founder_first_name:
        return state.founder_first_name
    slug = (state.founder_slug or "").strip()
    if not slug:
        return ""
    first_token = slug.split("_")[0].split("-")[0].split(" ")[0]
    return first_token.title()


def _internalization_cache_path(slug: str) -> Path:
    return Path(__file__).parent.parent.parent / "data" / "founders" / slug / ".internalization_cache.json"


def voice_load(llm: LLMProvider, state: BatchState) -> dict:
    """v5: Load founder voice + run calibration in ONE LLM call (01_voice_load.txt).

    Produces voice markers, formatting habits, word_count_range, signature scenes,
    tensions, key moments inventory, AND the calibration paragraph + critique.
    The third-person filter is enforced inside the prompt (TASK 1) and by the
    Python-side scrubber below as belt-and-suspenders.
    """
    # Try v5 task ID first; fall back to legacy "internalize" for callers that
    # haven't migrated their config yet.
    if getattr(state, "llm_router", None):
        try:
            llm = state.llm_router.for_task("voice_load")
        except Exception:
            llm = state.llm_router.for_task("internalize")

    # Stamp founder_first_name once so all downstream prompts can reuse it.
    state.founder_first_name = _derive_founder_first_name(state)

    # Filter corpus by authorship BEFORE hashing so the cache key reflects the
    # filtered input (re-runs after the filter is added must invalidate stale
    # caches that contained third-person voice markers like "Alok loved …").
    _filter_corpus_by_authorship(state)

    input_hash = _internalization_hash(state)
    cache_file = _internalization_cache_path(state.founder_slug)
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("hash") == input_hash:
                logger.info("[batch] Using cached voice_load (hash match)")
                _scrub_voice_markers_in_place(cached["result"], state.founder_slug)
                state.voice_load = cached["result"]
                return cached["result"]
        except Exception:
            pass

    founder_ctx = state.founder_ctx
    raw = state.raw_data

    # v5 hard-codes 01_voice_load.txt; no v1/v2 branching.
    template = load_prompt(PROMPTS_DIR / "corpus_internalize_v2.txt")

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

    # Graph-RAG enrichment: when raw_voice_dna or raw_story_bank are thin
    # (or missing entirely), backfill with graph nodes so the v5 voice_load
    # prompt sees the rich graph signal (beliefs, style_rules, stories,
    # thinking_models, contrast_pairs). README-compliant: we don't change
    # the prompt's placeholders, just fill them with richer content when
    # the founder has graph data but lean raw files.
    from .graph_rag import graph_signal_summary

    raw_voice_dna = raw.get("raw_voice_dna", "") or ""
    raw_story_bank = raw.get("raw_story_bank", "") or ""

    beliefs = founder_ctx.get("beliefs", []) or []
    style_rules = founder_ctx.get("style_rules", []) or []
    stories = founder_ctx.get("stories", []) or []
    contrast_pairs = founder_ctx.get("contrast_pairs", []) or []
    thinking_models = founder_ctx.get("thinking_models", []) or []

    if len(raw_voice_dna) < 1000 and (beliefs or style_rules or thinking_models or contrast_pairs):
        synth_voice_lines = ["# Voice DNA (synthesized from graph)\n"]
        if beliefs:
            synth_voice_lines.append("## Beliefs (conviction-ranked)\n")
            for b in beliefs[:20]:
                lbl = b.get("label", "")
                st = b.get("stance", "") or b.get("description", "")
                cv = b.get("conviction", 0)
                if lbl:
                    synth_voice_lines.append(f"- {lbl} (conviction {cv:.2f}): {st}")
        if contrast_pairs:
            synth_voice_lines.append("\n## Tensions\n")
            for c in contrast_pairs[:10]:
                synth_voice_lines.append(f"- {c.get('left', '')} vs {c.get('right', '')}: {c.get('description', '')}")
        if thinking_models:
            synth_voice_lines.append("\n## Thinking models\n")
            for m in thinking_models[:8]:
                synth_voice_lines.append(f"- {m.get('name') or m.get('label', '')}: {m.get('description', '')}")
        if style_rules:
            synth_voice_lines.append("\n## Style rules (documented)\n")
            for r in style_rules[:15]:
                rule = r.get("rule") or r.get("label") or r.get("description", "")
                if rule:
                    synth_voice_lines.append(f"- {rule}")
        raw_voice_dna = "\n".join(synth_voice_lines)

    if len(raw_story_bank) < 1000 and stories:
        synth_story_lines = ["# Story Bank (synthesized from graph, engagement-ranked)\n"]
        for s in stories[:15]:
            lbl = s.get("label", "") or s.get("title", "")
            summ = s.get("summary", "") or s.get("description", "")
            eng = s.get("engagement", 0)
            if lbl:
                synth_story_lines.append(f"## {lbl} (engagement {eng})\n{summ}\n")
        raw_story_bank = "\n".join(synth_story_lines)

    logger.info(
        "[batch] voice_load graph signal: %s; voice_dna=%d chars, story_bank=%d chars",
        graph_signal_summary(founder_ctx), len(raw_voice_dna), len(raw_story_bank),
    )

    fill_kwargs = dict(
        personality_card=state.personality_card[:3000],
        voice_dna=raw_voice_dna[:6000],
        story_bank=raw_story_bank[:6000],
        transcripts_excerpt=raw.get("transcripts", "")[:3000] or "(no transcripts available)",
        top_posts_engagement=top_posts_text,
        founder_posts_sample=raw.get("founder_posts_sample", "")[:8000],
        cast=cast_text,
        scenes=scenes_text,
        milestones=milestones_text,
        founder_first_name=state.founder_first_name or state.founder_slug.title(),
    )

    prompt = fill_prompt(template, **fill_kwargs)

    logger.info("[batch] Running v5 voice_load (corpus + calibration combined)...")
    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.3, max_tokens=8000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="voice_load",
            template="01_voice_load.txt",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=8000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            llm=llm,
        )

    if not isinstance(result, dict):
        logger.warning("[batch] voice_load returned non-dict, using defaults")
        return {}

    _scrub_voice_markers_in_place(result, state.founder_slug)

    # Stash on state so calibration_check() and downstream prompts can read
    # the full v5/v6 voice_load output (including calibration_paragraph,
    # signature_scenes, key_moments_inventory).
    state.voice_load = result

    # v6: parse voice_markers_with_budget (new schema). Each entry has
    # marker_id, marker_text, marker_type, common_rare, max_uses_per_pack.
    # Stash on state.voice_marker_budget for PackInventoryState init.
    markers_with_budget = result.get("voice_markers_with_budget") or []
    if isinstance(markers_with_budget, list) and markers_with_budget:
        state.voice_marker_budget = markers_with_budget
        # Also flatten marker_text into state.voice_markers for v5/legacy
        # callers that expect a list of strings.
        state.voice_markers = [
            m.get("marker_text", "") for m in markers_with_budget
            if isinstance(m, dict) and m.get("marker_text")
        ]
        logger.info(
            "[batch] v6 voice_marker_budget loaded: %d markers (%d common, %d rare)",
            len(markers_with_budget),
            sum(1 for m in markers_with_budget if isinstance(m, dict) and m.get("common_rare") == "common"),
            sum(1 for m in markers_with_budget if isinstance(m, dict) and m.get("common_rare") == "rare"),
        )

    try:
        from datetime import datetime
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({
            "hash": input_hash, "result": result,
            "cached_at": datetime.utcnow().isoformat(),
        }, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("[batch] Failed to write voice_load cache: %s", e)

    return result


# Back-compat alias — keeps session.py et al. importing internalize_corpus.
def internalize_corpus(llm: LLMProvider, state: BatchState) -> dict:
    """DEPRECATED alias: v5 calls voice_load() which merges in calibration."""
    return voice_load(llm, state)


def calibration_check(llm: LLMProvider, state: BatchState) -> dict:
    """v5: calibration is produced INSIDE voice_load — no extra LLM call here.

    Returns the calibration sub-block from the cached voice_load result so
    session.py's existing flow (which calls calibration_check after
    internalize_corpus) continues to work without a second API call.
    """
    src = state.voice_load or state.founder_internalization or {}
    return {
        "calibration_paragraph": src.get("calibration_paragraph", ""),
        "confidence": src.get("calibration_confidence", src.get("confidence", 0.0)),
        "self_critique": src.get("calibration_self_critique", src.get("self_critique", "")),
        "voice_markers_used": src.get("calibration_voice_markers_used", []),
        "word_count": src.get("calibration_word_count", 0),
    }


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
    file_names = " ".join(
        f.get("file", "") for f in raw_data.get("files_ingested", [])
    ).lower()
    identity_bio = (raw_data.get("identity") or {}).get("bio", "").lower()
    combined = "\n".join([card_lower, voice_lower, story_lower, file_names, identity_bio])

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

    # If the founder has no personality_card.md AND no embedded card, synthesize
    # one from graph nodes (top beliefs, tensions, thinking models, stories,
    # cast, scenes). Catches founders like manisha who have rich graphs but
    # missing/empty .md files.
    if not (personality_card or "").strip():
        try:
            from .graph_rag import build_personality_card_from_graph, graph_signal_summary
            synth = build_personality_card_from_graph(founder_ctx, display_name, founder_slug)
            if synth.strip():
                personality_card = synth
                logger.info(
                    "[batch] No personality-card.md found — synthesized one from graph (%d chars, signal=%s)",
                    len(synth), graph_signal_summary(founder_ctx),
                )
        except Exception as e:
            logger.warning("[batch] Failed to synthesize personality_card from graph: %s", e)

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


# ─── Corpus authorship filter + voice-marker scrub ────────────────────────
#
# The founder corpus is built from a mix of sources — Notion exports, LinkedIn
# scrapes, sometimes interview transcripts or PR coverage. Items written ABOUT
# the founder in third person leak through if not filtered, and the internalize
# LLM treats them as evidence of the founder's voice. Result: voice_markers like
# "Alok loved the question — it reveals an outdated model" make it into the
# pack, then transpose injects third-person founder references into supposedly
# first-person posts. The two functions below catch both layers.

_THIRD_PERSON_VERB_PATTERNS = [
    # past tense
    "loved", "hated", "said", "told", "asked", "argued", "claimed",
    "noticed", "realized", "discovered", "decided", "wrote", "explained",
    "responded", "answered", "wondered", "tweeted", "posted", "shared",
    "mentioned", "remarked", "observed",
    # present tense
    "loves", "hates", "says", "tells", "asks", "argues", "claims",
    "notices", "realizes", "discovers", "decides", "writes", "explains",
    "responds", "answers", "wonders", "tweets", "posts", "shares",
    "mentions", "remarks", "observes",
    "thinks", "believes", "argues", "knows", "feels",
]


def _founder_first_names(slug: str) -> list[str]:
    """Best-effort first-name extraction from a slug. 'anish_popli' → ['anish']."""
    parts = slug.replace("-", "_").split("_")
    return [p for p in parts if p and len(p) >= 2][:1]


def _looks_third_person(text: str, founder_first_names: list[str]) -> bool:
    """Heuristic: does this text reference the founder in third person?"""
    if not text or not founder_first_names:
        return False
    lower = text.lower()
    for name in founder_first_names:
        name_l = name.lower()
        if name_l not in lower:
            continue
        # If the name appears followed (within ~30 chars) by a third-person
        # verb, flag it.
        for m in re.finditer(rf"\b{re.escape(name_l)}\b", lower):
            window = lower[m.end(): m.end() + 60]
            for verb in _THIRD_PERSON_VERB_PATTERNS:
                if re.search(rf"\b{verb}\b", window):
                    return True
            # Also catch "name's <noun>" patterns ("Alok's playbook")
            if window.startswith("'s ") or window.startswith("’s "):
                return True
    return False


def _filter_corpus_by_authorship(state: BatchState) -> None:
    """Strip third-person posts from `state.raw_data.founder_posts_structured`
    and rebuild `founder_posts_sample` from the filtered set. Mutates state.

    Uses fast in-process regex heuristics — no LLM call. With Kimi the cost is
    cheap enough that an LLM classifier would be fine, but the regex catches
    the common pattern (founder first-name + third-person verb within 60 chars)
    deterministically and instantly.
    """
    raw = state.raw_data or {}
    structured = raw.get("founder_posts_structured") or []
    sample = raw.get("founder_posts_sample") or ""

    first_names = _founder_first_names(state.founder_slug)
    if not first_names:
        return  # nothing to match against

    kept_structured: list[dict] = []
    skipped = 0
    for p in structured:
        text = (p.get("text") or "")
        if _looks_third_person(text, first_names):
            skipped += 1
            continue
        kept_structured.append(p)

    # Also filter the flat sample text (split by --- boundaries used by founder_loader)
    sample_posts = sample.split("\n\n---\n\n") if sample else []
    kept_sample = [
        sp for sp in sample_posts if not _looks_third_person(sp, first_names)
    ]
    skipped_sample = len(sample_posts) - len(kept_sample)

    if skipped or skipped_sample:
        logger.info(
            "[corpus_filter] %s: skipped %d structured + %d sample posts (third-person about founder)",
            state.founder_slug, skipped, skipped_sample,
        )

    # Safety: never reduce the corpus below 5 documents. If filtering would
    # leave us with too little material, log and bail out without mutating.
    if structured and len(kept_structured) < 5:
        logger.warning(
            "[corpus_filter] %s: filter would leave %d/%d posts — too few. Keeping original corpus.",
            state.founder_slug, len(kept_structured), len(structured),
        )
        return

    if structured:
        raw["founder_posts_structured"] = kept_structured
    if sample_posts:
        raw["founder_posts_sample"] = "\n\n---\n\n".join(kept_sample)


def _rewrite_marker_no_name(marker: str, founder_first_names: list[str]) -> str:
    """Strip founder name from a voice marker, preserve the mechanic description.

    "Alok loved the question — it reveals an outdated model"
       → "The 'loved the question' construction — reframes a challenging
          prospect question as intellectual gift, signals confidence"

    Conservative — only rewrites the most common patterns; leaves complex
    cases alone.
    """
    if not marker:
        return marker
    out = marker
    for name in founder_first_names:
        # "Name loved X" → "The 'loved X' construction"
        for verb in _THIRD_PERSON_VERB_PATTERNS:
            pattern = rf"\b{re.escape(name)}\s+{verb}\b"
            if re.search(pattern, out, flags=re.IGNORECASE):
                out = re.sub(
                    pattern,
                    f"The '{verb}' construction",
                    out,
                    flags=re.IGNORECASE,
                )
        # "Name's <noun>" → "the <noun>"
        out = re.sub(
            rf"\b{re.escape(name)}'s\b",
            "the",
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(
            rf"\b{re.escape(name)}’s\b",
            "the",
            out,
            flags=re.IGNORECASE,
        )
    return out


def _scrub_voice_markers_in_place(result: dict, founder_slug: str) -> None:
    """Walk the internalize result and rewrite third-person voice markers
    in-place. Mutates `result`. Safe to call on cached results too.
    """
    first_names = _founder_first_names(founder_slug)
    if not first_names:
        return

    rewritten = 0
    markers = result.get("voice_markers")
    if isinstance(markers, list):
        for i, m in enumerate(markers):
            if isinstance(m, str) and _looks_third_person(m, first_names):
                new = _rewrite_marker_no_name(m, first_names)
                if new != m:
                    markers[i] = new
                    rewritten += 1

    if rewritten:
        logger.info(
            "[voice_marker_scrub] %s: rewrote %d third-person markers",
            founder_slug, rewritten,
        )
