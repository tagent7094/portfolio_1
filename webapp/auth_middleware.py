"""Subdomain-aware auth middleware for tagent.club deployment.

When TAGENT_AUTH_ENABLED=1, this middleware:
  1. Resolves the founder slug from the Host header (e.g. sharath.tagent.club -> "sharath")
  2. On /api/* requests (except /api/auth/*, /api/health), validates the tagent_token
     cookie and ensures its sub claim matches the subdomain.
  3. Sets the per-request ContextVar so existing helpers can read the scoped slug.

When TAGENT_AUTH_ENABLED is unset/0, this middleware is a NO-OP — local dev unaffected.
"""

from __future__ import annotations

import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.auth import context as auth_context
from src.auth.tokens import decode_token

logger = logging.getLogger(__name__)

# Paths that bypass subdomain auth even when scoped
_BYPASS_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
    "/api/health",
}
# Prefix that bypasses subdomain auth (admin has its own cookie-based auth)
_BYPASS_PREFIXES = ("/api/admin/",)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}
_APEX_DOMAIN = "tagent.club"


def _resolve_subdomain_slug(host: str) -> str | None:
    """Extract founder slug from a Host header. Returns None if unscoped/dev."""
    if not host:
        return None
    # Strip port
    bare = host.split(":")[0].lower()
    if bare in _LOCAL_HOSTS:
        return None
    if bare == _APEX_DOMAIN:
        return None
    # sharath.tagent.club -> ["sharath", "tagent", "club"]
    parts = bare.split(".")
    if len(parts) >= 3 and parts[-2] == "tagent" and parts[-1] == "club":
        # Let's Encrypt rejects underscores in hostnames, so subdomains use hyphens
        # (e.g. anish-popli.tagent.club) but backend slugs use underscores (anish_popli).
        # Normalize by converting hyphens → underscores.
        return parts[0].replace("-", "_")
    return None


class AuthMiddleware(BaseHTTPMiddleware):
    """Enforces subdomain-scoped auth when TAGENT_AUTH_ENABLED=1."""

    def __init__(self, app):
        super().__init__(app)
        self.enabled = os.environ.get("TAGENT_AUTH_ENABLED", "").lower() in ("1", "true", "yes")
        if self.enabled:
            logger.info("AuthMiddleware: ENABLED (subdomain auth enforced)")
        else:
            logger.info("AuthMiddleware: disabled (local dev mode, no auth)")

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        host = request.headers.get("host", "")
        slug = _resolve_subdomain_slug(host)

        path = request.url.path

        # Unscoped (apex/localhost) — let through, no ContextVar set
        if slug is None:
            return await call_next(request)

        # Scoped: set ContextVar so handlers see this slug
        token_for_context = auth_context.current_founder_slug.set(slug)
        try:
            # Bypass auth for the auth endpoints and admin routes
            if path in _BYPASS_PATHS or any(path.startswith(p) for p in _BYPASS_PREFIXES):
                return await call_next(request)

            # Only enforce on API routes
            if not path.startswith("/api/"):
                return await call_next(request)

            # Validate cookie
            cookie_token = request.cookies.get("tagent_token", "")
            claims = decode_token(cookie_token)
            if not claims:
                return JSONResponse({"error": "unauthenticated"}, status_code=401)
            if claims.get("sub") != slug:
                return JSONResponse({"error": "subdomain mismatch"}, status_code=403)

            return await call_next(request)
        finally:
            auth_context.current_founder_slug.reset(token_for_context)
