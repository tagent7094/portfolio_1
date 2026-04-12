"""Founder credential store at config/founder-auth.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from .passwords import hash_password

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_AUTH_FILE = _PROJECT_ROOT / "config" / "founder-auth.yaml"


def _load() -> dict:
    if not _AUTH_FILE.exists():
        return {"founders": {}}
    try:
        with open(_AUTH_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return {"founders": {}}
    if "founders" not in data or not isinstance(data["founders"], dict):
        data["founders"] = {}
    return data


def _save(data: dict) -> None:
    _AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_AUTH_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=True)


def get_hash(slug: str) -> str | None:
    """Return the bcrypt hash for a founder slug, or None if not set."""
    data = _load()
    entry = data["founders"].get(slug)
    if not entry:
        return None
    return entry.get("password_hash")


def set_password(slug: str, plain: str) -> None:
    """Hash a plaintext password and persist it for the given founder slug."""
    data = _load()
    data["founders"][slug] = {"password_hash": hash_password(plain)}
    _save(data)


def list_slugs() -> list[str]:
    """Return all founder slugs that have credentials configured."""
    return sorted(_load()["founders"].keys())
