"""Parse published-posts sources into structured PostRecord lists.

Recognises three formats:
  1. alok-style `Published_*.xlsx` with engagement columns (Likes / Comments / Reposts)
  2. New `linkedin-posts.md` with `## Post N (likes=X, comments=Y, reposts=Z)` blocks
  3. Legacy plain `*linkedin-posts.txt` (no metrics — bare post text)

Output: list of PostRecord dicts with consistent shape, plus `flatten_to_text` for
back-compat (the legacy `founder_posts_sample` consumer expects flat text).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TypedDict

from .xlsx_reader import read_xlsx

logger = logging.getLogger(__name__)


class PostRecord(TypedDict, total=False):
    text: str
    likes: int
    comments: int
    reposts: int
    posted_at: str
    url: str
    source: str


_POST_HEADER_RE = re.compile(
    r"^##\s*Post\s+(\d+)?\s*(?:\(([^)]*)\))?\s*$",
    re.IGNORECASE,
)
_KV_RE = re.compile(r"([a-z_]+)\s*=\s*(\d+)", re.IGNORECASE)


def _coerce_int(v) -> int:
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = re.sub(r"[,\s]", "", str(v))
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _parse_markdown_posts(text: str) -> list[PostRecord]:
    """Parse `## Post N (likes=X, comments=Y, reposts=Z)\\n\\n<text>` blocks."""
    if not text:
        return []
    lines = text.splitlines()
    records: list[PostRecord] = []
    current: PostRecord | None = None
    buf: list[str] = []

    def _flush():
        nonlocal current, buf
        if current is not None:
            body = "\n".join(buf).strip()
            if body:
                current["text"] = body
                records.append(current)
        current = None
        buf = []

    for line in lines:
        m = _POST_HEADER_RE.match(line.strip())
        if m:
            _flush()
            current = {"text": "", "likes": 0, "comments": 0, "reposts": 0, "source": "markdown"}
            meta = m.group(2) or ""
            for k, v in _KV_RE.findall(meta):
                key = k.lower()
                if key in ("likes", "comments", "reposts"):
                    current[key] = _coerce_int(v)  # type: ignore[literal-required]
        else:
            if current is not None:
                buf.append(line)
    _flush()
    return records


def _parse_xlsx_posts(path: Path) -> list[PostRecord]:
    """Parse a Published_*.xlsx exporter — multiple sheets, flexible column names.

    Skips sheets that look like generated-content run outputs (they have
    full_text + roast_* + selected columns from the alok-kumar pipeline).
    """
    sheets = read_xlsx(path)
    if not sheets:
        return []

    text_aliases = {"post content", "content", "post", "text", "post_text", "post text", "old content"}
    likes_aliases = {"likes", "like", "reactions", "like_count", "number of likes", "no of likes"}
    comments_aliases = {"comments", "comment", "comment_count", "number of comments", "no of comments"}
    reposts_aliases = {"reposts", "repost", "shares", "repost_count", "number of reposts", "no of reposts"}
    url_aliases = {"post url", "url", "permalink", "content link", "content_link", "link"}
    date_aliases = {"posted_at", "posted at", "date", "published_at", "published"}

    run_output_markers = {"full_text", "roast_overall", "final_score", "selected", "angle_num"}

    def _find(headers, aliases):
        for h in headers:
            if str(h).strip().lower() in aliases:
                return h
        return None

    records: list[PostRecord] = []
    for sheet in sheets:
        headers = sheet["headers"]
        header_lower = {str(h).strip().lower() for h in headers}
        # Skip pipeline run-output sheets — these are generated content, not published posts.
        if run_output_markers & header_lower:
            logger.debug("[post_parser] %s/%s skipped — run-output schema", path.name, sheet["sheet"])
            continue
        text_col = _find(headers, text_aliases)
        if not text_col:
            continue
        likes_col = _find(headers, likes_aliases)
        comments_col = _find(headers, comments_aliases)
        reposts_col = _find(headers, reposts_aliases)
        url_col = _find(headers, url_aliases)
        date_col = _find(headers, date_aliases)

        for row in sheet["rows"]:
            content = row.get(text_col)
            if not content or not isinstance(content, str):
                continue
            content = content.strip()
            if len(content) < 30:
                continue
            rec: PostRecord = {
                "text": content,
                "likes": _coerce_int(row.get(likes_col)) if likes_col else 0,
                "comments": _coerce_int(row.get(comments_col)) if comments_col else 0,
                "reposts": _coerce_int(row.get(reposts_col)) if reposts_col else 0,
                "url": str(row.get(url_col) or "").strip() if url_col else "",
                "posted_at": str(row.get(date_col) or "").strip() if date_col else "",
                "source": f"xlsx:{sheet['sheet']}",
            }
            records.append(rec)

    return records


def _parse_plain_text_posts(text: str) -> list[PostRecord]:
    """Split a flat .txt file into individual posts.

    Mirrors the heuristic in corpus_reader._split_posts (delimiter scan first,
    paragraph batching as fallback). Returns text-only records (no engagement).
    """
    if not text:
        return []
    separators = ["\n---\n", "\n===\n", "\n\n\n"]
    chunks: list[str] = []
    for sep in separators:
        if sep in text:
            chunks = [p.strip() for p in text.split(sep) if p.strip() and len(p.strip()) > 50]
            break
    if not chunks:
        paragraphs = text.split("\n\n")
        current: list[str] = []
        for p in paragraphs:
            current.append(p)
            if len("\n\n".join(current).split()) > 80:
                chunks.append("\n\n".join(current))
                current = []
        if current:
            chunks.append("\n\n".join(current))
        chunks = [c for c in chunks if len(c.split()) > 20]

    return [{"text": c, "likes": 0, "comments": 0, "reposts": 0, "source": "plain_text"} for c in chunks]


def parse_published_posts(source: str | Path) -> list[PostRecord]:
    """Dispatch to the right parser based on file extension/contents.

    `source` may be a path (Path or str) or a string of in-memory content
    (heuristically detected by '\\n' presence + length).
    """
    if isinstance(source, Path) or (isinstance(source, str) and len(source) < 260 and Path(source).exists()):
        p = Path(source)
        suffix = p.suffix.lower()
        if suffix in (".xlsx", ".xls"):
            return _parse_xlsx_posts(p)
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("[post_parser] failed to read %s: %s", p, e)
            return []
        if suffix == ".md" or "## Post" in content[:1000]:
            md = _parse_markdown_posts(content)
            if md:
                return md
        return _parse_plain_text_posts(content)

    text = str(source)
    if "## Post" in text[:1000]:
        md = _parse_markdown_posts(text)
        if md:
            return md
    return _parse_plain_text_posts(text)


def flatten_to_text(records: list[PostRecord]) -> str:
    """Render structured posts back to the flat string the legacy pipeline expects."""
    return "\n\n---\n\n".join(r.get("text", "") for r in records if r.get("text"))


def top_by_engagement(records: list[PostRecord], k: int = 5) -> list[PostRecord]:
    """Return the top-k posts by likes + comments*3 + reposts*2."""
    def score(r: PostRecord) -> int:
        return r.get("likes", 0) + r.get("comments", 0) * 3 + r.get("reposts", 0) * 2
    return sorted(records, key=score, reverse=True)[:k]
