"""FastAPI server wrapping digital-dna CLI functions."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os as _os

app = FastAPI(title="Digital DNA", version="0.2.0")

# CORS — allow credentials when auth is enabled, restrict origins via env
_allowed_origins_env = _os.environ.get("TAGENT_ALLOWED_ORIGINS", "")
if _allowed_origins_env:
    _allowed_origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
    _allow_credentials = True
else:
    _allowed_origins = ["*"]
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Subdomain auth middleware (no-op when TAGENT_AUTH_ENABLED is unset)
from webapp.auth_middleware import AuthMiddleware
app.add_middleware(AuthMiddleware)

# Auth routes
from webapp.auth_routes import router as auth_router, admin_router
app.include_router(auth_router)
app.include_router(admin_router)

# Deploy webhook (used by GitHub Actions — no SSH key required)
from webapp.deploy_routes import router as deploy_router
app.include_router(deploy_router)

# Post-pack routes (admin Excel viewer + one-time Google setup)
from webapp.pack_routes import router as pack_router, setup_router as pack_setup_router
app.include_router(pack_router)
app.include_router(pack_setup_router)

# Chat routes (AskSharath — RAG chatbot + admin config)
from webapp.chat_routes import router as chat_router, admin_chat_router
app.include_router(chat_router)
app.include_router(admin_chat_router)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).parent


# ── Simple request logging ──

import time as _time
from starlette.requests import Request


@app.middleware("http")
async def log_requests(request: Request, call_next):
    path = request.url.path
    # Skip static files
    if path in ("/", "/style.css", "/app.js", "/favicon.ico") or "." in path.split("/")[-1]:
        return await call_next(request)

    method = request.method
    start = _time.perf_counter()
    print(f"\033[1m-> {method} {path}\033[0m", flush=True)

    response = await call_next(request)

    ms = (_time.perf_counter() - start) * 1000
    color = "\033[32m" if response.status_code < 400 else "\033[31m"
    print(f"{color}{response.status_code}\033[0m {method} {path} ({ms:.0f}ms)", flush=True)

    return response


# --- Pydantic models ---

class ConfigUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class ScoreRequest(BaseModel):
    post: str
    topic: str
    platform: str = "linkedin"


class NodeUpdate(BaseModel):
    properties: dict


class NodeCreate(BaseModel):
    id: str
    node_type: str
    properties: dict = {}


class EdgeUpdate(BaseModel):
    action: str  # "add" or "remove"
    source: str
    target: str
    edge_type: str = "RELATED"


# --- Helpers ---

_graph_lock = asyncio.Lock()

def _load_config() -> dict:
    config_path = PROJECT_ROOT / "config" / "llm-config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def _graph_path(founder_slug: str | None = None) -> str:
    from src.config.founders import get_active_founder, get_founder_paths
    from src.auth import context as _auth_context
    config = _load_config()
    # Auth ContextVar takes precedence over explicit/active founder
    scoped = _auth_context.get()
    if scoped:
        paths = get_founder_paths(config, scoped)
    elif founder_slug:
        paths = get_founder_paths(config, founder_slug)
    else:
        paths = get_active_founder(config)
    return paths["graph_path"]


def _active_founder_slug() -> str:
    from src.auth import context as _auth_context
    scoped = _auth_context.get()
    if scoped:
        return scoped
    config = _load_config()
    return config.get("founders", {}).get("active", "sharath")


def _personality_card_path(founder_slug: str | None = None) -> str:
    """Return path to personality card, scoped to auth ContextVar if set."""
    from src.config.founders import get_active_founder, get_founder_paths
    from src.auth import context as _auth_context
    config = _load_config()
    scoped = _auth_context.get()
    if scoped:
        paths = get_founder_paths(config, scoped)
    elif founder_slug:
        paths = get_founder_paths(config, founder_slug)
    else:
        paths = get_active_founder(config)
    return paths["personality_card_path"]


# --- Static files ---

@app.get("/")
async def index():
    return FileResponse(WEBAPP_DIR / "index.html")


@app.get("/style.css")
async def css():
    return FileResponse(WEBAPP_DIR / "style.css", media_type="text/css")


@app.get("/app.js")
async def js():
    return FileResponse(WEBAPP_DIR / "app.js", media_type="application/javascript")


# --- Config routes ---

@app.get("/api/config")
async def get_config():
    return _load_config()


@app.get("/api/config/providers")
async def get_provider_defaults():
    """Return available providers with their default models and base URLs from .env."""
    from src.llm.factory import get_provider_defaults
    return get_provider_defaults()


@app.post("/api/config")
async def set_config(data: ConfigUpdate):
    logger.info("[set_config] provider=%s model=%s base_url=%s api_key=%s",
                data.provider, data.model, data.base_url, "***" if data.api_key else None)
    config_path = PROJECT_ROOT / "config" / "llm-config.yaml"
    config = _load_config()
    if data.provider:
        config["llm"]["provider"] = data.provider
    if data.model:
        config["llm"]["model"] = data.model
    if data.base_url:
        config["llm"]["base_url"] = data.base_url
    if data.api_key:
        config["llm"]["api_key"] = data.api_key
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    return {"status": "ok", "config": config}


@app.post("/api/config/ingestion")
async def set_ingestion_config(data: ConfigUpdate):
    """Set the LLM provider used for graph building / ingestion (cheaper model)."""
    logger.info("[set_ingestion_config] provider=%s model=%s base_url=%s",
                data.provider, data.model, data.base_url)
    config_path = PROJECT_ROOT / "config" / "llm-config.yaml"
    config = _load_config()
    if "llm_ingestion" not in config:
        config["llm_ingestion"] = {}
    if data.provider:
        config["llm_ingestion"]["provider"] = data.provider
    if data.model:
        config["llm_ingestion"]["model"] = data.model
    if data.base_url:
        config["llm_ingestion"]["base_url"] = data.base_url
    if data.api_key:
        config["llm_ingestion"]["api_key"] = data.api_key
    config["llm_ingestion"].setdefault("temperature", 0.3)
    config["llm_ingestion"].setdefault("max_tokens", 2000)
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    return {"status": "ok", "config": config}


# --- Graph routes ---

@app.get("/api/graph/stats")
async def graph_stats():
    gp = Path(_graph_path())
    card_path = Path(_personality_card_path())
    logger.info("[graph_stats] path=%s exists=%s", gp, gp.exists())

    if not gp.exists():
        logger.warning("[graph_stats] Graph file not found at %s", gp)
        return {"empty": True, "nodes": 0, "edges": 0, "types": {}}

    from src.graph.store import load_graph

    graph = load_graph(str(gp))
    counts = {}
    for _, data in graph.nodes(data=True):
        t = data.get("node_type", "unknown")
        counts[t] = counts.get(t, 0) + 1

    personality_card = ""
    if card_path.exists():
        personality_card = card_path.read_text(encoding="utf-8")

    return {
        "empty": graph.number_of_nodes() == 0,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "types": counts,
        "personality_card_words": len(personality_card.split()),
    }


def _node_label(node_id: str, data: dict) -> str:
    """Generate a short readable label for a node."""
    node_type = data.get("node_type", "unknown")
    if node_type == "founder":
        return data.get("label", "Founder")
    if node_type == "category":
        return data.get("label", node_id)
    if node_type == "belief":
        topic = data.get("topic", "")
        return topic.replace("_", " ").title()[:30] if topic else node_id
    if node_type == "story":
        return (data.get("title") or node_id)[:35]
    if node_type == "style_rule":
        return (data.get("rule_type") or "style").replace("_", " ").title()[:30]
    if node_type == "thinking_model":
        return (data.get("name") or node_id)[:35]
    if node_type == "contrast_pair":
        return (data.get("description") or node_id)[:40]
    if node_type == "vocabulary":
        return "Vocabulary"
    return node_id[:30]


@app.get("/api/graph/nodes")
async def graph_nodes():
    try:
        gp = Path(_graph_path())

        if not gp.exists():
            return {"nodes": [], "edges": []}

        from src.graph.store import load_graph

        graph = load_graph(str(gp))
        nodes = []
        for node_id, data in graph.nodes(data=True):
            node_type = data.get("node_type", "unknown")
            label = _node_label(node_id, data)

            # Send ALL properties so frontend can edit them
            props = {k: v for k, v in data.items() if k != "node_type"}
            # Serialise lists/dicts for JSON safety
            for k, v in props.items():
                if isinstance(v, (list, dict)):
                    props[k] = v  # already JSON-serialisable

            nodes.append({"id": node_id, "type": node_type, "label": label, **props})

        edges = []
        for u, v, data in graph.edges(data=True):
            edges.append({"source": u, "target": v, "type": data.get("edge_type", data.get("type", ""))})

        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        logger.exception("Failed to load graph nodes")
        raise HTTPException(status_code=500, detail=str(e))


# --- Graph CRUD ---

@app.put("/api/graph/nodes/{node_id}")
async def update_node(node_id: str, data: NodeUpdate):
    """Update properties of an existing node."""
    logger.info("[update_node] node_id=%s props=%s", node_id, list(data.properties.keys()))
    async with _graph_lock:
        from src.graph.store import load_graph, save_graph
        gp = _graph_path()
        graph = load_graph(gp)
        if node_id not in graph:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
        for k, v in data.properties.items():
            graph.nodes[node_id][k] = v
        save_graph(graph, gp)
    return {"status": "ok", "node_id": node_id}


@app.delete("/api/graph/nodes/{node_id}")
async def delete_node(node_id: str):
    """Delete a node and all its edges."""
    logger.info("[delete_node] node_id=%s", node_id)
    async with _graph_lock:
        from src.graph.store import load_graph, save_graph
        gp = _graph_path()
        graph = load_graph(gp)
        if node_id not in graph:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
        if node_id in ("founder",) or node_id.startswith("cat_"):
            raise HTTPException(status_code=400, detail="Cannot delete founder or category nodes")
        graph.remove_node(node_id)
        save_graph(graph, gp)
    return {"status": "ok", "node_id": node_id}


@app.post("/api/graph/nodes")
async def create_node(data: NodeCreate):
    """Create a new node."""
    logger.info("[create_node] id=%s type=%s", data.id, data.node_type)
    async with _graph_lock:
        from src.graph.store import load_graph, save_graph
        gp = _graph_path()
        graph = load_graph(gp)
        if data.id in graph:
            raise HTTPException(status_code=409, detail=f"Node '{data.id}' already exists")

        graph.add_node(data.id, node_type=data.node_type, **data.properties)

        # Auto-connect to category hub
        cat_map = {
            "belief": "cat_beliefs",
            "story": "cat_stories",
            "style_rule": "cat_style",
            "thinking_model": "cat_models",
            "vocabulary": "cat_vocabulary",
        }
        cat = cat_map.get(data.node_type)
        if cat and cat in graph:
            graph.add_edge(cat, data.id, edge_type="CONTAINS")

        save_graph(graph, gp)
    return {"status": "ok", "node_id": data.id}


@app.put("/api/graph/edges")
async def update_edge(data: EdgeUpdate):
    """Add or remove an edge."""
    async with _graph_lock:
        from src.graph.store import load_graph, save_graph
        gp = _graph_path()
        graph = load_graph(gp)

        if data.source not in graph:
            raise HTTPException(status_code=404, detail=f"Source node '{data.source}' not found")
        if data.target not in graph:
            raise HTTPException(status_code=404, detail=f"Target node '{data.target}' not found")

        if data.action == "add":
            graph.add_edge(data.source, data.target, edge_type=data.edge_type)
        elif data.action == "remove":
            if graph.has_edge(data.source, data.target):
                graph.remove_edge(data.source, data.target)
        else:
            raise HTTPException(status_code=400, detail="action must be 'add' or 'remove'")

        save_graph(graph, gp)
    return {"status": "ok"}


@app.get("/api/graph/personality-card")
async def personality_card():
    card_path = Path(_personality_card_path())
    if card_path.exists():
        return {"card": card_path.read_text(encoding="utf-8")}
    return {"card": ""}


# --- Founders ---

class FounderCreate(BaseModel):
    slug: str
    display_name: str

class FounderSwitch(BaseModel):
    slug: str

@app.get("/api/founders")
async def list_founders():
    from src.config.founders import list_founders as _list
    founders = _list()
    logger.info("[list_founders] %d founders, active=%s", len(founders), _active_founder_slug())
    return {"founders": founders, "active": _active_founder_slug()}

@app.post("/api/founders/active")
async def switch_founder(data: FounderSwitch):
    # When auth is enabled, founders cannot switch away from themselves
    if _os.environ.get("TAGENT_AUTH_ENABLED", "").lower() in ("1", "true", "yes"):
        raise HTTPException(status_code=403, detail="founder switching disabled in auth mode")
    logger.info("[switch_founder] switching to %s", data.slug)
    from src.config.founders import set_active_founder
    set_active_founder(data.slug)
    return {"status": "ok", "active": data.slug}

@app.post("/api/founders")
async def create_founder(data: FounderCreate):
    from src.config.founders import register_founder
    result = register_founder(data.slug, data.display_name)
    return {"status": "ok", **result}


# --- Viral Graph ---

@app.get("/api/viral-graph/stats")
async def viral_graph_stats():
    from src.config.founders import get_viral_graph_path
    from src.graph.store import load_graph
    vgp = get_viral_graph_path()
    if not Path(vgp).exists():
        return {"empty": True, "nodes": 0, "edges": 0, "types": {}}
    graph = load_graph(vgp)
    counts = {}
    for _, data in graph.nodes(data=True):
        t = data.get("node_type", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return {"empty": graph.number_of_nodes() == 0, "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(), "types": counts}

@app.get("/api/viral-graph/nodes")
async def viral_graph_nodes():
    """Return all nodes and edges from the viral knowledge graph."""
    from src.config.founders import get_viral_graph_path
    from src.graph.store import load_graph
    vgp = get_viral_graph_path()
    if not Path(vgp).exists():
        return {"nodes": [], "edges": []}

    graph = load_graph(vgp)
    nodes = []
    for node_id, data in graph.nodes(data=True):
        node_type = data.get("node_type", "unknown")
        # Build label from available fields
        label = (data.get("label") or data.get("hook_name") or data.get("template_name")
                 or data.get("pattern_name") or data.get("technique_name")
                 or data.get("bracket") or node_id)
        props = {k: v for k, v in data.items() if k != "node_type"}
        nodes.append({"id": node_id, "type": node_type, "label": str(label)[:50], **props})

    edges = [{"source": u, "target": v, "type": d.get("edge_type", d.get("type", ""))}
             for u, v, d in graph.edges(data=True)]

    return {"nodes": nodes, "edges": edges}

@app.post("/api/ingest/viral")
async def ingest_viral(use_llm: bool = False):
    """Build the viral posts knowledge graph (Big Brain).

    Args:
        use_llm: If True, also run LLM-based extraction (hooks, patterns, techniques).
                 If False (default), only statistical analysis (zero LLM cost, ~5 seconds).
    """
    mode = "full (statistical + LLM)" if use_llm else "statistical only (no LLM)"
    logger.info("[ingest_viral] Starting viral graph ingestion — mode: %s", mode)
    try:
        from src.config.founders import get_viral_csv_path, get_viral_graph_path
        from src.ingestion.viral_csv_parser import parse_viral_csv
        from src.ingestion.viral_extractor import run_full_viral_extraction
        from src.graph.viral_builder import build_viral_graph
        from src.graph.store import save_graph

        csv_path = get_viral_csv_path()
        records = parse_viral_csv(csv_path)
        if not records:
            raise HTTPException(status_code=400, detail="No records found in CSV")

        # Run extraction — optionally with LLM for deeper pattern analysis
        llm_instance = None
        if use_llm:
            from src.llm.factory import create_llm
            llm_instance = create_llm(purpose="ingestion")

        extracted = run_full_viral_extraction(records, llm=llm_instance)

        # Build and save graph
        graph = build_viral_graph(extracted)
        vgp = get_viral_graph_path()
        Path(vgp).parent.mkdir(parents=True, exist_ok=True)
        save_graph(graph, vgp)

        return {
            "status": "ok",
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "posts_parsed": len(records),
        }
    except Exception as e:
        logger.exception("Viral ingestion failed")
        raise HTTPException(status_code=500, detail=str(e))


# --- Coverage ---

@app.get("/api/coverage/{founder_slug}")
async def get_coverage(founder_slug: str):
    from src.graph.store import load_graph
    from src.tracking.node_usage import load_usage_history, compute_coverage
    gp = _graph_path(founder_slug)
    if not Path(gp).exists():
        return {"overall_pct": 0, "by_type": {}, "heatmap": {}, "opportunities": []}
    graph = load_graph(gp)
    history = load_usage_history(founder_slug)
    coverage = compute_coverage(graph, history)
    return coverage


# --- Ingest ---

@app.post("/api/ingest")
async def run_ingest():
    # Resolve active founder's data directory
    from src.config.founders import get_active_founder
    active = get_active_founder()
    data_dir = active.get("data_dir", str(PROJECT_ROOT / "data" / "founder-data"))
    founder_slug = active.get("slug", "sharath")
    logger.info("[run_ingest] Starting ingestion for founder=%s data_dir=%s", founder_slug, data_dir)

    try:
        # Run with output visible in terminal — fix env var that breaks Anthropic SDK
        import os as _os
        clean_env = {**_os.environ, "ANTHROPIC_BASE_URL": "https://api.anthropic.com"}
        result = await asyncio.to_thread(
            lambda: subprocess.run(
                [sys.executable, "-m", "src.cli", "ingest", "--data-dir", data_dir],
                cwd=str(PROJECT_ROOT),
                text=True,  # No timeout — let it run to completion
                stdout=sys.stdout, stderr=sys.stderr,
                env=clean_env,
            )
        )
        logger.info("[run_ingest] Finished with returncode=%d", result.returncode)
        return {
            "status": "ok" if result.returncode == 0 else "error",
        }
    except Exception as e:
        logger.error("[run_ingest] Failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# --- Scoring ---

@app.post("/api/score")
async def score_post(data: ScoreRequest):
    """Score a post against the knowledge graph to see influence breakdown."""
    try:
        from src.graph.store import load_graph
        from src.humanization.graph_scorer import score_graph_influence
        from src.humanization.quality_gate import quality_gate

        gp = _graph_path()
        graph = load_graph(gp)
        influence = score_graph_influence(data.post, graph, data.topic, data.platform)
        quality = quality_gate(data.post, graph)

        return {
            "status": "ok",
            "influence": influence,
            "quality": quality,
        }
    except Exception as e:
        logger.exception("Scoring failed")
        raise HTTPException(status_code=500, detail=str(e))


# --- Workflow ---

class WorkflowSave(BaseModel):
    id: str = "default"
    name: str = "Default Pipeline"
    nodes: list = []
    edges: list = []

@app.get("/api/workflow")
async def get_workflow():
    from src.workflow.engine import load_workflow
    return load_workflow()

@app.post("/api/workflow")
async def save_workflow_endpoint(data: WorkflowSave):
    from src.workflow.engine import save_workflow
    path = save_workflow(data.model_dump())
    return {"status": "ok", "path": path}

@app.get("/api/workflow/node-types")
async def get_node_types():
    from src.workflow.engine import get_node_types
    return {"node_types": get_node_types()}

@app.get("/api/workflow/list")
async def list_workflows():
    from src.workflow.engine import list_workflows
    return {"workflows": list_workflows()}


# --- Graph Dedup ---

@app.post("/api/graph/dedup")
async def dedup_graph():
    """Deduplicate the founder knowledge graph by removing semantically duplicate nodes."""
    logger.info("[dedup_graph] Starting graph deduplication...")
    try:
        from src.graph.store import load_graph, save_graph
        from src.graph.dedup import deduplicate_graph
        from src.vectors.embedder import Embedder

        gp = _graph_path()
        if not Path(gp).exists():
            raise HTTPException(status_code=400, detail="No graph found to deduplicate")

        graph = load_graph(gp)
        config = _load_config()
        embedder = Embedder(config["embedding"]["model"])

        before = graph.number_of_nodes()
        graph, stats = await asyncio.to_thread(deduplicate_graph, graph, embedder)
        after = graph.number_of_nodes()

        save_graph(graph, gp)
        logger.info("[dedup_graph] Done: %d → %d nodes (%d removed)", before, after, stats["total_removed"])

        return {
            "status": "ok",
            "before": before,
            "after": after,
            "removed": stats["total_removed"],
            "by_type": stats["by_type"],
        }
    except Exception as e:
        logger.exception("Dedup failed")
        raise HTTPException(status_code=500, detail=str(e))


# --- Post Database + Customization ---

class PostSearchRequest(BaseModel):
    query: str
    page: int = 1
    page_size: int = 20



@app.get("/api/posts/browse")
async def browse_posts(
    page: int = 1, page_size: int = 20,
    min_engagement: int = None, max_engagement: int = None,
    content_type: str = None, min_followers: int = None,
    min_likes: int = None, max_likes: int = None,
    min_comments: int = None, max_comments: int = None,
    min_reposts: int = None, max_reposts: int = None,
    sort_by: str = "engagement_score",
):
    from src.customizer.post_db import browse_posts as _browse
    logger.info("[browse_posts] page=%d filters: min_eng=%s likes=%s-%s comments=%s-%s reposts=%s-%s",
                page, min_engagement, min_likes, max_likes, min_comments, max_comments, min_reposts, max_reposts)
    return _browse(page=page, page_size=page_size, min_engagement=min_engagement,
                   max_engagement=max_engagement, content_type=content_type,
                   min_followers=min_followers, min_likes=min_likes, max_likes=max_likes,
                   min_comments=min_comments, max_comments=max_comments,
                   min_reposts=min_reposts, max_reposts=max_reposts, sort_by=sort_by)

@app.get("/api/posts/{post_id}")
async def get_post(post_id: str):
    from src.customizer.post_db import get_post as _get
    result = _get(post_id)
    if not result:
        raise HTTPException(status_code=404, detail="Post not found")
    return result

@app.post("/api/posts/search")
async def search_posts(data: PostSearchRequest):
    from src.customizer.post_db import search_posts as _search
    logger.info("[search_posts] query=%s", data.query[:50])
    return _search(query=data.query, page=data.page, page_size=data.page_size)

## ── Batch Post Generation (Cowork-style) ─────────────────────────────────

class BatchGenerateRequest(BaseModel):
    founder_slug: str
    platform: str = "linkedin"
    creativity: float = 0.5
    n_sources: int = 10
    posts_per_source: int = 9
    enable_thinking: bool = True
    source_posts: list[str] | None = None


@app.post("/api/generate/batch/stream")
async def generate_batch_stream(data: BatchGenerateRequest, request: Request):
    """SSE streaming batch generation with cancellation support."""
    logger.info("[batch_stream] founder=%s sources=%d creativity=%.2f thinking=%s",
                data.founder_slug, data.n_sources, data.creativity, data.enable_thinking)

    from src.generation.pipeline_events import PipelineEvent, PipelineEventBus
    from src.batch.session import BatchSession, CancelledError

    event_bus = PipelineEventBus()
    session = BatchSession(event_bus=event_bus)

    async def run():
        try:
            await asyncio.to_thread(
                session.run,
                founder_slug=data.founder_slug,
                platform=data.platform,
                creativity=data.creativity,
                n_sources=data.n_sources,
                posts_per_source=data.posts_per_source,
                enable_thinking=data.enable_thinking,
                source_posts=data.source_posts,
            )
        except CancelledError:
            logger.info("Batch generation cancelled by user")
            event_bus.emit(PipelineEvent(
                stage="cancelled", status="pipeline_done", data={"cancelled": True},
            ))
        except Exception as e:
            logger.exception("Batch generation failed")
            event_bus.emit(PipelineEvent(
                stage="error", status="pipeline_done", data={"error": str(e)},
            ))

    async def monitor_disconnect():
        while not session.cancel_event.is_set():
            if await request.is_disconnected():
                logger.info("Client disconnected, cancelling batch generation")
                session.cancel_event.set()
                event_bus.close()
                return
            await asyncio.sleep(1)

    asyncio.create_task(run())
    asyncio.create_task(monitor_disconnect())

    return StreamingResponse(
        event_bus.stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/generate/batch")
async def generate_batch(data: BatchGenerateRequest):
    """Non-streaming batch generation — returns full JSON result."""
    logger.info("[batch] founder=%s sources=%d creativity=%.2f",
                data.founder_slug, data.n_sources, data.creativity)
    try:
        from src.batch.session import BatchSession
        session = BatchSession()
        result = await asyncio.to_thread(
            session.run,
            founder_slug=data.founder_slug,
            platform=data.platform,
            creativity=data.creativity,
            n_sources=data.n_sources,
            posts_per_source=data.posts_per_source,
            enable_thinking=data.enable_thinking,
            source_posts=data.source_posts,
        )
        return {"status": "ok", **result}
    except Exception as e:
        logger.exception("Batch generation failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/viral-sources")
async def list_viral_sources(q: str = "", limit: int = 50, offset: int = 0):
    """Browse available viral source posts for manual selection."""
    import csv
    from pathlib import Path

    csv_path = Path(__file__).parent.parent / "data" / "viral-posts-samples" / "viral-linkedin-posts.csv"
    md_path = Path(__file__).parent.parent / "data" / "viral-posts-samples" / "viral-linkedin.md"
    sources = []

    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                content = row.get("Post content", "").strip()
                if not content or len(content) < 50:
                    continue
                sources.append({
                    "id": f"csv_{len(sources)}",
                    "content": content[:500],
                    "full_content": content,
                    "likes": int(row.get("Likes", 0) or 0),
                    "comments": int(row.get("Comments", 0) or 0),
                    "reposts": int(row.get("Reposts", 0) or 0),
                    "creator": row.get("LinkedIn Profile of Creator", ""),
                    "content_type": row.get("Content type", ""),
                    "source": "csv",
                })

    if md_path.exists():
        import re
        text = md_path.read_text(encoding="utf-8")
        chunks = re.split(r"\n## ", text)
        for i, chunk in enumerate(chunks):
            if i == 0 and not chunk.startswith("##"):
                continue
            chunk = chunk.strip()
            if len(chunk) < 50:
                continue
            title_match = re.match(r"^(.+?)(?:\n|$)", chunk)
            title = title_match.group(1) if title_match else f"Sample {i}"
            body = chunk[len(title):].strip() if title_match else chunk
            sources.append({
                "id": f"md_{i}",
                "content": body[:500],
                "full_content": body,
                "likes": 0,
                "comments": 0,
                "reposts": 0,
                "creator": "",
                "content_type": title,
                "source": "curated",
            })

    if q:
        q_lower = q.lower()
        sources = [s for s in sources if q_lower in s["full_content"].lower() or q_lower in s.get("content_type", "").lower()]

    total = len(sources)
    sources.sort(key=lambda s: s["likes"] + s["comments"] * 3 + s["reposts"] * 2, reverse=True)
    page = sources[offset:offset + limit]

    for s in page:
        s.pop("full_content", None)

    return {"sources": page, "total": total}


@app.get("/api/posts/stats")
async def posts_stats():
    from src.customizer.post_db import count_posts
    return {"total": count_posts()}


# --- Outputs ---

@app.get("/api/outputs")
async def list_outputs():
    output_dir = PROJECT_ROOT / "data" / "output"
    if not output_dir.exists():
        return {"outputs": []}
    outputs = []
    for f in sorted(output_dir.iterdir(), reverse=True):
        if f.suffix == ".txt" and not f.name.startswith("."):
            outputs.append({
                "name": f.name,
                "content": f.read_text(encoding="utf-8"),
                "size": f.stat().st_size,
            })
    return {"outputs": outputs[:20]}


if __name__ == "__main__":
    import os
    import subprocess as _sp

    PORT = int(os.environ.get("PORT", 8000))

    # Kill any process using the port before starting
    try:
        result = _sp.run(
            f"netstat -ano | findstr :{PORT} | findstr LISTENING",
            capture_output=True, text=True, shell=True,
        )
        for line in result.stdout.strip().splitlines():
            parts = line.strip().split()
            pid = parts[-1] if parts else ""
            if pid.isdigit() and int(pid) != os.getpid():
                print(f"[startup] Killing PID {pid} on port {PORT}")
                _sp.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                import time; time.sleep(0.5)
    except Exception as e:
        print(f"[startup] Port cleanup skipped: {e}")

    # Ensure we run from project root
    os.chdir(str(PROJECT_ROOT))

    print(f"[startup] Starting Digital DNA backend on http://127.0.0.1:{PORT}")
    print(f"[startup] No reload - restart manually with: python webapp/server.py")

    # Run directly via uvicorn CLI for reliable startup (no reload watcher issues)
    import uvicorn
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=PORT,
        log_level="info",
    )
