"""Source post selection and ranking for batch generation."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..llm.base import LLMProvider
from .state import BatchState

logger = logging.getLogger(__name__)

VIRAL_SAMPLES_DIR = Path(__file__).parent.parent.parent / "data" / "viral-posts-samples"


def _parse_engagement(text: str) -> list[dict]:
    """Extract posts with engagement data from founder's linkedin posts file."""
    posts = []
    if not text:
        return posts

    separators = ["\n---\n", "\n===\n"]
    chunks = [text]
    for sep in separators:
        if sep in text:
            chunks = [c.strip() for c in text.split(sep) if c.strip()]
            break

    if len(chunks) == 1:
        chunks = [c.strip() for c in text.split("\n\n\n") if c.strip() and len(c) > 50]

    for chunk in chunks:
        if len(chunk.split()) < 20:
            continue
        likes = 0
        comments = 0
        reposts = 0
        for match in re.finditer(r"(\d[\d,]*)\s*(?:likes?|reactions?)", chunk, re.I):
            likes = max(likes, int(match.group(1).replace(",", "")))
        for match in re.finditer(r"(\d[\d,]*)\s*comments?", chunk, re.I):
            comments = max(comments, int(match.group(1).replace(",", "")))
        for match in re.finditer(r"(\d[\d,]*)\s*reposts?", chunk, re.I):
            reposts = max(reposts, int(match.group(1).replace(",", "")))

        engagement = likes + comments * 3 + reposts * 2
        posts.append({
            "text": chunk,
            "likes": likes,
            "comments": comments,
            "reposts": reposts,
            "engagement_score": engagement,
        })

    return posts


def load_viral_sources() -> list[dict]:
    """Load viral post samples from the data directory."""
    sources = []
    if not VIRAL_SAMPLES_DIR.exists():
        return sources

    for f in VIRAL_SAMPLES_DIR.glob("*.md"):
        text = f.read_text(encoding="utf-8")
        chunks = [c.strip() for c in re.split(r"\n#{1,3}\s", text) if len(c.strip()) > 100]
        for chunk in chunks:
            sources.append({"text": chunk, "source_file": f.name})

    return sources


def select_sources(
    llm: LLMProvider,
    state: BatchState,
    n_sources: int = 10,
    provided_sources: list[str] | None = None,
) -> list[str]:
    """Select top viral source posts for adaptation.

    If provided_sources is given, uses those directly.
    Otherwise ranks founder's posts + viral samples by engagement and structural diversity.
    """
    if provided_sources:
        logger.info("[batch] Using %d user-provided source posts (first 80 chars: %s)",
                    len(provided_sources), provided_sources[0][:80] if provided_sources else "")
        return provided_sources[:n_sources]

    founder_posts = _parse_engagement(state.raw_data.get("founder_posts_sample", ""))
    viral_posts = load_viral_sources()

    all_candidates = []
    for p in founder_posts:
        if p["engagement_score"] > 0:
            all_candidates.append(p)
    for v in viral_posts:
        all_candidates.append({**v, "engagement_score": 500})

    all_candidates.sort(key=lambda x: x["engagement_score"], reverse=True)
    top = all_candidates[:30]

    if len(top) <= n_sources:
        return [p["text"] for p in top]

    posts_block = "\n\n---\n\n".join(
        f"POST {i+1} (engagement: {p['engagement_score']}):\n{p['text'][:600]}"
        for i, p in enumerate(top)
    )

    prompt = f"""You are selecting the top {n_sources} viral source posts for adaptation into a founder's voice.

CRITERIA for selection:
1. Structural diversity — pick posts with DIFFERENT hook mechanics (scene drop, confession, contrarian claim, data anchor, etc.)
2. Engagement signal — higher engagement posts preferred
3. Adaptability — the post's structure should work when transplanted into a different domain
4. Avoid redundancy — no two sources should use the same hook pattern

CANDIDATE POSTS:
{posts_block}

Return a JSON array of the post numbers you selected (1-indexed), in order of priority:
```json
[1, 5, 8, 12, 3, 15, 7, 20, 11, 6]
```

Select exactly {n_sources} posts."""

    logger.info("[batch] Selecting %d source posts from %d candidates...", n_sources, len(top))
    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.3, max_tokens=500)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="select_sources",
            template="(inline prompt)",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=500,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"candidates": len(top), "requested": n_sources},
        )

    if isinstance(result, list):
        selected = []
        for idx in result:
            if isinstance(idx, int) and 1 <= idx <= len(top):
                selected.append(top[idx - 1]["text"])
        if len(selected) >= n_sources:
            return selected[:n_sources]

    return [p["text"] for p in top[:n_sources]]
