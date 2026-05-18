"""v6 anchor inventory — runs once per founder per run.

Per README §"File structure" and ORCHESTRATOR_SPEC §"Step 2: Implement anchor
inventory state passing".

Output is the master constraint set consumed by 02_dissect (routing),
03_generate (anchors_remaining), 05_validate (verification), and 06_compile
(audit). Cached to disk so multi-source runs don't re-run this step per pack.

Cache key includes:
- graph file mtime (graph nodes drive most anchors)
- personality_card content hash
- 7-day pack_history hash (so freshness signals stay current)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import BatchState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"
_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _cache_path(founder_slug: str) -> Path:
    return _PROJECT_ROOT / "data" / "founders" / founder_slug / ".anchor_inventory_cache.json"


def _cache_key(state: BatchState) -> str:
    """Hash the inputs that determine inventory output.

    v6.1: cache key now bumped to `v6_1_anchor_inventory` AND includes the
    prompt file's mtime. This forces all existing v6.0 caches (which lack
    `unlocks_sub_mechanics[]` per anchor) to be invalidated on the next
    batch run, so every founder picks up the new schema automatically.
    No manual cache busting needed.
    """
    parts: list[str] = ["v6_1_anchor_inventory"]

    # Prompt file mtime — if the prompt is updated, every founder rebuilds.
    try:
        prompt_path = PROMPTS_DIR / "anchor_inventory.txt"
        if prompt_path.exists():
            parts.append(f"prompt_mtime:{prompt_path.stat().st_mtime}")
    except Exception:
        pass

    # Graph file mtime
    try:
        from ..config.founders import get_founder_paths
        import yaml
        with open(_PROJECT_ROOT / "config" / "llm-config.yaml") as f:
            cfg = yaml.safe_load(f)
        paths = get_founder_paths(cfg, state.founder_slug)
        graph_path = Path(paths.get("graph_path", ""))
        if graph_path.exists():
            parts.append(f"graph_mtime:{graph_path.stat().st_mtime}")
    except Exception:
        pass

    parts.append(state.personality_card[:3000])

    # 7-day pack_history fingerprint (so freshness updates daily without
    # invalidating after every single new pack).
    try:
        from .pack_history import load_pack_history
        recent = load_pack_history(state.founder_slug, days=7)
        parts.append(json.dumps(
            [{"id": r.get("pack_id"), "anchors": r.get("anchors_used", [])} for r in recent],
            sort_keys=True,
            ensure_ascii=False,
        ))
    except Exception:
        parts.append("(no_pack_history)")

    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()


def build_anchor_inventory(state: BatchState, llm: LLMProvider) -> dict:
    """Run 00_anchor_inventory.txt and return the parsed result.

    Cached to disk; subsequent calls within the same day skip the LLM call
    when the cache key matches. Returns a dict with at minimum
    `anchor_inventory[]`, `voice_marker_budget[]`, `inventory_summary{}`,
    `founder_card_depth_assessment{}`.
    """
    if getattr(state, "llm_router", None):
        try:
            llm = state.llm_router.for_task("anchor_inventory")
        except Exception:
            # Fall back to voice_load LLM if the task ID isn't configured yet.
            llm = state.llm_router.for_task("voice_load")

    key = _cache_key(state)
    cache_file = _cache_path(state.founder_slug)
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("hash") == key:
                logger.info("[anchor_inventory] using cached inventory (hash match)")
                return cached["result"]
        except Exception:
            pass

    template = load_prompt(PROMPTS_DIR / "anchor_inventory.txt")

    raw = state.raw_data or {}
    founder_ctx = state.founder_ctx or {}

    # Reuse the same compact graph snippets we already use in 01_voice_load.
    cast_text = "\n".join(
        f"- {c.get('name', '') or c.get('label', '')}: {c.get('description', '')[:150]}"
        for c in founder_ctx.get("cast", [])[:10]
    ) or "(none — graph has no cast nodes)"
    scenes_text = "\n".join(
        f"- {s.get('name', '') or s.get('label', '')}: {s.get('description', '')[:200]}"
        for s in founder_ctx.get("scenes", [])[:8]
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

    pack_history_text = "(no recent packs)"
    try:
        from .pack_history import load_pack_history
        recent = load_pack_history(state.founder_slug, days=30)
        if recent:
            lines = []
            for r in recent[-10:]:
                pid = r.get("pack_id", "?")
                ts = r.get("timestamp", "")
                anchors = ", ".join(
                    a.get("anchor_id", str(a)) if isinstance(a, dict) else str(a)
                    for a in (r.get("anchors_used") or [])[:8]
                )
                lines.append(f"- {pid} ({ts[:10]}): {anchors}")
            pack_history_text = "\n".join(lines)
    except Exception:
        pass

    prompt = fill_prompt(
        template,
        personality_card=state.personality_card[:3000],
        voice_dna=raw.get("raw_voice_dna", "")[:4000],
        story_bank=raw.get("raw_story_bank", "")[:6000],
        transcripts_excerpt=raw.get("transcripts", "")[:3000] or "(no transcripts available)",
        top_posts_engagement=top_posts_text,
        cast=cast_text,
        scenes=scenes_text,
        milestones=milestones_text,
        pack_history=pack_history_text,
    )

    logger.info("[batch] Running v6 00_anchor_inventory (once per founder per run)...")
    _start = time.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=8000)
    _dur = int((time.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="anchor_inventory",
            template="00_anchor_inventory.txt",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=8000,
            duration_ms=_dur,
            thinking=getattr(llm, "last_thinking", ""),
            llm=llm,
        )

    if not isinstance(result, dict):
        logger.warning("[batch] anchor_inventory returned non-dict; using empty stub")
        result = {
            "anchor_inventory": [],
            "voice_marker_budget": [],
            "inventory_summary": {},
            "founder_card_depth_assessment": {"depth_rating": "unknown"},
        }

    # Persist cache.
    try:
        from datetime import datetime
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(
                {"hash": key, "cached_at": datetime.utcnow().isoformat(), "result": result},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("[batch] failed to cache anchor_inventory: %s", e)

    return result
