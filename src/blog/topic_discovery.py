"""Topic discovery — finds blog-worthy topics from founder's graph + web search."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import BlogState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def discover_topics(llm: LLMProvider, state: BlogState, n_topics: int = 10) -> list[dict]:
    """Find blog topics at the intersection of founder expertise and trending conversation."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("blog_topic_discovery")

    beliefs = state.founder_ctx.get("beliefs", [])[:10]
    beliefs_summary = "\n".join(
        f"- {b.get('topic', '')}: {b.get('stance', '')}" for b in beliefs
    )

    thinking_models = state.founder_ctx.get("thinking_models", [])
    thinking_str = "\n".join(
        f"- {m.get('name', '')}: {m.get('description', '')}" for m in thinking_models[:5]
    )

    contrast_pairs = state.founder_ctx.get("contrast_pairs", [])
    contrasts_str = "\n".join(
        f"- {c.get('left', '')} vs {c.get('right', '')}: {c.get('description', '')}"
        for c in contrast_pairs[:5]
    )

    web_context = _web_search_for_topics(llm, state)
    state.web_search_context = web_context

    template = load_prompt(PROMPTS_DIR / "topic_discovery.txt")
    prompt = fill_prompt(
        template,
        personality_card=state.personality_card[:3000],
        beliefs_summary=beliefs_summary,
        thinking_models=thinking_str or "Not documented",
        contrast_pairs=contrasts_str or "Not documented",
        web_context=_format_web_context(web_context),
        n_topics=str(n_topics),
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.3, max_tokens=3000)
    _dur = int((_t.time() - _start) * 1000)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="blog_topic_discovery",
            template="topic_discovery.txt",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=3000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"n_topics": n_topics},
        )

    topics = []
    if isinstance(result, dict) and "topics" in result:
        topics = result["topics"]
    elif isinstance(result, list):
        topics = result

    for t in topics:
        if not isinstance(t, dict):
            continue
        t.setdefault("relevance_score", 0.5)
        t.setdefault("source", "graph")
        t.setdefault("supporting_beliefs", [])
        t.setdefault("trending_signal", "")
        t.setdefault("suggested_angles", [])

    topics.sort(key=lambda t: t.get("relevance_score", 0), reverse=True)
    state.discovered_topics = topics[:n_topics]
    return state.discovered_topics


def _web_search_for_topics(llm: LLMProvider, state: BlogState) -> dict:
    """Run web search using the full founder graph for contextual queries."""
    if getattr(state, "llm_router", None):
        search_llm = state.llm_router.for_task("blog_topic_discovery")
    else:
        search_llm = llm

    if not hasattr(search_llm, 'generate_with_search'):
        return {"searches": [], "trending_topics": [], "facts": []}

    from .graph_search import build_graph_enriched_search_prompt
    from ..graph.store import load_graph
    from ..config.founders import get_founder_paths, load_config

    try:
        config = load_config()
        paths = get_founder_paths(config, state.founder_slug)
        graph = load_graph(paths["graph_path"])
    except Exception as e:
        logger.warning("[blog] failed to load graph for search (%s), using basic prompt", e)
        graph = None

    if graph:
        prompt = build_graph_enriched_search_prompt(
            state.founder_slug,
            state.topic,
            graph,
            state.personality_card,
        )
    else:
        beliefs = state.founder_ctx.get("beliefs", [])[:5]
        domains = [b.get("topic", "") for b in beliefs if b.get("topic")]
        domain_str = ", ".join(domains[:3]) if domains else "technology, startups"
        founder_name = state.founder_slug.replace("_", " ").title()
        prompt = f"""Search for trending topics and news relevant to {founder_name} who writes about: {domain_str}

Summarize as JSON:
```json
{{
  "trending_topics": ["topic1", "topic2"],
  "facts": [{{"fact": "...", "source": "...", "relevance": "..."}}],
  "contrarian_angles": ["angle1", "angle2"]
}}
```"""

    import time as _t
    _start = _t.time()
    try:
        result = search_llm.generate_with_search(
            prompt,
            system_prompt="You are a research assistant. Search the web and provide factual, current information.",
            temperature=0.3,
            max_tokens=2000,
            max_searches=5,
        )
    except Exception as e:
        logger.warning("[blog] web search failed (%s), continuing without", e)
        return {"searches": [], "trending_topics": [], "facts": []}
    _dur = int((_t.time() - _start) * 1000)

    if state.tracer:
        for s in result.get("searches", []):
            state.tracer.trace_web_search(
                stage="blog_topic_web_search",
                query=s.get("query", ""),
                results=s.get("results", []),
                duration_ms=_dur // max(len(result.get("searches", [])), 1),
            )

    parsed = parse_llm_json(result.get("text", ""))
    if not isinstance(parsed, dict):
        parsed = {}
    parsed["searches"] = result.get("searches", [])
    return parsed


def _format_web_context(ctx: dict) -> str:
    parts = []
    for topic in ctx.get("trending_topics", [])[:5]:
        parts.append(f"- Trending: {topic}")
    for fact in ctx.get("facts", [])[:5]:
        if isinstance(fact, dict):
            parts.append(f"- Fact: {fact.get('fact', '')} (source: {fact.get('source', '')})")
    for angle in ctx.get("contrarian_angles", [])[:3]:
        parts.append(f"- Contrarian angle: {angle}")
    return "\n".join(parts) if parts else "(no web search results available)"
