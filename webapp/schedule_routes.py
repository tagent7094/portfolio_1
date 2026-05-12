"""
Schedule routes: recurring batch generation.

Schedules persist in data/schedules.json and run via an asyncio background loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, time, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from webapp.auth_routes import _require_admin

router = APIRouter(prefix="/api/admin/schedules", tags=["admin-schedules"])
logger = logging.getLogger(__name__)

SCHEDULES_FILE = Path(__file__).parent.parent / "data" / "schedules.json"

_schedules: list[dict] = []
_running_loop: asyncio.Task | None = None


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
    SCHEDULES_FILE.write_text(json.dumps(_schedules, indent=2), encoding="utf-8")


class ScheduleCreate(BaseModel):
    founder_slug: str
    hour: int = 9
    minute: int = 0
    days: list[str] = ["mon", "tue", "wed", "thu", "fri"]
    n_sources: int = 3
    creativity: float = 0.5
    effort: str = "high"
    enabled: bool = True


@router.get("")
async def list_schedules(request: Request):
    _require_admin(request)
    return {"schedules": _schedules}


@router.post("")
async def create_schedule(body: ScheduleCreate, request: Request):
    _require_admin(request)
    schedule = {
        "id": uuid.uuid4().hex[:8],
        "founder_slug": body.founder_slug,
        "hour": body.hour,
        "minute": body.minute,
        "days": body.days,
        "n_sources": body.n_sources,
        "creativity": body.creativity,
        "effort": body.effort,
        "enabled": body.enabled,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
        "last_status": None,
    }
    _schedules.append(schedule)
    _save_schedules()
    logger.info("[schedule] Created: %s for %s at %02d:%02d",
                schedule["id"], body.founder_slug, body.hour, body.minute)
    return schedule


@router.put("/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleCreate, request: Request):
    _require_admin(request)
    for s in _schedules:
        if s["id"] == schedule_id:
            s.update({
                "founder_slug": body.founder_slug,
                "hour": body.hour,
                "minute": body.minute,
                "days": body.days,
                "n_sources": body.n_sources,
                "creativity": body.creativity,
                "effort": body.effort,
                "enabled": body.enabled,
            })
            _save_schedules()
            return s
    raise HTTPException(status_code=404, detail="Schedule not found")


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str, request: Request):
    _require_admin(request)
    global _schedules
    before = len(_schedules)
    _schedules = [s for s in _schedules if s["id"] != schedule_id]
    if len(_schedules) == before:
        raise HTTPException(status_code=404, detail="Schedule not found")
    _save_schedules()
    return {"ok": True}


@router.post("/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str, request: Request):
    _require_admin(request)
    for s in _schedules:
        if s["id"] == schedule_id:
            s["enabled"] = not s["enabled"]
            _save_schedules()
            return s
    raise HTTPException(status_code=404, detail="Schedule not found")


async def _run_scheduled_generation(schedule: dict):
    """Execute a scheduled generation run."""
    logger.info("[scheduler] Running for %s (schedule %s)", schedule["founder_slug"], schedule["id"])
    try:
        from src.batch.session import BatchSession
        session = BatchSession()
        await asyncio.to_thread(
            session.run,
            founder_slug=schedule["founder_slug"],
            platform="linkedin",
            creativity=schedule.get("creativity", 0.5),
            n_sources=schedule.get("n_sources", 3),
            posts_per_source=9,
            enable_thinking=True,
            effort=schedule.get("effort", "high"),
        )
        schedule["last_status"] = "success"
    except Exception as e:
        logger.exception("[scheduler] Failed for %s: %s", schedule["founder_slug"], e)
        schedule["last_status"] = f"error: {str(e)[:100]}"
    schedule["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_schedules()


async def _scheduler_loop():
    """Background loop that checks schedules every 60 seconds."""
    _load_schedules()
    day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

    while True:
        await asyncio.sleep(60)
        now = datetime.now(timezone.utc)
        weekday = now.weekday()
        current_time = (now.hour, now.minute)

        for schedule in _schedules:
            if not schedule.get("enabled", True):
                continue

            sched_days = [day_map.get(d.lower()[:3], -1) for d in schedule.get("days", [])]
            if weekday not in sched_days:
                continue

            if current_time != (schedule.get("hour", 9), schedule.get("minute", 0)):
                continue

            last_run = schedule.get("last_run")
            if last_run:
                try:
                    lr = datetime.fromisoformat(last_run)
                    if (now - lr).total_seconds() < 3600:
                        continue
                except Exception:
                    pass

            asyncio.create_task(_run_scheduled_generation(schedule))


def start_scheduler():
    """Call once at app startup."""
    global _running_loop
    _load_schedules()
    if _running_loop is None or _running_loop.done():
        _running_loop = asyncio.create_task(_scheduler_loop())
        logger.info("[scheduler] Background scheduler started")
