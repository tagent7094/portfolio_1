"""FastAPI server wrapping digital-dna CLI functions."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import os as _os
import time as _time

_server_start = _time.time()

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
from webapp.pack_routes import router as pack_router, setup_router as pack_setup_router, founder_router as pack_founder_router
app.include_router(pack_router)
app.include_router(pack_setup_router)
app.include_router(pack_founder_router)

# Chat routes (AskSharath — RAG chatbot + admin config)
from webapp.chat_routes import router as chat_router, admin_chat_router
app.include_router(chat_router)
app.include_router(admin_chat_router)

# Post customizer routes (blend opener + body, chat edits)
from webapp.customize_routes import customize_router
app.include_router(customize_router)

# Schedule routes (recurring generation)
from webapp.schedule_routes import router as schedule_router, start_scheduler
app.include_router(schedule_router)

# OS management routes (os.tagent.club)
from webapp.os_routes import router as os_router
app.include_router(os_router)


@app.on_event("startup")
async def _startup_scheduler():
    start_scheduler()

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
    # Skip static files and noisy polling endpoints
    if path in ("/", "/style.css", "/app.js", "/favicon.ico") or "." in path.split("/")[-1]:
        return await call_next(request)
    if "/api/generate/batch/status/" in path:
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

@app.get("/api/posts/stats")
async def posts_stats():
    from src.customizer.post_db import count_posts
    return {"total": count_posts()}

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
    effort: str = "high"


@app.post("/api/generate/batch/stream")
async def generate_batch_stream(data: BatchGenerateRequest, request: Request):
    """SSE streaming batch generation with cancellation support."""
    logger.info("[batch_stream] founder=%s sources=%d creativity=%.2f thinking=%s source_posts=%s",
                data.founder_slug, data.n_sources, data.creativity, data.enable_thinking,
                f"{len(data.source_posts)} provided" if data.source_posts else "auto")

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
                effort=data.effort,
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
        while not session.cancel_event.is_set() and not event_bus._closed:
            if await request.is_disconnected():
                if not event_bus._closed:
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
            effort=data.effort,
        )
        return {"status": "ok", **result}
    except Exception as e:
        logger.exception("Batch generation failed")
        raise HTTPException(status_code=500, detail=str(e))


## ── Background batch tasks ──────────────────────────────────────────────

_bg_tasks: dict[str, dict] = {}
_MAX_FINISHED_TASKS = 50


def _cleanup_old_tasks():
    finished = [k for k, v in _bg_tasks.items() if v["status"] in ("done", "error", "cancelled")]
    if len(finished) > _MAX_FINISHED_TASKS:
        by_time = sorted(finished, key=lambda k: _bg_tasks[k].get("finished_at", ""))
        for k in by_time[: len(finished) - _MAX_FINISHED_TASKS]:
            del _bg_tasks[k]


@app.post("/api/generate/batch/background")
async def generate_batch_background(data: BatchGenerateRequest):
    """Start generation as a background task. Returns task_id for polling."""
    logger.info("[batch_bg] founder=%s sources=%d", data.founder_slug, data.n_sources)

    from dataclasses import asdict
    from src.generation.pipeline_events import PipelineEvent, PipelineEventBus
    from src.batch.session import BatchSession, CancelledError

    task_id = uuid.uuid4().hex[:10]
    event_bus = PipelineEventBus()
    session = BatchSession(event_bus=event_bus)

    task_state: dict = {
        "task_id": task_id,
        "founder_slug": data.founder_slug,
        "status": "running",
        "progress": 0.0,
        "stage": "starting",
        "log": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "error": None,
        "filepath": None,
        "web_search_summary": None,
        "_session": session,
    }
    _bg_tasks[task_id] = task_state
    _cleanup_old_tasks()

    async def _run():
        try:
            gen_future = asyncio.ensure_future(asyncio.to_thread(
                session.run,
                founder_slug=data.founder_slug,
                platform=data.platform,
                creativity=data.creativity,
                n_sources=data.n_sources,
                posts_per_source=data.posts_per_source,
                enable_thinking=data.enable_thinking,
                source_posts=data.source_posts,
                effort=data.effort,
            ))

            # Drain event bus into task_state
            async for chunk in event_bus.stream():
                if not chunk.startswith("data:"):
                    continue
                try:
                    ev = json.loads(chunk[5:].strip())
                except Exception:
                    continue
                task_state["progress"] = ev.get("progress", task_state["progress"])
                task_state["stage"] = ev.get("stage", task_state["stage"])
                llm_text = ev.get("llm_text", "")
                if llm_text:
                    task_state["current_llm_text"] = llm_text
                if ev.get("status") == "llm_chunk":
                    continue
                task_state["log"].append({
                    "stage": ev.get("stage", ""),
                    "status": ev.get("status", ""),
                })
                if ev.get("stage") == "web_search" and ev.get("status") == "completed":
                    task_state["web_search_summary"] = ev.get("data", {})
                fp = (ev.get("data") or {}).get("filepath")
                if fp:
                    task_state["filepath"] = fp
                err = (ev.get("data") or {}).get("error")
                if err:
                    task_state["error"] = err
                if ev.get("status") == "pipeline_done":
                    break

            await gen_future

            if task_state["error"]:
                task_state["status"] = "error"
            elif task_state["status"] == "running":
                task_state["status"] = "done"
                task_state["progress"] = 1.0

        except CancelledError:
            task_state["status"] = "cancelled"
        except Exception as e:
            logger.exception("[batch_bg] failed: %s", e)
            task_state["status"] = "error"
            task_state["error"] = str(e)
        finally:
            task_state["finished_at"] = datetime.now(timezone.utc).isoformat()

    asyncio.create_task(_run())
    return {"task_id": task_id}


@app.get("/api/generate/batch/tasks")
async def list_batch_tasks():
    return {"tasks": [
        {k: v for k, v in t.items() if not k.startswith("_") and k != "log"}
        for t in _bg_tasks.values()
    ]}


@app.get("/api/generate/batch/status/{task_id}")
async def get_batch_task_status(task_id: str, since: int = 0):
    """Poll task status. Pass since=N to get only log entries after index N."""
    task = _bg_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task["task_id"],
        "founder_slug": task["founder_slug"],
        "status": task["status"],
        "progress": task["progress"],
        "stage": task["stage"],
        "log": task["log"][since:],
        "log_offset": len(task["log"]),
        "started_at": task["started_at"],
        "finished_at": task["finished_at"],
        "error": task["error"],
        "filepath": task["filepath"],
        "current_llm_text": task.get("current_llm_text", ""),
        "web_search_summary": task.get("web_search_summary"),
    }


@app.post("/api/generate/batch/cancel/{task_id}")
async def cancel_batch_task(task_id: str):
    task = _bg_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    session = task.get("_session")
    if session and hasattr(session, "cancel_event"):
        session.cancel_event.set()
    task["status"] = "cancelled"
    task["finished_at"] = datetime.now(timezone.utc).isoformat()
    return {"status": "cancelled"}


@app.get("/api/viral-sources/sheets")
async def list_sheets():
    """Return distinct source sheet names available in the post database."""
    from src.customizer.post_db import get_sheets
    return {"sheets": get_sheets()}


@app.get("/api/viral-sources")
async def list_viral_sources(
    q: str = "",
    limit: int = 50,
    offset: int = 0,
    min_likes: int | None = None,
    max_likes: int | None = None,
    min_comments: int | None = None,
    max_comments: int | None = None,
    min_reposts: int | None = None,
    max_reposts: int | None = None,
    sort_by: str = "engagement_score",
    source_sheet: str | None = None,
):
    """Browse viral source posts with engagement filters."""
    from src.customizer.post_db import browse_posts, search_posts

    page_num = (offset // limit) + 1 if limit else 1

    if q:
        result = search_posts(query=q, page=page_num, page_size=limit)
    else:
        result = browse_posts(
            page=page_num, page_size=limit,
            min_likes=min_likes, max_likes=max_likes,
            min_comments=min_comments, max_comments=max_comments,
            min_reposts=min_reposts, max_reposts=max_reposts,
            sort_by=sort_by if sort_by in {"engagement_score", "likes", "comments", "reposts"} else "engagement_score",
            source_sheet=source_sheet,
        )

    sources = [
        {
            "id": p["post_id"],
            "content": p["content"],
            "likes": p["likes"],
            "comments": p["comments"],
            "reposts": p["reposts"],
            "creator": p.get("creator_url", ""),
            "content_type": p.get("content_type", ""),
            "source": "csv",
            "engagement_score": p.get("engagement_score", 0),
            "source_sheet": p.get("source_sheet", ""),
        }
        for p in result["posts"]
    ]
    return {"sources": sources, "total": result["total"]}


@app.get("/api/founders/{slug}/used-sources")
async def get_used_sources(slug: str):
    from src.batch.source_tracker import load_used_sources_full
    return {"sources": load_used_sources_full(slug)}


## ── Viral Repo Management (admin) ──────────────────────────────────────────

@app.get("/api/admin/server/status")
async def get_server_status(request: Request):
    from webapp.auth_routes import _require_admin
    _require_admin(request)
    import platform
    from webapp.schedule_routes import _schedules, _running_loop
    active_tasks = sum(1 for t in _bg_tasks.values() if t.get("status") == "running")
    try:
        import psutil
        mem_mb = round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        mem_mb = None
    return {
        "uptime_seconds": int(_time.time() - _server_start),
        "python_version": platform.python_version(),
        "active_tasks": active_tasks,
        "total_tasks": len(_bg_tasks),
        "memory_mb": mem_mb,
        "scheduler_running": _running_loop is not None and not _running_loop.done(),
        "enabled_schedules": sum(1 for s in _schedules if s.get("enabled", True)),
        "total_schedules": len(_schedules),
    }


VIRAL_DIR = PROJECT_ROOT / "data" / "viral-posts-samples"


@app.get("/api/admin/viral-repos")
async def list_viral_repos(request: Request):
    """List viral post repo files."""
    from webapp.auth_routes import _require_admin
    _require_admin(request)

    from src.config.founders import get_viral_csv_path
    active_path = get_viral_csv_path()
    active_name = Path(active_path).name if active_path else ""

    files = []
    if VIRAL_DIR.exists():
        for f in sorted(VIRAL_DIR.iterdir()):
            if f.suffix.lower() in (".csv", ".xlsx"):
                post_count = 0
                try:
                    from src.ingestion.viral_csv_parser import parse_viral_csv
                    post_count = len(parse_viral_csv(str(f)))
                except Exception:
                    pass
                files.append({
                    "name": f.name,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "post_count": post_count,
                    "active": f.name == active_name,
                })
    return {"files": files, "active": active_name}


@app.post("/api/admin/viral-repos/upload")
async def upload_viral_repo(request: Request, file: UploadFile = File(...)):
    """Upload a viral post CSV/XLSX file."""
    from webapp.auth_routes import _require_admin
    _require_admin(request)

    if not file.filename or file.filename.split(".")[-1].lower() not in ("csv", "xlsx"):
        raise HTTPException(status_code=400, detail="Only .csv and .xlsx files accepted")

    VIRAL_DIR.mkdir(parents=True, exist_ok=True)
    dest = VIRAL_DIR / file.filename
    content = await file.read()
    dest.write_bytes(content)
    logger.info("[viral-repos] Uploaded %s (%d bytes)", dest.name, len(content))

    post_count = 0
    try:
        from src.ingestion.viral_csv_parser import parse_viral_csv
        post_count = len(parse_viral_csv(str(dest)))
    except Exception:
        pass

    return {"name": dest.name, "size_kb": round(len(content) / 1024, 1), "post_count": post_count}


@app.delete("/api/admin/viral-repos/{name}")
async def delete_viral_repo(name: str, request: Request):
    """Delete a viral repo file."""
    from webapp.auth_routes import _require_admin
    _require_admin(request)

    from src.config.founders import get_viral_csv_path
    active_name = Path(get_viral_csv_path()).name
    if name == active_name:
        raise HTTPException(status_code=400, detail="Cannot delete the active viral repo file")

    target = VIRAL_DIR / name
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")
    target.unlink()
    return {"ok": True}


class CombineRequest(BaseModel):
    files: list[str]
    output_name: str


@app.post("/api/admin/viral-repos/combine")
async def combine_viral_repos(body: CombineRequest, request: Request):
    """Merge multiple viral repo files into a combined CSV."""
    from webapp.auth_routes import _require_admin
    _require_admin(request)

    import csv as csv_mod
    from src.ingestion.viral_csv_parser import parse_viral_csv

    seen_ids: set[str] = set()
    merged: list[dict] = []

    for fname in body.files:
        fpath = VIRAL_DIR / fname
        if not fpath.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {fname}")
        records = parse_viral_csv(str(fpath))
        for r in records:
            if r["post_id"] not in seen_ids:
                seen_ids.add(r["post_id"])
                merged.append(r)

    output_name = body.output_name if body.output_name.endswith(".csv") else f"{body.output_name}.csv"
    dest = VIRAL_DIR / output_name

    fieldnames = ["post_id", "content", "likes", "comments", "reposts",
                   "followers", "likes_ratio", "engagement_score", "content_type", "creator_url"]
    # Write CSV using the standard parser column names expected by re-import
    with open(dest, "w", newline="", encoding="utf-8") as f:
        # Use column headers the parser expects
        writer = csv_mod.writer(f)
        writer.writerow([
            "LinkedIn Profile of Creator", "", "Number of followers", "",
            "Content type", "", "", "Likes vs followers ratio",
            "Likes", "Comments", "Reposts", "Post content",
        ])
        for r in merged:
            writer.writerow([
                r.get("creator_url", ""), "", r.get("followers", 0), "",
                r.get("content_type", ""), "", "", r.get("likes_ratio", 0),
                r.get("likes", 0), r.get("comments", 0), r.get("reposts", 0),
                r.get("content", ""),
            ])

    logger.info("[viral-repos] Combined %d files -> %s (%d posts)", len(body.files), output_name, len(merged))
    return {"name": output_name, "post_count": len(merged), "size_kb": round(dest.stat().st_size / 1024, 1)}


class ActivateRequest(BaseModel):
    filename: str


@app.post("/api/admin/viral-repos/activate")
async def activate_viral_repo(body: ActivateRequest, request: Request):
    """Set a file as the active viral post source and re-import into SQLite."""
    from webapp.auth_routes import _require_admin
    _require_admin(request)

    target = VIRAL_DIR / body.filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    from src.config.founders import _load_config, _save_config
    config = _load_config()
    if "viral_graph" not in config:
        config["viral_graph"] = {}
    config["viral_graph"]["source_csv"] = f"data/viral-posts-samples/{body.filename}"
    _save_config(config)

    from src.customizer.post_db import import_from_csv
    count = await asyncio.to_thread(import_from_csv, str(target), True)

    logger.info("[viral-repos] Activated %s, imported %d posts", body.filename, count)
    return {"ok": True, "imported": count}


## ── Best-Match: Semantic Founder-Post Alignment ──────────────────────────────

import hashlib as _hashlib
import struct as _struct

_founder_profile_cache: dict[str, list[float]] = {}


def _build_founder_profile_sentences(graph) -> list[str]:
    """Build rich natural-language sentences from a founder's knowledge graph.

    Node field mapping (graph schema uses topic/title/name, not label):
      belief       -> topic, stance
      sub_belief   -> topic, stance
      story        -> title, summary
      thinking_model -> name, description
      vocabulary   -> phrases_used (list-as-string)
      contrast_pair -> label, left, right
      milestone    -> title, summary
      identity/value/topic/category -> label or description
    """
    sentences: list[str] = []
    for _, data in graph.nodes(data=True):
        nt = data.get("node_type", "")
        if nt in ("belief", "sub_belief"):
            topic = data.get("topic", "") or data.get("label", "")
            stance = data.get("stance", "")
            if topic:
                s = f"I believe in {topic}."
                if stance:
                    s += f" {stance}"
                sentences.append(s)
        elif nt == "story":
            title = data.get("title", "") or data.get("label", "")
            summary = data.get("summary", "")
            if title and summary:
                sentences.append(f"Story: {title}. {summary}")
            elif title:
                sentences.append(f"Experience with {title}.")
        elif nt == "thinking_model":
            name = data.get("name", "") or data.get("label", "")
            desc = data.get("description", "")
            applies = data.get("applies_to", "")
            if name:
                s = f"I think about {name}."
                if desc:
                    s += f" {desc}"
                if applies:
                    s += f" This applies to {applies}."
                sentences.append(s)
        elif nt == "vocabulary":
            phrases = data.get("phrases_used", "")
            if isinstance(phrases, str) and phrases.startswith("["):
                import ast
                try:
                    phrase_list = ast.literal_eval(phrases)
                    for p in phrase_list[:10]:
                        sentences.append(f"I often say: {p}")
                except Exception:
                    pass
            elif isinstance(phrases, list):
                for p in phrases[:10]:
                    sentences.append(f"I often say: {p}")
        elif nt == "contrast_pair":
            label = data.get("label", "")
            left = data.get("left", "")
            right = data.get("right", "")
            if label and left and right:
                sentences.append(f"I contrast {left} versus {right} when discussing {label}.")
        elif nt == "milestone":
            title = data.get("title", "") or data.get("label", "")
            summary = data.get("summary", "")
            if title and summary:
                sentences.append(f"Milestone: {title}. {summary}")
            elif title:
                sentences.append(f"Milestone: {title}.")
        elif nt == "identity":
            desc = data.get("description", "")
            label = data.get("label", "")
            if desc:
                sentences.append(desc)
            elif label:
                sentences.append(label)
        elif nt == "value":
            label = data.get("label", "")
            if label:
                sentences.append(f"I value {label}.")
        elif nt == "category":
            label = data.get("label", "") or data.get("name", "")
            if label:
                sentences.append(f"I frequently discuss {label}.")
        elif nt == "topic":
            label = data.get("label", "") or data.get("name", "")
            if label:
                sentences.append(f"I frequently discuss {label}.")
    return sentences


def _get_founder_embedding(slug: str, graph, embedder) -> list[float]:
    """Get or compute the average embedding for a founder's profile."""
    sentences = _build_founder_profile_sentences(graph)
    if not sentences:
        return []
    content_hash = _hashlib.md5("||".join(sentences).encode()).hexdigest()[:12]
    cache_key = f"{slug}:{content_hash}"
    if cache_key in _founder_profile_cache:
        return _founder_profile_cache[cache_key]

    embs = embedder.embed(sentences)
    import numpy as np
    avg = np.mean(embs, axis=0)
    avg = (avg / np.linalg.norm(avg)).tolist()
    _founder_profile_cache[cache_key] = avg
    return avg


