"""Per-subdomain password gate for tagent.club tenant sites.

Each subdomain (asksharath, askrevsure, ...) can have an independent
password set by an admin. When a subdomain entry has `enabled: true`,
non-auth API requests to that subdomain require an HTTP-only cookie
set by POST /api/subdomain/auth/login.

Storage: config/subdomain-passwords.yaml (gitignored). Hashes use bcrypt.

Endpoints (public):
    POST /api/subdomain/auth/login    {subdomain, password} → sets cookie
    POST /api/subdomain/auth/logout   → clears cookie
    GET  /api/subdomain/auth/me       → {authenticated, subdomain}

Endpoints (admin-only):
    GET  /api/admin/subdomain-passwords
    PUT  /api/admin/subdomain-passwords/{slug}
"""

from __future__ import annotations

import logging
import secrets
import time
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
PASSWORDS_PATH = PROJECT_ROOT / "config" / "subdomain-passwords.yaml"

COOKIE_NAME_PREFIX = "tagent_sub_"
COOKIE_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days

# Endpoint paths that should bypass the subdomain gate (always reachable
# so users can log in even when not yet authenticated).
GATE_EXEMPT_PATH_PREFIXES = (
    "/api/subdomain/auth/",
    "/api/admin/",          # admin auth is separate
    "/api/health",
    "/api/founders",        # used by initial UI hydration; harmless
)

router = APIRouter()
admin_router = APIRouter()


# ── Storage helpers ──────────────────────────────────────────────────────────


def _load_store() -> dict:
    if not PASSWORDS_PATH.exists():
        return {}
    try:
        data = yaml.safe_load(PASSWORDS_PATH.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("[subdomain_auth] failed to read %s: %s", PASSWORDS_PATH, e)
        return {}


def _save_store(data: dict) -> None:
    PASSWORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PASSWORDS_PATH.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=True),
        encoding="utf-8",
    )


def _hash_password(plain: str) -> str:
    import bcrypt
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        import bcrypt
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except Exception:
        return False


# ── Session tokens (stateless, signed via HMAC of a server secret) ──────────


_SERVER_SECRET: Optional[str] = None


def _get_secret() -> str:
    """Lazy-load a stable server secret from config/subdomain-passwords.yaml
    (a `_session_secret:` top-level key). Generated on first run if missing.
    """
    global _SERVER_SECRET
    if _SERVER_SECRET:
        return _SERVER_SECRET
    store = _load_store()
    secret = store.get("_session_secret")
    if not secret:
        secret = secrets.token_urlsafe(32)
        store["_session_secret"] = secret
        _save_store(store)
    _SERVER_SECRET = secret
    return secret


def _make_token(subdomain: str) -> str:
    import hmac, hashlib
    timestamp = str(int(time.time()))
    payload = f"{subdomain}|{timestamp}"
    sig = hmac.new(_get_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{payload}|{sig}"


def _verify_token(token: str, expected_subdomain: str) -> bool:
    import hmac, hashlib
    if not token or token.count("|") != 2:
        return False
    sub, ts, sig = token.split("|", 2)
    if sub != expected_subdomain:
        return False
    try:
        age = int(time.time()) - int(ts)
        if age < 0 or age > COOKIE_MAX_AGE_SECONDS:
            return False
    except Exception:
        return False
    expected_sig = hmac.new(_get_secret().encode("utf-8"), f"{sub}|{ts}".encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, expected_sig)


# ── Subdomain extraction ─────────────────────────────────────────────────────


def get_request_subdomain(request: Request) -> Optional[str]:
    """Pull the subdomain slug from the Host header.

    `asksharath.tagent.club`  → "asksharath"
    `askrevsure.tagent.club`  → "askrevsure"
    `tagent.club`             → None (apex)
    `localhost`               → None (local dev)
    """
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if not host or host in ("tagent.club", "www.tagent.club"):
        return None
    if host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith("127.") or host[0].isdigit():
        return None
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2:] == ["tagent", "club"]:
        return parts[0].replace("-", "_")
    return None


# ── Middleware: gate non-auth requests on gated subdomains ──────────────────


