"""Pack history persistence — 30-day rolling per-founder record.

Per ORCHESTRATOR_SPEC §6 / README §"Cross-pack scene history persistence".

Used to:
- Compute anchor freshness (fresh / used_recently / saturated) in
  `00_anchor_inventory.txt`
- Cross-pack saturation check in `05_validate.txt`
- Root cause analysis in `06_compile.txt`

Storage: JSON file at `data/founders/<slug>/pack_history.json`.
Auto-pruned to last 90 days on each read; 30-day window is the query default.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_RETAIN_DAYS = 90  # hard storage cap; queries default to 30


def _history_path(founder_slug: str) -> Path:
    return _PROJECT_ROOT / "data" / "founders" / founder_slug / "pack_history.json"


def _parse_iso(ts: str) -> datetime | None:
    try:
        # Allow either "...Z" or "+00:00"
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def load_pack_history(founder_slug: str, days: int = 30) -> list[dict]:
    """Load this founder's pack history within the last `days` days.

    Each record is a dict with at minimum: timestamp (ISO), pack_id,
    anchors_used (list of anchor records or IDs), voice_markers_used.
    Returns an empty list when the file doesn't exist.
    Auto-prunes records older than _RETAIN_DAYS as a side effect.
    """
    path = _history_path(founder_slug)
    if not path.exists():
        return []

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        records: list[dict] = raw.get("history", []) if isinstance(raw, dict) else (raw or [])
    except Exception as e:
        logger.warning("[pack_history] failed to read %s: %s", path, e)
        return []

    now = datetime.utcnow()
    retain_cutoff = now - timedelta(days=_RETAIN_DAYS)
    query_cutoff = now - timedelta(days=days)

    # Prune to retention window.
    pruned: list[dict] = []
    for r in records:
        ts = _parse_iso(r.get("timestamp", ""))
        if ts and ts.replace(tzinfo=None) >= retain_cutoff.replace(tzinfo=retain_cutoff.tzinfo):
            pruned.append(r)

    if len(pruned) < len(records):
        try:
            path.write_text(
                json.dumps({"history": pruned}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(
                "[pack_history] pruned %d → %d records (>%dd) for %s",
                len(records), len(pruned), _RETAIN_DAYS, founder_slug,
            )
        except Exception as e:
            logger.warning("[pack_history] failed to write pruned %s: %s", path, e)

    # Filter to query window.
    out = []
    for r in pruned:
        ts = _parse_iso(r.get("timestamp", ""))
        if ts and ts.replace(tzinfo=None) >= query_cutoff.replace(tzinfo=query_cutoff.tzinfo):
            out.append(r)
    return out


def append_pack_to_history(
    founder_slug: str,
    pack_id: str,
    anchors_used: list,
    voice_markers_used: list,
) -> None:
    """Append a freshly-shipped pack to the founder's history file."""
    path = _history_path(founder_slug)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            records: list[dict] = existing.get("history", []) if isinstance(existing, dict) else (existing or [])
        except Exception:
            records = []
    else:
        records = []

    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "pack_id": pack_id,
        "anchors_used": list(anchors_used or []),
        "voice_markers_used": list(voice_markers_used or []),
    }
    records.append(record)

    try:
        path.write_text(
            json.dumps({"history": records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "[pack_history] appended pack %s for %s (history size %d)",
            pack_id, founder_slug, len(records),
        )
    except Exception as e:
        logger.warning("[pack_history] failed to append to %s: %s", path, e)
