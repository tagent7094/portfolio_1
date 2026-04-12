"""Per-request founder context using ContextVar."""

from __future__ import annotations

from contextvars import ContextVar

current_founder_slug: ContextVar[str | None] = ContextVar("current_founder_slug", default=None)


def get() -> str | None:
    """Return the current request's authenticated founder slug, or None."""
    return current_founder_slug.get()


def set(slug: str | None) -> None:
    """Set the current request's authenticated founder slug."""
    current_founder_slug.set(slug)
