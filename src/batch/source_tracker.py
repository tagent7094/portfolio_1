"""Track which viral source posts have been used per founder."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "founders"


def _hash_source(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _index_path(slug: str) -> Path:
    return DATA_DIR / slug / ".used_sources.json"


def _load_index(slug: str) -> dict:
    path = _index_path(slug)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "entries": []}


def _save_index(slug: str, index: dict):
    path = _index_path(slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def load_used_sources(slug: str) -> set[str]:
    index = _load_index(slug)
    return {e["source_hash"] for e in index.get("entries", [])}


def load_used_sources_full(slug: str) -> list[dict]:
    index = _load_index(slug)
    return index.get("entries", [])


def is_source_used(slug: str, text: str) -> bool:
    return _hash_source(text) in load_used_sources(slug)


def record_used_sources(slug: str, sources: list[str], batch_filename: str):
    index = _load_index(slug)
    existing_hashes = {e["source_hash"] for e in index.get("entries", [])}
    now = datetime.now(IST).isoformat()

    added = 0
    for text in sources:
        h = _hash_source(text)
        if h not in existing_hashes:
            index["entries"].append({
                "source_hash": h,
                "source_snippet": text[:120].replace("\n", " "),
                "used_in_batch": batch_filename,
                "used_at": now,
            })
            existing_hashes.add(h)
            added += 1

    _save_index(slug, index)
    logger.info("[source_tracker] Recorded %d new sources for %s (total: %d)", added, slug, len(index["entries"]))
