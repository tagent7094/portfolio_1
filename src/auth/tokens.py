"""JWT token issue/decode for subdomain auth."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

logger = logging.getLogger(__name__)

_DEFAULT_EXPIRY_DAYS = 30
_ALGORITHM = "HS256"

_ephemeral_secret: str | None = None


def _get_secret() -> str:
    """Read JWT secret from env or fall back to an ephemeral one (dev only)."""
    global _ephemeral_secret

    # Prefer file-based secret (for systemd / production)
    secret_file = os.environ.get("TAGENT_JWT_SECRET_FILE", "")
    if secret_file:
        try:
            with open(secret_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError as e:
            logger.warning("Failed to read TAGENT_JWT_SECRET_FILE=%s: %s", secret_file, e)

    secret = os.environ.get("TAGENT_JWT_SECRET", "")
    if secret:
        return secret

    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_urlsafe(32)
        logger.warning(
            "TAGENT_JWT_SECRET not set — using ephemeral secret. "
            "Tokens will be invalidated on restart. Set TAGENT_JWT_SECRET in production."
        )
    return _ephemeral_secret


def issue_token(slug: str, expiry_days: int = _DEFAULT_EXPIRY_DAYS) -> str:
    """Issue a JWT for a founder slug."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": slug,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=expiry_days)).timestamp()),
    }
    return jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """Decode and verify a JWT. Returns claims dict or None if invalid/expired."""
    if not token:
        return None
    try:
        return jwt.decode(token, _get_secret(), algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.debug("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug("Invalid token: %s", e)
        return None