async def gate_middleware(request: Request, call_next):
    """FastAPI middleware. Apply to webapp/server.py with
    `app.middleware("http")(gate_middleware)`.
    """
    path = request.url.path or "/"
    for prefix in GATE_EXEMPT_PATH_PREFIXES:
        if path.startswith(prefix):
            return await call_next(request)
    if not path.startswith("/api/"):
        # Non-API requests (static assets, the SPA itself) are always served;
        # the frontend handles the password gate UI.
        return await call_next(request)

    subdomain = get_request_subdomain(request)
    if not subdomain:
        return await call_next(request)

    store = _load_store()
    entry = store.get(subdomain) or {}
    if not entry.get("enabled"):
        # Subdomain not registered for gating, or disabled — let through.
        return await call_next(request)

    cookie_name = f"{COOKIE_NAME_PREFIX}{subdomain}"
    token = request.cookies.get(cookie_name, "")
    if _verify_token(token, subdomain):
        return await call_next(request)

    return Response(
        content='{"detail":"Authentication required for this subdomain"}',
        status_code=401,
        media_type="application/json",
    )


# ── Public endpoints ─────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    subdomain: str
    password: str


@router.post("/api/subdomain/auth/login")
async def subdomain_login(data: LoginRequest, response: Response):
    sub = (data.subdomain or "").strip().lower()
    if not sub:
        raise HTTPException(status_code=400, detail="subdomain required")
    store = _load_store()
    entry = store.get(sub) or {}
    if not entry.get("enabled"):
        raise HTTPException(status_code=404, detail="subdomain not configured for auth")
    if not _verify_password(data.password, entry.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="incorrect password")
    token = _make_token(sub)
    response.set_cookie(
        key=f"{COOKIE_NAME_PREFIX}{sub}",
        value=token,
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,  # nginx terminates SSL; cookie still functions over the proxy
    )
    return {"authenticated": True, "subdomain": sub}


@router.post("/api/subdomain/auth/logout")
async def subdomain_logout(request: Request, response: Response):
    sub = get_request_subdomain(request) or ""
    if sub:
        response.delete_cookie(f"{COOKIE_NAME_PREFIX}{sub}")
    return {"authenticated": False, "subdomain": sub}


@router.get("/api/subdomain/auth/me")
async def subdomain_me(request: Request):
    sub = get_request_subdomain(request)
    if not sub:
        return {"authenticated": False, "subdomain": None, "enabled": False}
    store = _load_store()
    entry = store.get(sub) or {}
    if not entry.get("enabled"):
        # No gate on this subdomain → effectively "authenticated"
        return {"authenticated": True, "subdomain": sub, "enabled": False}
    token = request.cookies.get(f"{COOKIE_NAME_PREFIX}{sub}", "")
    return {
        "authenticated": _verify_token(token, sub),
        "subdomain": sub,
        "enabled": True,
    }


# ── Admin endpoints ──────────────────────────────────────────────────────────


class UpdatePasswordRequest(BaseModel):
    new_password: Optional[str] = None
    enabled: Optional[bool] = None


@admin_router.get("/api/admin/subdomain-passwords")
async def admin_list_subdomains():
    store = _load_store()
    out = []
    for slug, entry in store.items():
        if slug.startswith("_"):
            continue
        if not isinstance(entry, dict):
            continue
        out.append({
            "subdomain": slug,
            "enabled": bool(entry.get("enabled")),
            "has_password": bool(entry.get("password_hash")),
            "updated_at": entry.get("updated_at", ""),
            "updated_by": entry.get("updated_by", ""),
        })
    return {"subdomains": sorted(out, key=lambda x: x["subdomain"])}


@admin_router.put("/api/admin/subdomain-passwords/{slug}")
async def admin_set_subdomain(slug: str, data: UpdatePasswordRequest):
    slug = (slug or "").strip().lower()
    if not slug or slug.startswith("_"):
        raise HTTPException(status_code=400, detail="invalid subdomain slug")
    store = _load_store()
    entry = store.get(slug) or {}
    if data.new_password is not None and data.new_password.strip():
        if len(data.new_password) < 6:
            raise HTTPException(status_code=400, detail="password must be at least 6 characters")
        entry["password_hash"] = _hash_password(data.new_password)
    if data.enabled is not None:
        entry["enabled"] = bool(data.enabled)
    entry["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry["updated_by"] = "admin"
    store[slug] = entry
    _save_store(store)
    return {
        "subdomain": slug,
        "enabled": bool(entry.get("enabled")),
        "has_password": bool(entry.get("password_hash")),
        "updated_at": entry.get("updated_at", ""),
    }
