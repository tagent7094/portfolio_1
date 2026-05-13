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


def _internalization_hash(state: BatchState) -> str:
    """Hash the inputs that determine internalization output."""
    founder_ctx = state.founder_ctx
    raw = state.raw_data
    parts = [
        state.personality_card[:3000],
        str(founder_ctx.get("beliefs", [])[:30]),
        str(founder_ctx.get("stories", [])[:20]),
        str(founder_ctx.get("contrast_pairs", [])[:15]),
        str(founder_ctx.get("thinking_models", [])[:10]),
        raw.get("raw_voice_dna", "")[:4000],
        raw.get("raw_story_bank", "")[:4000],
        raw.get("founder_posts_sample", "")[:8000],
    ]
    return hashlib.sha256("||".join(parts).encode()).hexdigest()


def _internalization_cache_path(slug: str) -> Path:
    return Path(__file__).parent.parent.parent / "data" / "founders" / slug / ".internalization_cache.json"


def internalize_corpus(llm: LLMProvider, state: BatchState) -> dict:
    """Run deep corpus internalization via LLM — extracts voice markers, formatting, scenes, tensions."""
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

    template = load_prompt(PROMPTS_DIR / "corpus_internalize.txt")

    founder_ctx = state.founder_ctx
    raw = state.raw_data

    beliefs_text = "\n".join(
        f"- {b.get('topic', '')}: {b.get('stance', '')}" for b in founder_ctx.get("beliefs", [])[:30]
    )
    stories_text = "\n".join(
        f"- {s.get('title', '')}: {s.get('content', s.get('description', ''))[:200]}"
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

    prompt = fill_prompt(
        template,
        personality_card=state.personality_card[:3000],
        beliefs=beliefs_text,
        stories=stories_text,
        contrast_pairs=contrast_text,
        thinking_models=models_text,
        raw_voice_dna=raw.get("raw_voice_dna", "")[:4000],
        raw_story_bank=raw.get("raw_story_bank", "")[:4000],
        founder_posts_sample=posts_sample,
    )

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
    personality_card = get_personality_card(graph)
    raw_data = load_raw_founder_data(founder_slug)

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

    state = BatchState(
        founder_slug=founder_slug,
        platform=platform,
        founder_ctx=founder_ctx,
        raw_data=raw_data,
        personality_card=personality_card,
        median_word_count=median,
        word_count_range=wc_range,
        freshness_warning=freshness_warning,
    )
    return state
