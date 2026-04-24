"""Auth endpoints: founder login/logout/me, permissions, password change, admin."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from src.auth import context as auth_context
from src.auth.passwords import verify_password
from src.auth.permissions import get_pages, get_all_permissions, set_pages, verify_admin_password, ALL_PAGES
from src.auth.store import get_hash, get_last_reset, has_password, reset_password, set_password
from src.auth.tokens import decode_token, issue_token
from src.config.founders import get_founder_paths
from webapp.auth_middleware import _resolve_subdomain_slug

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])

_COOKIE_NAME = "tagent_token"
_ADMIN_COOKIE_NAME = "admin_token"
_COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days


# ── Helpers ──

def _cookie_kwargs(name: str = _COOKIE_NAME) -> dict:
    secure = os.environ.get("TAGENT_COOKIE_SECURE", "").lower() in ("1", "true", "yes")
    return {
        "key": name,
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "path": "/",
        "max_age": _COOKIE_MAX_AGE,
    }


def _display_name_for(slug: str) -> str:
    try:
        import yaml
        from pathlib import Path
        config_path = Path(__file__).parent.parent / "config" / "llm-config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        paths = get_founder_paths(config, slug)
        return paths.get("display_name", slug.title())
    except Exception:
        return slug.title()


def _get_slug_from_cookie(request: Request) -> str:
    """Extract and validate founder slug from the tagent_token cookie."""
    token = request.cookies.get(_COOKIE_NAME, "")
    claims = decode_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="unauthenticated")
    return claims.get("sub", "")


def _require_admin(request: Request) -> None:
    """Validate admin_token cookie. Raises 401/403 on failure."""
    token = request.cookies.get(_ADMIN_COOKIE_NAME, "")
    claims = decode_token(token)
    if not claims or claims.get("sub") != "admin":
        raise HTTPException(status_code=401, detail="admin authentication required")


# ── Founder Auth ──

class LoginRequest(BaseModel):
    slug: str
    password: str


@router.post("/login")
async def login(data: LoginRequest, request: Request, response: Response):
    host = request.headers.get("host", "")
    subdomain_slug = _resolve_subdomain_slug(host)
    if subdomain_slug and subdomain_slug != data.slug:
        logger.warning("Login slug mismatch: subdomain=%s posted=%s", subdomain_slug, data.slug)
        raise HTTPException(status_code=403, detail="subdomain mismatch")

    stored_hash = get_hash(data.slug)
    if not stored_hash:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_password(data.password, stored_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    token = issue_token(data.slug)
    response.set_cookie(value=token, **_cookie_kwargs())

    logger.info("Login success: %s", data.slug)
    return {
        "ok": True,
        "slug": data.slug,
        "display_name": _display_name_for(data.slug),
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    slug = _get_slug_from_cookie(request)

    host = request.headers.get("host", "")
    subdomain_slug = _resolve_subdomain_slug(host)
    if subdomain_slug and subdomain_slug != slug:
        raise HTTPException(status_code=403, detail="subdomain mismatch")

    return {
        "slug": slug,
        "display_name": _display_name_for(slug),
    }


# ── Permissions ──

@router.get("/permissions")
async def permissions(request: Request):
    """Return allowed pages for the current session's founder."""
    slug = _get_slug_from_cookie(request)
    pages = get_pages(slug)
    return {"pages": pages, "all_pages": ALL_PAGES}


# ── Change Password ──

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(data: ChangePasswordRequest, request: Request, response: Response):
    """Founder changes their own password."""
    slug = _get_slug_from_cookie(request)

    stored_hash = get_hash(slug)
    if not stored_hash or not verify_password(data.current_password, stored_hash):
        raise HTTPException(status_code=401, detail="current password is wrong")

    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="password must be at least 6 characters")

    set_password(slug, data.new_password)

    # Re-issue token (in case we change claims structure in the future)
    token = issue_token(slug)
    response.set_cookie(value=token, **_cookie_kwargs())

    logger.info("Password changed: %s", slug)
    return {"ok": True, "slug": slug}


# ── Admin Auth ──

class AdminLoginRequest(BaseModel):
    password: str


@admin_router.post("/login")
async def admin_login(data: AdminLoginRequest, response: Response):
    """Admin login with separate admin password."""
    if not verify_admin_password(data.password):
        raise HTTPException(status_code=401, detail="invalid admin password")

    token = issue_token("admin")
    response.set_cookie(value=token, **_cookie_kwargs(_ADMIN_COOKIE_NAME))

    logger.info("Admin login success")
    return {"ok": True}


