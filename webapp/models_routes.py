"""Admin + founder API endpoints for the Models & Providers config page.

Mirrors the notify-config pattern at server.py:85-109 — JSON file on disk,
admin auth via _require_admin, founder auth via _require_founder (which
already permits admin-as-founder). All write endpoints validate task IDs
against the canonical TASK_CATALOG.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from src.llm.config_io import (
    delete_founder_override_task,
    load_admin_config,
    load_founder_override,
    mask_provider_keys,
    merged_config_for_founder,
    save_admin_config,
    save_admin_keys_only,
    save_founder_keys_only,
    save_founder_override,
)
from src.llm.provider_catalog import provider_catalog_with_env_status
from src.llm.task_catalog import TASK_CATALOG, task_catalog_dict, validate_task_id
from src.llm.test_provider import quick_test

logger = logging.getLogger(__name__)

router = APIRouter(tags=["models"])


def _strip_synth(cfg: dict) -> dict:
    """Don't ship the internal _synthesized flag to the client."""
    if isinstance(cfg, dict) and "_synthesized" in cfg:
        cfg = {k: v for k, v in cfg.items() if k != "_synthesized"}
    return cfg


# ---------- admin endpoints ----------


@router.get("/api/admin/models/providers")
async def get_models_providers(request: Request) -> dict:
    # No auth — read-only catalog with no secrets (just model lists + key_present booleans)
    admin_cfg = load_admin_config()
    stored_keys = admin_cfg.get("provider_keys", {})
    return {"providers": provider_catalog_with_env_status(stored_keys=stored_keys)}


@router.get("/api/admin/models/tasks")
async def get_models_tasks(request: Request) -> dict:
    # No auth — read-only catalog, no secrets
    return {"tasks": task_catalog_dict()}


@router.get("/api/admin/models/config")
async def get_admin_models_config(request: Request) -> dict:
    from webapp.auth_routes import _require_admin
    _require_admin(request)
    cfg = _strip_synth(load_admin_config())
    cfg["provider_keys"] = mask_provider_keys(cfg.get("provider_keys", {}))
    return cfg


@router.put("/api/admin/models/config")
async def put_admin_models_config(request: Request) -> dict:
    from webapp.auth_routes import _require_admin
    _require_admin(request)
    body = await request.json()
    try:
        saved = save_admin_config(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _strip_synth(saved)


@router.post("/api/admin/models/test")
async def admin_test_provider(request: Request) -> dict:
    from webapp.auth_routes import _require_admin
    _require_admin(request)
    body = await request.json()
    provider = (body or {}).get("provider", "")
    model = (body or {}).get("model", "")
    api_key = (body or {}).get("api_key") or None
    base_url = (body or {}).get("base_url") or None
    if not provider or not model:
        raise HTTPException(status_code=400, detail="provider and model required")
    result = await asyncio.to_thread(quick_test, provider, model, api_key, base_url)
    return result


@router.put("/api/admin/models/keys")
async def put_admin_models_keys(request: Request) -> dict:
    from webapp.auth_routes import _require_admin
    _require_admin(request)
    body = await request.json()
    keys = body.get("provider_keys")
    if not isinstance(keys, dict):
        raise HTTPException(status_code=400, detail="provider_keys dict required")
    saved = save_admin_keys_only(keys)
    return {"provider_keys": saved}


# ---------- founder endpoints ----------


@router.get("/api/founders/{slug}/models/config")
async def get_founder_models_config(slug: str, request: Request) -> dict:
    from webapp.pack_routes import _require_founder
    _require_founder(request, slug)
    merged = merged_config_for_founder(slug)
    merged["admin_defaults"] = _strip_synth(merged.get("admin_defaults", {}))
    merged["admin_defaults"].pop("provider_keys", None)
    return merged


@router.put("/api/founders/{slug}/models/config")
async def put_founder_models_config(slug: str, request: Request) -> dict:
    from webapp.pack_routes import _require_founder
    _require_founder(request, slug)
    body = await request.json()
    try:
        saved = save_founder_override(slug, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return saved


@router.delete("/api/founders/{slug}/models/config/{task_id}")
async def delete_founder_models_task(slug: str, task_id: str, request: Request) -> dict:
    from webapp.pack_routes import _require_founder
    _require_founder(request, slug)
    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail=f"unknown task_id: {task_id!r}")
    return delete_founder_override_task(slug, task_id)


@router.post("/api/founders/{slug}/models/test")
async def founder_test_provider(slug: str, request: Request) -> dict:
    from webapp.pack_routes import _require_founder
    _require_founder(request, slug)
    body = await request.json()
    provider = (body or {}).get("provider", "")
    model = (body or {}).get("model", "")
    api_key = (body or {}).get("api_key") or None
    base_url = (body or {}).get("base_url") or None
    if not provider or not model:
        raise HTTPException(status_code=400, detail="provider and model required")
    result = await asyncio.to_thread(quick_test, provider, model, api_key, base_url)
    return result


@router.put("/api/founders/{slug}/models/keys")
async def put_founder_models_keys(slug: str, request: Request) -> dict:
    from webapp.pack_routes import _require_founder
    _require_founder(request, slug)
    body = await request.json()
    keys = body.get("provider_keys")
    if not isinstance(keys, dict):
        raise HTTPException(status_code=400, detail="provider_keys dict required")
    saved = save_founder_keys_only(slug, keys)
    return {"provider_keys": saved}
