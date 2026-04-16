"""Page visibility permissions per founder + admin auth."""

from __future__ import annotations

from pathlib import Path

import yaml

from .passwords import hash_password, verify_password

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_PERMISSIONS_FILE = _PROJECT_ROOT / "config" / "founder-permissions.yaml"

ALL_PAGES = [
    "dashboard", "generate", "customize", "graph",
    "coverage", "workflow", "history", "config",
]


def _load() -> dict:
    if not _PERMISSIONS_FILE.exists():
        return {"defaults": {"pages": ["graph"]}, "founders": {}, "admin": {"password_hash": ""}}
    try:
        with open(_PERMISSIONS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return {"defaults": {"pages": ["graph"]}, "founders": {}, "admin": {"password_hash": ""}}
    data.setdefault("defaults", {"pages": ["graph"]})
    data.setdefault("founders", {})
    data.setdefault("admin", {"password_hash": ""})
    return data


def _save(data: dict) -> None:
    _PERMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_PERMISSIONS_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)


def get_pages(slug: str) -> list[str]:
    """Return allowed page IDs for a founder. Falls back to defaults."""
    data = _load()
    entry = data["founders"].get(slug)
    if entry and "pages" in entry:
        return entry["pages"]
    return data["defaults"].get("pages", ["graph"])


def set_pages(slug: str, pages: list[str]) -> None:
    """Set allowed pages for a founder."""
    data = _load()
    if slug not in data["founders"]:
        data["founders"][slug] = {}
    data["founders"][slug]["pages"] = [p for p in pages if p in ALL_PAGES]
    _save(data)


def get_all_permissions() -> dict:
    """Return full {slug: pages} mapping for the admin panel."""
    data = _load()
    result = {}
    for slug, entry in data["founders"].items():
        result[slug] = entry.get("pages", data["defaults"].get("pages", ["graph"]))
    return result


def get_default_pages() -> list[str]:
    return _load()["defaults"].get("pages", ["graph"])


# ── Admin credentials ──

def get_admin_hash() -> str | None:
    """Return the admin bcrypt hash, or None if not set."""
    h = _load()["admin"].get("password_hash", "")
    return h if h else None


def set_admin_password(plain: str) -> None:
    """Set the admin password."""
    data = _load()
    data["admin"]["password_hash"] = hash_password(plain)
    _save(data)


def verify_admin_password(plain: str) -> bool:
    """Verify admin password."""
    h = get_admin_hash()
    if not h:
        return False
    return verify_password(plain, h)
