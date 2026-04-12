"""Auth endpoints: /api/auth/login, /api/auth/logout, /api/auth/me."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from src.auth import context as auth_context
from src.auth.passwords import verify_password
from src.auth.store import get_hash
from src.auth.tokens import decode_token, issue_token
from src.config.founders import get_founder_paths
from webapp.auth_middleware import _resolve_subdomain_slug

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_COOKIE_NAME = "tagent_token"
_COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days


class LoginRequest(BaseModel):
    slug: str
    password: str


def _cookie_kwargs() -> dict:
    """Cookie attributes — Secure only when explicitly enabled."""
    secure = os.environ.get("TAGENT_COOKIE_SECURE", "").lower() in ("1", "true", "yes")
    return {
        "key": _COOKIE_NAME,
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


@router.post("/login")
async def login(data: LoginRequest, request: Request, response: Response):
    """Verify credentials and set the tagent_token cookie."""
    # If hosted on a subdomain, the posted slug must match the subdomain
    host = request.headers.get("host", "")
    subdomain_slug = _resolve_subdomain_slug(host)
    if subdomain_slug and subdomain_slug != data.slug:
        logger.warning("Login slug mismatch: subdomain=%s posted=%s", subdomain_slug, data.slug)
        raise HTTPException(status_code=403, detail="subdomain mismatch")

    stored_hash = get_hash(data.slug)
    if not stored_hash:
        logger.warning("Login attempt for unknown slug: %s", data.slug)
        raise HTTPException(status_code=401, detail="invalid credentials")

    if not verify_password(data.password, stored_hash):
        logger.warning("Login failed for slug: %s", data.slug)
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
    """Clear the tagent_token cookie."""
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    """Return the current authenticated founder, or 401."""
    token = request.cookies.get(_COOKIE_NAME, "")
    claims = decode_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="unauthenticated")
    slug = claims.get("sub", "")

    # If hosted on a subdomain, the cookie must match it
    host = request.headers.get("host", "")
    subdomain_slug = _resolve_subdomain_slug(host)
    if subdomain_slug and subdomain_slug != slug:
        raise HTTPException(status_code=403, detail="subdomain mismatch")

    return {
        "slug": slug,
        "display_name": _display_name_for(slug),
    }