def _bytes_to_floats(b: bytes) -> list[float]:
    n = len(b) // 4
    return list(_struct.unpack(f"{n}f", b))


async def _haiku_rerank(
    candidates: list[dict],
    profile_sentences: list[str],
    founder_slug: str,
    api_key: str,
) -> list[dict]:
    """Re-rank top candidates using Haiku for deep topic/mechanics matching."""
    import anthropic

    profile_text = "\n".join(f"- {s}" for s in profile_sentences[:60])

    posts_block = ""
    for i, c in enumerate(candidates):
        content_preview = c["content"][:600]
        posts_block += f"\n[POST {i}]\n{content_preview}\n"

    prompt = f"""You are scoring viral LinkedIn posts for how well they align with a specific founder's profile.

## Founder Profile ({founder_slug})
{profile_text}

## Scoring Criteria (0-100 each)
1. **Topic Fit**: Does the post's subject matter overlap with the founder's domain, beliefs, expertise?
2. **Mechanics Match**: Would the post's writing structure (storytelling, lists, contrarian takes, data-driven, personal anecdote) work well adapted to this founder's voice?
3. **Audience Alignment**: Would this founder's audience engage with this type of content?

## Posts to Score
{posts_block}

## Instructions
Return ONLY a JSON array of objects, one per post, in order:
[{{"idx": 0, "topic": 85, "mechanics": 70, "audience": 80, "reason": "one sentence why"}}]

Be harsh — most posts should score below 50. Only truly aligned posts deserve 70+."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = await asyncio.to_thread(
            lambda: client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
        )
        text = resp.content[0].text.strip()
        # Extract JSON from response
        import json as _json
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        scores = _json.loads(text)

        for item in scores:
            idx = item.get("idx", -1)
            if 0 <= idx < len(candidates):
                topic = min(100, max(0, item.get("topic", 0)))
                mechanics = min(100, max(0, item.get("mechanics", 0)))
                audience = min(100, max(0, item.get("audience", 0)))
                overall = round((topic * 0.4 + mechanics * 0.3 + audience * 0.3), 1)
                candidates[idx]["match_score"] = overall
                candidates[idx]["topic_score"] = topic
                candidates[idx]["mechanics_score"] = mechanics
                candidates[idx]["audience_score"] = audience
                candidates[idx]["match_reason"] = item.get("reason", "")
                candidates[idx]["deep"] = True

        candidates.sort(key=lambda x: x["match_score"], reverse=True)
        return candidates
    except Exception as e:
        logger.warning("[best-match] Haiku rerank failed: %s", e)
        return candidates


@app.get("/api/viral-posts/best-match/{founder_slug}")
async def best_match_viral_posts(
    founder_slug: str,
    request: Request,
    page: int = 1,
    page_size: int = 20,
    min_likes: int | None = None,
    max_likes: int | None = None,
    min_comments: int | None = None,
    max_comments: int | None = None,
    q: str = "",
    source_sheet: str | None = None,
    deep: bool = False,
    api_key: str = "",
):
    """Return viral posts scored by semantic alignment with a founder's knowledge graph.
    With deep=true and an api_key, uses Haiku to re-rank top 50 candidates."""
    from src.config.founders import _load_config, get_founder_paths
    from src.graph.store import load_graph
    from src.customizer.post_db import (
        browse_posts, search_posts, init_db, count_posts,
        import_from_csv, load_all_embeddings, embeddings_count,
    )

    init_db()
    if count_posts() == 0:
        await asyncio.to_thread(import_from_csv)

    config = _load_config()
    try:
        paths = get_founder_paths(config, founder_slug)
        graph = load_graph(paths["graph_path"])
    except Exception as e:
        logger.warning("[best-match] Failed to load graph for %s: %s", founder_slug, e)
        raise HTTPException(status_code=404, detail=f"No graph found for {founder_slug}")

    if graph.number_of_nodes() == 0:
        raise HTTPException(status_code=404, detail=f"Empty graph for {founder_slug}")

    # Check if semantic embeddings are available
    n_emb = embeddings_count()
    use_semantic = n_emb > 0

    if use_semantic:
        import numpy as np
        from src.vectors.embedder import Embedder
        embedder = Embedder()

        founder_emb = await asyncio.to_thread(_get_founder_embedding, founder_slug, graph, embedder)
        if not founder_emb:
            use_semantic = False

    if use_semantic:
        all_embs = await asyncio.to_thread(load_all_embeddings)

        if q:
            all_result = search_posts(query=q, page=1, page_size=5000)
        else:
            all_result = browse_posts(
                page=1, page_size=5000,
                min_likes=min_likes, max_likes=max_likes,
                min_comments=min_comments, max_comments=max_comments,
                source_sheet=source_sheet,
            )

        founder_vec = np.array(founder_emb, dtype=np.float32)
        scored = []
        for p in all_result["posts"]:
            emb_bytes = all_embs.get(p["post_id"])
            if not emb_bytes:
                continue
            post_vec = np.frombuffer(emb_bytes, dtype=np.float32)
            sim = float(np.dot(founder_vec, post_vec) / (
                np.linalg.norm(founder_vec) * np.linalg.norm(post_vec) + 1e-9
            ))
            match_pct = round(max(0, sim) * 100, 1)
            scored.append({**p, "match_score": match_pct, "matched_keywords": 0, "semantic": True})

        profile_sentences = _build_founder_profile_sentences(graph)
        n_profile = len(profile_sentences)
    else:
        # Fallback: keyword overlap (when embeddings not computed yet)
        import re as _re
        stop_words = {
            "the","a","an","is","are","was","were","be","been","being","have","has","had",
            "do","does","did","will","would","could","should","may","might","can","shall",
            "to","of","in","for","on","with","at","by","from","as","into","about","like",
            "through","after","over","between","out","up","down","off","and","but","or",
            "nor","not","no","so","yet","both","either","this","that","these","those",
            "it","its","they","them","their","we","us","our","you","your","he","him","his",
            "she","her","who","which","what","when","where","how","why","all","each","every",
            "any","some","most","more","than","very","just","only","also","much","many",
            "such","own","other","one","two","new","get","got","make","made","thing",
            "things","way","time","people",
        }
        def _tokenize(text):
            return {w for w in _re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in stop_words}

        founder_kw = set()
        for _, data in graph.nodes(data=True):
            for field in ("label","stance","summary","description","applies_to","definition","left","right"):
                founder_kw |= _tokenize(data.get(field, ""))

        if q:
            all_result = search_posts(query=q, page=1, page_size=5000)
        else:
            all_result = browse_posts(
                page=1, page_size=5000,
                min_likes=min_likes, max_likes=max_likes,
                min_comments=min_comments, max_comments=max_comments,
                source_sheet=source_sheet,
            )

        scored = []
        for p in all_result["posts"]:
            post_words = set(_re.findall(r"[a-z]{3,}", p["content"].lower()))
            overlap = founder_kw & post_words
            match_pct = round(len(overlap) / max(len(post_words), 1) * 100, 1)
            scored.append({**p, "match_score": match_pct, "matched_keywords": len(overlap), "semantic": False})
        n_profile = len(founder_kw)

    scored.sort(key=lambda x: x["match_score"], reverse=True)

    # Deep reranking with Haiku: take top 50 embedding candidates → LLM score
    used_deep = False
    if deep and api_key and len(scored) > 0:
        profile_sentences = _build_founder_profile_sentences(graph)
        top_candidates = scored[:50]
        scored_deep = await _haiku_rerank(top_candidates, profile_sentences, founder_slug, api_key)
        scored = scored_deep + scored[50:]
        scored.sort(key=lambda x: x["match_score"], reverse=True)
        used_deep = True

    total = len(scored)
    start = (page - 1) * page_size
    page_items = scored[start:start + page_size]

    sources = [
        {
            "id": p["post_id"],
            "content": p["content"],
            "likes": p["likes"],
            "comments": p["comments"],
            "reposts": p["reposts"],
            "creator": p.get("creator_url", ""),
            "content_type": p.get("content_type", ""),
            "source": "csv",
            "engagement_score": p.get("engagement_score", 0),
            "source_sheet": p.get("source_sheet", ""),
            "match_score": p["match_score"],
            "matched_keywords": p.get("matched_keywords", 0),
            "topic_score": p.get("topic_score"),
            "mechanics_score": p.get("mechanics_score"),
            "audience_score": p.get("audience_score"),
            "match_reason": p.get("match_reason", ""),
        }
        for p in page_items
    ]

    return {
        "sources": sources,
        "total": total,
        "founder_profile_nodes": n_profile,
        "semantic": use_semantic,
        "deep": used_deep,
    }


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
