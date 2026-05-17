"""
Schedule routes: recurring batch generation.

Schedules persist in data/schedules.json and run via an asyncio background loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from webapp.auth_routes import _require_admin, decode_token

router = APIRouter(prefix="/api/admin/schedules", tags=["admin-schedules"])
logger = logging.getLogger(__name__)

_ADMIN_COOKIE = "admin_token"
_FOUNDER_COOKIE = "tagent_token"


def _resolve_caller(request: Request) -> tuple[str, bool]:
    """Return (slug, is_admin). Founders can manage only their own schedules;
    admins can manage all. Raises 401 if neither cookie is valid.

    Auth is bypassed when TAGENT_AUTH_ENABLED is unset (local dev mode) —
    caller is treated as admin in that case.
    """
    if os.environ.get("TAGENT_AUTH_ENABLED", "").lower() not in ("1", "true", "yes"):
        return ("admin", True)

    admin_claims = decode_token(request.cookies.get(_ADMIN_COOKIE, ""))
    if admin_claims and admin_claims.get("sub") == "admin":
        return ("admin", True)

    founder_claims = decode_token(request.cookies.get(_FOUNDER_COOKIE, ""))
    if founder_claims and founder_claims.get("sub"):
        return (founder_claims["sub"], False)

    raise HTTPException(status_code=401, detail="authentication required")


def _check_owns(slug: str, is_admin: bool, schedule: dict) -> bool:
    return is_admin or schedule.get("founder_slug") == slug

SCHEDULES_FILE = Path(__file__).parent.parent / "data" / "schedules.json"
IST = timezone(timedelta(hours=5, minutes=30))

_schedules: list[dict] = []
_running_loop: asyncio.Task | None = None
_tick_count: int = 0
_last_tick: str | None = None


def _load_schedules():
    global _schedules
    if SCHEDULES_FILE.exists():
        try:
            _schedules = json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
        except Exception:
            _schedules = []
    else:
        _schedules = []


def _save_schedules():
    SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SCHEDULES_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_schedules, indent=2), encoding="utf-8")
    tmp.replace(SCHEDULES_FILE)


class ScheduleCreate(BaseModel):
    founder_slug: str
    hour: int = 9
    minute: int = 0
    days: list[str] = ["mon", "tue", "wed", "thu", "fri"]
    n_sources: int = 3
    posts_per_source: int = 9
    creativity: float = 0.5
    effort: str = "high"
    enable_thinking: bool = True
    enabled: bool = True


@router.get("/status")
async def scheduler_status(request: Request):
    _require_admin(request)  # admin-only — exposes global tick state
    return {
        "running": _running_loop is not None and not _running_loop.done(),
        "tick_count": _tick_count,
        "last_tick": _last_tick,
        "enabled_count": sum(1 for s in _schedules if s.get("enabled")),
        "total_count": len(_schedules),
    }


@router.get("")
async def list_schedules(request: Request):
    slug, is_admin = _resolve_caller(request)
    if is_admin:
        return {"schedules": _schedules}
    # Founders see only their own schedules.
    return {"schedules": [s for s in _schedules if s.get("founder_slug") == slug]}


@router.post("")
async def create_schedule(body: ScheduleCreate, request: Request):
    slug, is_admin = _resolve_caller(request)
    # Founders may only create schedules for themselves.
    if not is_admin and body.founder_slug != slug:
        raise HTTPException(status_code=403, detail=f"founder '{slug}' cannot schedule for '{body.founder_slug}'")
    schedule = {
        "id": uuid.uuid4().hex[:8],
        "founder_slug": body.founder_slug,
        "hour": body.hour,
        "minute": body.minute,
        "days": body.days,
        "n_sources": body.n_sources,
        "posts_per_source": body.posts_per_source,
        "creativity": body.creativity,
        "effort": body.effort,
        "enable_thinking": body.enable_thinking,
        "enabled": body.enabled,
        "created_at": datetime.now(IST).isoformat(),
        "created_by": "admin" if is_admin else slug,
        "last_run": None,
        "last_status": None,
    }
    _schedules.append(schedule)
    _save_schedules()
    logger.info("[schedule] Created: %s for %s at %02d:%02d by %s",
                schedule["id"], body.founder_slug, body.hour, body.minute,
                "admin" if is_admin else slug)
    return schedule


@router.put("/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleCreate, request: Request):
    slug, is_admin = _resolve_caller(request)
    for s in _schedules:
        if s["id"] == schedule_id:
            if not _check_owns(slug, is_admin, s):
                raise HTTPException(status_code=403, detail="not your schedule")
            # Founders cannot move a schedule to a different founder.
            if not is_admin and body.founder_slug != slug:
                raise HTTPException(status_code=403, detail="cannot reassign schedule to another founder")
            s.update({
                "founder_slug": body.founder_slug,
                "hour": body.hour,
                "minute": body.minute,
                "days": body.days,
                "n_sources": body.n_sources,
                "posts_per_source": body.posts_per_source,
                "creativity": body.creativity,
                "effort": body.effort,
                "enable_thinking": body.enable_thinking,
                "enabled": body.enabled,
            })
            _save_schedules()
            return s
    raise HTTPException(status_code=404, detail="Schedule not found")


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str, request: Request):
    slug, is_admin = _resolve_caller(request)
    global _schedules
    target = next((s for s in _schedules if s["id"] == schedule_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if not _check_owns(slug, is_admin, target):
        raise HTTPException(status_code=403, detail="not your schedule")
    _schedules = [s for s in _schedules if s["id"] != schedule_id]
    _save_schedules()
    return {"ok": True}


@router.post("/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str, request: Request):
    slug, is_admin = _resolve_caller(request)
    for s in _schedules:
        if s["id"] == schedule_id:
            if not _check_owns(slug, is_admin, s):
                raise HTTPException(status_code=403, detail="not your schedule")
            s["enabled"] = not s["enabled"]
            _save_schedules()
            return s
    raise HTTPException(status_code=404, detail="Schedule not found")


@router.post("/{schedule_id}/run-now")
async def run_schedule_now(schedule_id: str, request: Request):
    slug, is_admin = _resolve_caller(request)
    for s in _schedules:
        if s["id"] == schedule_id:
            if not _check_owns(slug, is_admin, s):
                raise HTTPException(status_code=403, detail="not your schedule")
            asyncio.create_task(_run_scheduled_generation(s))
            return {"ok": True, "message": f"Started generation for {s['founder_slug']}"}
    raise HTTPException(status_code=404, detail="Schedule not found")


async def _run_scheduled_generation(schedule: dict):
    """Execute a scheduled generation run."""
    logger.info("[scheduler] Running for %s (schedule %s)", schedule["founder_slug"], schedule["id"])
    try:
        from src.batch.session import BatchSession
        session = BatchSession()
        result = await asyncio.to_thread(
            session.run,
            founder_slug=schedule["founder_slug"],
            platform="linkedin",
            creativity=schedule.get("creativity", 0.5),
            n_sources=schedule.get("n_sources", 3),
            posts_per_source=schedule.get("posts_per_source", 9),
            enable_thinking=schedule.get("enable_thinking", True),
            effort=schedule.get("effort", "high"),
        )
        schedule["last_status"] = "success"
        try:
            from src.batch.notify import send_batch_notification
            await asyncio.to_thread(
                send_batch_notification,
                founder_slug=schedule["founder_slug"],
                total_posts=(result or {}).get("metadata", {}).get("total_posts", 0),
                trigger="scheduled",
                schedule_id=schedule["id"],
            )
        except Exception:
            logger.warning("[scheduler] Email notification failed", exc_info=True)
    except Exception as e:
        logger.exception("[scheduler] Failed for %s: %s", schedule["founder_slug"], e)
        schedule["last_status"] = f"error: {str(e)[:100]}"
    schedule["last_run"] = datetime.now(IST).isoformat()
    _save_schedules()


_last_fired: dict[str, str] = {}


async def _scheduler_loop():
    """Background loop that checks schedules every 30 seconds."""
    global _tick_count, _last_tick
    _load_schedules()
    day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

    while True:
        await asyncio.sleep(30)
        _tick_count += 1
        now = datetime.now(IST)
        _last_tick = now.isoformat()
        weekday = now.weekday()
        current_time = (now.hour, now.minute)
        time_key = now.strftime("%Y-%m-%d %H:%M")
        logger.debug("[scheduler] tick #%d at %s IST (%d schedules loaded)", _tick_count, now.isoformat(), len(_schedules))

        for schedule in _schedules:
            try:
                if not schedule.get("enabled", True):
                    continue

                sched_days = [day_map.get(d.lower()[:3], -1) for d in schedule.get("days", [])]
                if weekday not in sched_days:
                    continue

                if current_time != (schedule.get("hour", 9), schedule.get("minute", 0)):
                    continue

                sid = schedule.get("id", schedule.get("founder_slug", ""))
                if _last_fired.get(sid) == time_key:
                    continue

                last_run = schedule.get("last_run")
                if last_run:
                    try:
                        lr = datetime.fromisoformat(last_run)
                        if (now - lr).total_seconds() < 3600:
                            continue
                    except Exception:
                        pass

                _last_fired[sid] = time_key
                logger.info("[scheduler] FIRING schedule %s for %s at %s", sid, schedule.get("founder_slug"), time_key)
                asyncio.create_task(_run_scheduled_generation(schedule))
            except Exception:
                logger.exception("[scheduler] Error checking schedule %s", schedule.get("id", "?"))


def start_scheduler():
    """Call once at app startup."""
    global _running_loop
    _load_schedules()
    if _running_loop is None or _running_loop.done():
        _running_loop = asyncio.create_task(_scheduler_loop())
        logger.info("[scheduler] Background scheduler started")
