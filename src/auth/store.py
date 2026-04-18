"""Founder credential store at config/founder-auth.yaml."""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_hash(slug: str) -> str | None:
    """Return the bcrypt hash for a founder slug, or None if not set."""
    data = _load()
    entry = data["founders"].get(slug)
    if not entry:
        return None
    return entry.get("password_hash")


def get_last_reset(slug: str) -> str | None:
    """Return the ISO-8601 timestamp of the last password reset, or None."""
    data = _load()
    entry = data["founders"].get(slug)
    if not entry:
        return None
    return entry.get("last_reset_at")


def has_password(slug: str) -> bool:
    """Check whether a founder has a password set."""
    return get_hash(slug) is not None


def set_password(slug: str, plain: str) -> None:
    """Hash a plaintext password and persist it for the given founder slug."""
    data = _load()
    # Preserve any existing fields (forward-compatible)
    existing = data["founders"].get(slug, {}) if isinstance(data["founders"].get(slug), dict) else {}
    existing["password_hash"] = hash_password(plain)
    existing["last_reset_at"] = _utc_now_iso()
    data["founders"][slug] = existing
    _save(data)


def generate_password(length: int = 14) -> str:
    """Generate a cryptographically-random alphanumeric password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def reset_password(slug: str, length: int = 14) -> str:
    """Generate a fresh random password, store the hash, return the plaintext ONCE.

    The plaintext is never persisted — only the bcrypt hash. Caller MUST show the
    returned string to the end user immediately; it cannot be retrieved again.
    """
    new_pw = generate_password(length)
    set_password(slug, new_pw)
    return new_pw


def list_slugs() -> list[str]:
    """Return all founder slugs that have credentials configured."""
    return sorted(_load()["founders"].keys())