@admin_router.post("/logout")
async def admin_logout(response: Response):
    response.delete_cookie(key=_ADMIN_COOKIE_NAME, path="/")
    return {"ok": True}


@admin_router.get("/me")
async def admin_me(request: Request):
    _require_admin(request)
    return {"ok": True, "role": "admin"}


# ── Admin: Permissions Management ──

@admin_router.get("/permissions")
async def admin_get_permissions(request: Request):
    """Return all founders' page permissions."""
    _require_admin(request)
    return {
        "permissions": get_all_permissions(),
        "all_pages": ALL_PAGES,
    }


class UpdatePermissionsRequest(BaseModel):
    slug: str
    pages: list[str]


@admin_router.post("/permissions")
async def admin_set_permissions(data: UpdatePermissionsRequest, request: Request):
    """Set page permissions for a specific founder."""
    _require_admin(request)
    set_pages(data.slug, data.pages)
    logger.info("Admin updated permissions for %s: %s", data.slug, data.pages)
    return {"ok": True, "slug": data.slug, "pages": get_pages(data.slug)}


# ── Admin: Founder Profile + Password Management ──

def _subdomain_for(slug: str) -> str:
    """Map an internal slug to its Let's Encrypt-safe subdomain (underscores → hyphens)."""
    return slug.replace("_", "-")


def _scan_founder_dirs() -> set[str]:
    """Scan data/founders/*/founder-data/ on disk and return slugs found.

    This is a 4th source of truth: any folder that exists on disk appears in
    the admin panel even if provision.sh hasn't updated llm-config.yaml yet.
    """
    from pathlib import Path
    founders_dir = Path(__file__).parent.parent / "data" / "founders"
    slugs: set[str] = set()
    if not founders_dir.is_dir():
        return slugs
    for folder in founders_dir.iterdir():
        if not folder.is_dir():
            continue
        if not (folder / "founder-data").is_dir():
            continue
        slug = folder.name.lower().replace(" ", "_").replace("-", "_")
        slugs.add(slug)
    return slugs


@admin_router.get("/founders")
async def admin_list_founders(request: Request):
    """Return full profile data for every founder the server knows about.

    Sources:
      - config/llm-config.yaml (registry: display_name, paths)
      - config/founder-auth.yaml (has_password, last_reset_at)
      - config/founder-permissions.yaml (allowed pages)
      - data/founders/*/founder-data/ on disk (catches newly pushed folders
        before provision.sh has run on the VPS)
    """
    _require_admin(request)
    import yaml
    from pathlib import Path

    # Load llm-config for display names + registered founders
    config_path = Path(__file__).parent.parent / "config" / "llm-config.yaml"
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        config = {}

    registry = config.get("founders", {}).get("registry", {}) or {}
    perms = get_all_permissions()

    # Union of slugs from all four sources
    from src.auth.store import list_slugs
    auth_slugs = set(list_slugs())
    disk_slugs = _scan_founder_dirs()
    all_slugs = sorted(set(registry.keys()) | auth_slugs | set(perms.keys()) | disk_slugs)

    profiles = []
    for slug in all_slugs:
        reg = registry.get(slug, {})
        profiles.append({
            "slug": slug,
            "display_name": reg.get("display_name", slug.replace("_", " ").title()),
            "subdomain": _subdomain_for(slug),
            "url": f"https://{_subdomain_for(slug)}.tagent.club",
            "has_password": has_password(slug),
            "last_reset_at": get_last_reset(slug),
            "pages": get_pages(slug),
            "graph_path": reg.get("graph_path", ""),
        })

    return {"founders": profiles}


@admin_router.post("/founders/{slug}/reset-password")
async def admin_reset_password(slug: str, request: Request):
    """Generate a new random password for a founder. Returns plaintext ONCE.

    The plaintext is NOT persisted anywhere — only the bcrypt hash is saved.
    Admin must copy the returned password immediately; it cannot be retrieved later.
    """
    _require_admin(request)
    new_pw = reset_password(slug)
    logger.info("Admin reset password for %s", slug)
    return {
        "ok": True,
        "slug": slug,
        "password": new_pw,
        "last_reset_at": get_last_reset(slug),
    }
