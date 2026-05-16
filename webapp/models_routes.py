"""Admin + founder API endpoints for the Models & Providers config page.

Mirrors the notify-config pattern at server.py:85-109 — JSON file on disk,
admin auth via _require_admin, founder auth via _require_founder (which
already permits admin-as-founder). All write endpoints validate task IDs
against the canonical TASK_CATALOG.

Config sync: when TAGENT_VPS_URL + DEPLOY_SECRET are set, every config save
also POSTs the full config to the VPS sync endpoint so both environments
stay identical without committing secrets to git.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from src.llm.config_io import (
    ADMIN_CONFIG_PATH,
    _founder_override_path,
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


# ---------- VPS config sync ----------


async def _sync_to_vps(payload: dict) -> None:
    """POST config to VPS so it stays in sync. Requires TAGENT_VPS_URL + DEPLOY_SECRET."""
    vps_url = os.environ.get("TAGENT_VPS_URL", "").rstrip("/")
    secret = os.environ.get("DEPLOY_SECRET", "")
    if not vps_url or not secret:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{vps_url}/api/admin/models/sync",
                json=payload,
                headers={"x-sync-secret": secret},
            )
            if resp.status_code == 200:
                logger.info("[config_sync] synced to VPS (%s)", vps_url)
            else:
                logger.warning("[config_sync] VPS returned %d: %s", resp.status_code, resp.text[:200])
    except Exception:
        logger.warning("[config_sync] VPS sync failed — config saved locally only", exc_info=True)


@router.post("/api/admin/models/sync")
async def sync_receive(request: Request) -> dict:
    """Receive config from another environment. Auth via X-Sync-Secret header."""
    expected = os.environ.get("DEPLOY_SECRET", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="sync not configured")
    incoming = (request.headers.get("x-sync-secret") or "").strip()
    if incoming != expected:
        raise HTTPException(status_code=401, detail="invalid sync secret")
    body = await request.json()
    saved = {}
    if "admin_config" in body:
        try:
            saved["admin"] = bool(save_admin_config(body["admin_config"]))
        except ValueError as e:
            saved["admin_error"] = str(e)
    for key, val in body.items():
        if key.startswith("founder:") and isinstance(val, dict):
            slug = key.split(":", 1)[1]
            try:
                save_founder_override(slug, val)
                saved[key] = True
            except ValueError as e:
                saved[f"{key}_error"] = str(e)
    logger.info("[config_sync] received sync: %s", list(body.keys()))
    return {"ok": True, "saved": saved}


def _strip_synth(cfg: dict) -> dict:
    """Don't ship the internal _synthesized flag to the client."""
    if isinstance(cfg, dict) and "_synthesized" in cfg:
        cfg = {k: v for k, v in cfg.items() if k != "_synthesized"}
    return cfg


# ---------- admin endpoints ----------


@router.get("/api/admin/models/providers")
async def get_models_providers(request: Request) -> dict:
    admin_cfg = load_admin_config()
    stored_keys = admin_cfg.get("provider_keys", {})
    return {"providers": provider_catalog_with_env_status(stored_keys=stored_keys)}


@router.get("/api/admin/models/tasks")
async def get_models_tasks(request: Request) -> dict:
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
    asyncio.create_task(_sync_to_vps({"admin_config": saved}))
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
    full_cfg = load_admin_config()
    asyncio.create_task(_sync_to_vps({"admin_config": full_cfg}))
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
    asyncio.create_task(_sync_to_vps({f"founder:{slug}": saved}))
    return saved


@router.delete("/api/founders/{slug}/models/config/{task_id}")
async def delete_founder_models_task(slug: str, task_id: str, request: Request) -> dict:
    from webapp.pack_routes import _require_founder
    _require_founder(request, slug)
    if not validate_task_id(task_id):
        raise HTTPException(status_code=400, detail=f"unknown task_id: {task_id!r}")
    result = delete_founder_override_task(slug, task_id)
    asyncio.create_task(_sync_to_vps({f"founder:{slug}": result}))
    return result


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
    founder_cfg = load_founder_override(slug)
    asyncio.create_task(_sync_to_vps({f"founder:{slug}": founder_cfg}))
    return {"provider_keys": saved}
