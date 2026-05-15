"""Saturation guard — flag generated posts that recycle the founder's published phrases.

Catches the failure mode where a generated post copies 6-word (or longer) sequences
verbatim from the founder's existing posts. Lower-bound check; doesn't block.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, return non-empty tokens."""
    if not text:
        return []
    return _TOKEN_RE.findall(text.lower())


def extract_ngrams(text: str, n: int = 6) -> set[str]:
    """Return the set of distinct n-grams in `text` (lowercased, punctuation-stripped)."""
    tokens = _tokenize(text)
    if len(tokens) < n:
        return set()
    return {" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


@dataclass
class SaturationResult:
    shared_ngrams: list[str]
    count: int
    warning: bool
    worst_match_id: str
    worst_match_count: int


def check_saturation(
    generated: str,
    published_corpus: list[str] | list[dict],
    n: int = 6,
    threshold: int = 5,
) -> dict:
    """Compare a generated post against the founder's published posts.

    Returns a dict (also serializable as SaturationResult).

    `published_corpus` may be a list of strings or a list of dicts (PostRecord
    shape — uses `text` field, falls back to dict repr). The worst-match index
    is reported in `worst_match_id` for review.

    `warning=True` if any single published post shares more than `threshold`
    n-grams with the generated text.
    """
    gen_ngrams = extract_ngrams(generated, n=n)
    if not gen_ngrams:
        return {
            "shared_ngrams": [],
            "count": 0,
            "warning": False,
            "worst_match_id": "",
            "worst_match_count": 0,
        }

    worst_count = 0
    worst_id = ""
    worst_shared: list[str] = []

    for i, item in enumerate(published_corpus):
        if isinstance(item, dict):
            text = item.get("text", "")
            ident = item.get("post_id") or item.get("url") or f"post_{i}"
        else:
            text = str(item)
            ident = f"post_{i}"
        if not text:
            continue
        published_ngrams = extract_ngrams(text, n=n)
        shared = gen_ngrams & published_ngrams
        if len(shared) > worst_count:
            worst_count = len(shared)
            worst_id = str(ident)
            worst_shared = sorted(shared)[:10]

    warning = worst_count > threshold
    return {
        "shared_ngrams": worst_shared,
        "count": worst_count,
        "warning": warning,
        "worst_match_id": worst_id,
        "worst_match_count": worst_count,
    }
