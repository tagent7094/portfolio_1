"""askrevsure.tagent.club — Q&A + graph + sankey endpoints over RevSure call transcripts.

Mirrors the shape of chat_routes.py but scoped to the `revsure_qa` ChromaDB
collection and the revsure_qa_graph.json NetworkX graph. Every answer is
quote-grounded — citations come from the retrieved chunk metadata.

Endpoints:
    POST /api/revsure/ask          → { answer, citations[] }
    POST /api/revsure/ask/stream   → SSE stream of the same
    GET  /api/revsure/clients      → list of 30 client thumbnails
    GET  /api/revsure/client/{slug}→ full per-client extract JSON
    GET  /api/revsure/graph        → filtered nodes + links for force-graph
    GET  /api/revsure/sankey       → aggregated ToolFrom → Pain → Win flow
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DEEPINDER_ROOT = PROJECT_ROOT / "data" / "founders" / "deepinder"
EXTRACTS_DIR = DEEPINDER_ROOT / "revsure-extracts"
GRAPH_PATH = DEEPINDER_ROOT / "knowledge-graph" / "revsure_qa_graph.json"
CHROMA_DIR = DEEPINDER_ROOT / "knowledge-graph" / "revsure_chroma"
SYSTEM_PROMPT_PATH = DEEPINDER_ROOT / "revsure-ask-system-prompt.md"

router = APIRouter()

# ── Singletons ───────────────────────────────────────────────────────────────

_embedder_instance = None
_graph_cache = None
_clients_cache: Optional[list[dict]] = None


def _get_embedder():
    global _embedder_instance
    if _embedder_instance is None:
        from src.vectors.embedder import Embedder
        _embedder_instance = Embedder()
    return _embedder_instance


def _get_store():
    from src.vectors.store import VectorStore
    return VectorStore(persist_dir=str(CHROMA_DIR), collection_name="revsure_qa")


def _load_graph():
    """Lazy-load the revsure graph; reload-on-mtime so a re-index picks up."""
    global _graph_cache
    if not GRAPH_PATH.exists():
        return None
    if _graph_cache is not None:
        cached_mtime, graph = _graph_cache
        if cached_mtime == GRAPH_PATH.stat().st_mtime:
            return graph
    from src.graph.store import load_graph
    g = load_graph(str(GRAPH_PATH))
    _graph_cache = (GRAPH_PATH.stat().st_mtime, g)
    return g


def _load_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "You are an analyst over RevSure customer call transcripts. Answer "
        "questions using ONLY the provided citation chunks. Every claim must "
        "be backed by a verbatim quote from the chunks. If the chunks don't "
        "contain the answer, say so — do not fabricate. Format answers as "
        "concise paragraphs with inline citations like [Client/Speaker/Timestamp]."
    )


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name or "").strip("_").lower()
    return s or "client"


# ── Public endpoints ─────────────────────────────────────────────────────────


class AskRequest(BaseModel):
    question: str
    n_results: int = 8
    client_filter: Optional[str] = None       # restrict by client slug
    category_filter: Optional[str] = None     # restrict by category tag


@router.post("/api/revsure/ask")
async def revsure_ask(data: AskRequest):
    """RAG-grounded answer with verbatim citations."""
    if not (data.question or "").strip():
        raise HTTPException(status_code=400, detail="Question is required")
    if not CHROMA_DIR.exists():
        raise HTTPException(
            status_code=503,
            detail="RevSure vector index not built yet. Run "
                   "`python src/batch/revsure_vector_index.py` after extraction.",
        )

    embedder = _get_embedder()
    store = _get_store()

    if store.count() == 0:
        raise HTTPException(
            status_code=503,
            detail="RevSure vector index is empty. Run the extraction + index scripts.",
        )

    where_clause: dict = {}
    if data.client_filter:
        where_clause["client_name"] = data.client_filter
    if data.category_filter:
        where_clause["category"] = data.category_filter

    q_emb = embedder.embed([data.question])[0]
    results = store.search(q_emb, n_results=max(1, min(20, data.n_results)), where=where_clause or None)

    citations = []
    docs = (results or {}).get("documents", [[]])[0]
    metas = (results or {}).get("metadatas", [[]])[0]
    dists = (results or {}).get("distances", [[]])[0] if (results or {}).get("distances") else [0.0] * len(docs)
    for doc, meta, dist in zip(docs, metas, dists):
        citations.append({
            "text": doc,
            "client_name": meta.get("client_name", ""),
            "category": meta.get("category", ""),
            "speaker": meta.get("speaker", ""),
            "timestamp": meta.get("timestamp", ""),
            "summary": meta.get("summary", ""),
            "quote": meta.get("quote", ""),
            "source_file": meta.get("source_file", ""),
            "distance": round(float(dist), 4),
        })

    answer = _compose_answer(data.question, citations)
    return {"answer": answer, "citations": citations, "system_prompt_loaded": SYSTEM_PROMPT_PATH.exists()}


def _compose_answer(question: str, citations: list[dict]) -> str:
    """Synthesize an answer from citations using the Kimi router.

    Fails gracefully if the LLM call errors — returns a "raw citations only"
    response so the page still renders useful evidence.
    """
    if not citations:
        return ("No relevant call transcript evidence was found for this question. "
                "Try rephrasing, removing client filters, or expanding the category filter.")
    try:
        from src.llm.task_router import LLMRouter
        router_obj = LLMRouter(founder_slug=None)
        llm = router_obj.for_task("revsure_qa_answer")
    except Exception as e:
        logger.warning("[revsure] LLM router unavailable, returning raw citations: %s", e)
        return _raw_citation_summary(citations)

    system_prompt = _load_system_prompt()
    cite_block = "\n\n".join(
        f"[CITATION {i+1}] client={c['client_name']} speaker={c['speaker']} ts={c['timestamp']} category={c['category']}\n\"{c['quote']}\"\nContext: {c['text']}"
        for i, c in enumerate(citations)
    )
    prompt = (
        f"{system_prompt}\n\n"
        f"USER QUESTION:\n{question}\n\n"
        f"AVAILABLE CITATIONS (use ONLY these):\n{cite_block}\n\n"
        "Write a concise, well-organized answer. For every claim, cite by "
        "[CITATION N]. If the citations don't fully answer the question, say "
        "what you can answer and what's missing. Do not invent quotes."
    )
    try:
        response = llm.generate(prompt, temperature=0.3, max_tokens=4000)
        return (response or "").strip() or _raw_citation_summary(citations)
    except Exception as e:
        logger.warning("[revsure] answer compose failed: %s", e)
        return _raw_citation_summary(citations)


def _raw_citation_summary(citations: list[dict]) -> str:
    parts = ["Direct citations from the transcripts (LLM composer unavailable):", ""]
    for i, c in enumerate(citations, start=1):
        parts.append(f"[{i}] {c['client_name']} — {c['speaker']} @ {c['timestamp']} ({c['category']})")
        parts.append(f"    \"{c['quote']}\"")
    return "\n".join(parts)


# ── Client thumbnails ────────────────────────────────────────────────────────


def _load_clients() -> list[dict]:
    global _clients_cache
    if _clients_cache is not None:
        return _clients_cache
    if not EXTRACTS_DIR.exists():
        _clients_cache = []
        return _clients_cache
    out: list[dict] = []
    for jpath in sorted(EXTRACTS_DIR.glob("*.json")):
        try:
            extract = json.loads(jpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        f = extract.get("findings") or {}
        wins = f.get("wins") or {}
        out.append({
            "slug": _slug(extract.get("client_name", jpath.stem)),
            "client_name": extract.get("client_name", jpath.stem),
            "call_type": extract.get("call_type", ""),
            "pain_count": len(f.get("pains") or []),
            "tool_count": len(f.get("tools_switched_from") or []),
            "tussle_count": len(f.get("political_tussles") or []),
            "contrarian_count": len(f.get("contrarians") or []),
            "problem_count": len(f.get("revsure_problems") or []),
            "best_count": len(f.get("best_about_revsure") or []),
            "win_count_immediate": len(wins.get("immediate") or []),
            "win_count_long_term": len(wins.get("long_term") or []),
            "has_before_state": bool((extract.get("before_state") or {}).get("pain_summary")),
            "has_after_state": bool((extract.get("after_state") or {}).get("with_revsure")),
        })
    _clients_cache = out
    return out


@router.get("/api/revsure/clients")
async def revsure_clients():
    return {"clients": _load_clients(), "count": len(_load_clients())}


@router.get("/api/revsure/client/{slug}")
async def revsure_client(slug: str):
    if not EXTRACTS_DIR.exists():
        raise HTTPException(status_code=404, detail="Extracts not built yet")
    target = None
    for jpath in EXTRACTS_DIR.glob("*.json"):
        try:
            extract = json.loads(jpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        if _slug(extract.get("client_name", "")) == slug:
            target = extract
            break
    if not target:
        raise HTTPException(status_code=404, detail=f"client not found: {slug}")
    return target


# ── Graph + sankey ───────────────────────────────────────────────────────────


@router.get("/api/revsure/graph")
async def revsure_graph(
    client: Optional[str] = Query(None, description="Filter to one client slug"),
    category: Optional[str] = Query(None, description="Filter to one category (Pain/ToolFrom/Tussle/Contrarian/RevSureProblem/Win/BestAspect)"),
):
    """Return nodes + links shaped for react-force-graph-2d."""
    g = _load_graph()
    if g is None:
        raise HTTPException(status_code=503, detail="Graph not built yet")

    # If filtering by client, keep that client node + its 1-hop neighborhood
    # (claim nodes + their cited Quotes). Plus optionally filter claim type.
    selected_ids: set[str]
    if client:
        target_cid = None
        for nid, attrs in g.nodes(data=True):
            if attrs.get("node_type") == "Client" and attrs.get("slug") == client:
                target_cid = nid
                break
        if not target_cid:
            return {"nodes": [], "links": []}
        selected_ids = {target_cid}
        for succ in g.successors(target_cid):
            sattrs = g.nodes[succ]
            if category and sattrs.get("node_type") != category:
                continue
            selected_ids.add(succ)
            # Include the Quotes cited by this claim
            for q in g.successors(succ):
                qattrs = g.nodes[q]
                if qattrs.get("node_type") == "Quote":
                    selected_ids.add(q)
    else:
        selected_ids = set(g.nodes())
        if category:
            selected_ids = {
                nid for nid in selected_ids
                if g.nodes[nid].get("node_type") in (category, "Client", "Quote")
            }

    nodes = []
    for nid in selected_ids:
        attrs = dict(g.nodes[nid])
        nodes.append({"id": nid, **attrs})
    links = []
    for s, t, d in g.edges(data=True):
        if s in selected_ids and t in selected_ids:
            links.append({"source": s, "target": t, **d})
    return {"nodes": nodes, "links": links}


@router.get("/api/revsure/sankey")
async def revsure_sankey():
    """Aggregate ToolFrom → Pain → Win flow across all clients."""
    g = _load_graph()
    if g is None:
        raise HTTPException(status_code=503, detail="Graph not built yet")

    # Sankey nodes: "tool:<name>", "pain:<bucket>", "win:<bucket>"
    # Links: count of clients with that tool → pain bucket → win bucket.
    tool_counts: dict[str, int] = {}
    pain_counts: dict[str, int] = {}
    win_counts: dict[str, int] = {}
    tool_to_pain: dict[tuple[str, str], int] = {}
    pain_to_win: dict[tuple[str, str], int] = {}

    for cid, attrs in g.nodes(data=True):
        if attrs.get("node_type") != "Client":
            continue
        # Collect this client's tools, pains, wins (by claim node label).
        client_tools, client_pains, client_wins = [], [], []
        for succ in g.successors(cid):
            sattrs = g.nodes[succ]
            t = sattrs.get("node_type")
            label = (sattrs.get("label") or "")[:60] or "(unspecified)"
            if t == "ToolFrom":
                client_tools.append(label)
            elif t == "Pain":
                client_pains.append(label)
            elif t == "Win":
                client_wins.append(label)
        # Per-client cartesian (capped to top 3 of each to avoid sankey explosion)
        client_tools = client_tools[:3]
        client_pains = client_pains[:3]
        client_wins = client_wins[:3]
        for t in client_tools:
            tool_counts[t] = tool_counts.get(t, 0) + 1
        for p in client_pains:
            pain_counts[p] = pain_counts.get(p, 0) + 1
        for w in client_wins:
            win_counts[w] = win_counts.get(w, 0) + 1
        for t in client_tools:
            for p in client_pains:
                tool_to_pain[(t, p)] = tool_to_pain.get((t, p), 0) + 1
        for p in client_pains:
            for w in client_wins:
                pain_to_win[(p, w)] = pain_to_win.get((p, w), 0) + 1

    node_ids: dict[str, int] = {}
    nodes: list[dict] = []

    def _add_node(label: str, kind: str) -> int:
        key = f"{kind}:{label}"
        if key not in node_ids:
            node_ids[key] = len(nodes)
            nodes.append({"name": label, "kind": kind})
        return node_ids[key]

    for t, n in sorted(tool_counts.items(), key=lambda x: -x[1])[:12]:
        _add_node(t, "tool")
    for p, n in sorted(pain_counts.items(), key=lambda x: -x[1])[:12]:
        _add_node(p, "pain")
    for w, n in sorted(win_counts.items(), key=lambda x: -x[1])[:12]:
        _add_node(w, "win")

    links: list[dict] = []
    for (t, p), v in tool_to_pain.items():
        if f"tool:{t}" not in node_ids or f"pain:{p}" not in node_ids:
            continue
        links.append({"source": node_ids[f"tool:{t}"], "target": node_ids[f"pain:{p}"], "value": v})
    for (p, w), v in pain_to_win.items():
        if f"pain:{p}" not in node_ids or f"win:{w}" not in node_ids:
            continue
        links.append({"source": node_ids[f"pain:{p}"], "target": node_ids[f"win:{w}"], "value": v})

    return {"nodes": nodes, "links": links}


# ── Streaming variant ────────────────────────────────────────────────────────


@router.post("/api/revsure/ask/stream")
async def revsure_ask_stream(data: AskRequest):
    """SSE variant: same content as /ask but streamed line-by-line."""
    # For simplicity we compute the whole answer then stream it in 32-char
    # chunks (Kimi non-stream is fine for ~4K outputs). A future iteration
    # can swap to true LLM streaming if the UX warrants.
    payload = await revsure_ask(data)

    async def event_stream():
        yield f"data: {json.dumps({'event': 'citations', 'citations': payload['citations']})}\n\n"
        answer = payload["answer"]
        for i in range(0, len(answer), 64):
            yield f"data: {json.dumps({'event': 'chunk', 'text': answer[i:i + 64]})}\n\n"
        yield f"data: {json.dumps({'event': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
