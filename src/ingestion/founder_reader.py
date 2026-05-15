"""Universal founder data reader.

Auto-detects new vs old folder layout, classifies every file by name + content
sniff, extracts text from .md/.txt/.docx/.xlsx/.csv/.yaml/.json, caches
extractions by (path, mtime, size), and returns a normalized FounderBundle
shaped to drop into the existing BatchState.

Replaces the narrow `load_raw_founder_data` (only read .md/.txt) with a
reader that never silently skips a file.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

import yaml

from .docx_reader import read_docx
from .post_parser import PostRecord, flatten_to_text, parse_published_posts
from .xlsx_reader import read_xlsx

logger = logging.getLogger(__name__)

Layout = Literal["new", "old", "mixed", "empty"]


_FILE_ROLES = {
    "voice_dna": ("identity",),
    "story_bank": ("narrative",),
    "personality_card": ("identity",),
    "bio": ("identity",),
    "tensions": ("identity",),
    "posts_text": ("content",),
    "posts_xlsx": ("content",),
    "transcript": ("content",),
    "co_founder_post": ("content",),
    "viral_used": ("audit",),
    "viral_data": ("audit",),
    "founder_config": ("config",),
    "linkedin_account": ("config",),
    "instructions": ("config",),
    "graph": ("graph",),
    "exclusions": ("config",),
    "run_history": ("history",),
    "unknown": ("unknown",),
}

_SKIP_DIRS = {"post-data", "chroma", "__pycache__", ".git", "run-history"}


def detect_layout(root: Path) -> Layout:
    """Detect founder folder layout.

    new = has identity/ + graph/graph.json
    old = has founder-data/ + knowledge-graph/graph.json
    mixed = both present (during migration)
    empty = neither present
    """
    has_new = (root / "identity").is_dir() and (root / "graph" / "graph.json").exists()
    has_old = (root / "founder-data").is_dir()
    if has_new and has_old:
        return "mixed"
    if has_new:
        return "new"
    if has_old:
        return "old"
    return "empty"


def _classify_file(path: Path, sample_head: str = "") -> str:
    """Map a file to one of the FILE_ROLES based on name + parent + content sniff.

    Order matters — parent-folder hints win first because the new layout puts
    files in semantic folders (identity/, content/, config/). Then filename
    globs. Then content sniff.
    """
    name = path.name.lower()
    stem = path.stem.lower()
    parent = path.parent.name.lower()
    suffix = path.suffix.lower()

    if parent == "identity":
        if "personality" in stem or "personality-card" in stem:
            return "personality_card"
        if "voice" in stem and "dna" in stem:
            return "voice_dna"
        if stem == "bio":
            return "bio"
        if stem == "tensions":
            return "tensions"
    if parent == "content":
        if "linkedin-posts" in stem or "posts" in stem:
            if suffix in (".md", ".txt"):
                return "posts_text"
            if suffix in (".xlsx", ".xls"):
                return "posts_xlsx"
        if parent in ("transcripts",) or "transcript" in stem:
            return "transcript"
    if parent == "transcripts":
        return "transcript"
    if parent == "co-founder-posts":
        return "co_founder_post"
    if parent == "config":
        if "founder-config" in stem:
            return "founder_config"
        if "linkedin-account" in stem:
            return "linkedin_account"
        if "instruction" in stem:
            return "instructions"
    if parent == "viral-source-used":
        return "viral_used"
    if parent == "viral-post-data":
        return "viral_data"
    if parent == "graph" and stem == "graph":
        return "graph"
    if parent == "knowledge-graph":
        if stem == "graph":
            return "graph"
        if "personality-card" in stem:
            return "personality_card"
        return "unknown"

    if "voice" in stem and "dna" in stem:
        return "voice_dna"
    if "story" in stem and ("bank" in stem or "inventory" in stem):
        return "story_bank"
    if "narrative" in stem and suffix in (".md", ".docx"):
        return "story_bank"
    if "personality-card" in stem or "personality_card" in stem:
        return "personality_card"
    if "linkedin-ghostwriting" in stem or "system-instruction" in stem or "system-prompt" in stem:
        return "instructions"
    if "exclusion" in stem:
        return "exclusions"

    if suffix in (".xlsx", ".xls"):
        if "viral" in stem:
            return "viral_data"
        if "published" in stem:
            return "posts_xlsx"
        if "linkedin" in stem and ("post" in stem or "pack" in stem):
            return "posts_xlsx"
        # Dated LinkedIn exports like 2026-04-19-alok-kumar-linkedin.xlsx
        if "linkedin" in stem and any(ch.isdigit() for ch in stem):
            return "posts_xlsx"
        return "unknown"
    if suffix == ".docx":
        if "transcript" in stem or "calls" in stem:
            return "transcript"
        if "content" in stem and suffix == ".docx":
            return "story_bank"
        if "narrative" in stem:
            return "story_bank"
        return "unknown"
    if suffix in (".md", ".txt"):
        if "posts" in stem and "linkedin" in stem:
            return "posts_text"
        if "posts_extracted" in stem or stem.endswith("_posts"):
            return "posts_text"
        if "sources" in stem and "post" in stem:
            return "story_bank"
    if suffix == ".csv":
        if "viral" in stem and "used" in stem:
            return "viral_used"

    return "unknown"


def _extract_text(path: Path, role: str) -> tuple[str, dict[str, Any]]:
    """Pull the text payload + structured extras from a file.

    Returns (plain_text, extras). `extras` carries structured data (tables,
    xlsx rows, parsed yaml/json) for downstream consumers.
    """
    suffix = path.suffix.lower()
    extras: dict[str, Any] = {}

    try:
        if suffix in (".md", ".txt"):
            text = path.read_text(encoding="utf-8", errors="replace")
            return text, extras
        if suffix == ".docx":
            doc = read_docx(path)
            if doc.get("error"):
                extras["error"] = doc["error"]
            extras["tables"] = doc.get("tables", [])
            return doc.get("plain_text", ""), extras
        if suffix in (".xlsx", ".xls"):
            sheets = read_xlsx(path)
            extras["sheets"] = sheets
            text_parts: list[str] = []
            for sheet in sheets:
                for row in sheet["rows"]:
                    for v in row.values():
                        if isinstance(v, str) and len(v) > 50:
                            text_parts.append(v)
            return "\n\n".join(text_parts), extras
        if suffix == ".csv":
            with path.open(encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            extras["rows"] = rows
            return "\n".join(",".join(r) for r in rows), extras
        if suffix in (".yaml", ".yml"):
            text = path.read_text(encoding="utf-8", errors="replace")
            try:
                extras["parsed"] = yaml.safe_load(text)
            except yaml.YAMLError as e:
                extras["error"] = f"yaml parse failed: {e}"
            return text, extras
        if suffix == ".json":
            text = path.read_text(encoding="utf-8", errors="replace")
            try:
                extras["parsed"] = json.loads(text)
            except json.JSONDecodeError as e:
                extras["error"] = f"json parse failed: {e}"
            return text, extras
    except Exception as e:
        extras["error"] = f"{type(e).__name__}: {e}"
        logger.warning("[founder_reader] failed to read %s — %s", path.name, extras["error"])

    return "", extras


def _ingestion_cache_path(slug: str) -> Path:
    project_root = Path(__file__).parent.parent.parent
    return project_root / "data" / "founders" / slug / ".ingestion_cache.json"


def _load_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache_path: Path, data: dict) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("[founder_reader] failed to write cache %s: %s", cache_path, e)


def _file_cache_key(path: Path) -> str:
    try:
        st = path.stat()
        return f"{path}|{int(st.st_mtime)}|{st.st_size}"
    except OSError:
        return f"{path}|missing"


def _founder_root(slug: str) -> Path:
    project_root = Path(__file__).parent.parent.parent
    return project_root / "data" / "founders" / slug


def _walk_founder_files(root: Path) -> list[Path]:
    """Walk a founder folder, returning every file path except those in skip dirs."""
    files: list[Path] = []
    if not root.exists():
        return files
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parts_lower = {part.lower() for part in p.parts}
        if parts_lower & _SKIP_DIRS:
            continue
        if p.name.startswith("."):
            continue
        files.append(p)
    return files


def read_founder(slug: str) -> dict:
    """Read every recognisable file under data/founders/<slug>/ into a bundle.

    Returns the normalized FounderBundle dict. Adds new keys without breaking
    the legacy three-key contract — load_raw_founder_data wraps this and pulls
    out raw_voice_dna / raw_story_bank / founder_posts_sample.
    """
    root = _founder_root(slug)
    layout = detect_layout(root)
    cache_path = _ingestion_cache_path(slug)
    cache = _load_cache(cache_path)
    cache_hits = 0

    bundle = {
        "slug": slug,
        "layout": layout,
        "raw_voice_dna": "",
        "raw_story_bank": "",
        "founder_posts_sample": "",
        "founder_posts_structured": [],
        "identity": {"bio": "", "personality_card": "", "tensions": "", "voice_dna": ""},
        "config": {"founder_config": None, "linkedin_account": None, "instructions": ""},
        "transcripts": "",
        "co_founder_posts": "",
        "viral_used_urls": [],
        "extra_xlsx_data": [],
        "files_ingested": [],
        "files_skipped": [],
    }

    if layout == "empty":
        logger.warning("[founder_reader] %s: folder layout is empty (%s)", slug, root)
        return bundle

    files = _walk_founder_files(root)
    new_cache: dict[str, Any] = {}

    voice_dna_parts: list[str] = []
    story_bank_parts: list[str] = []
    posts_text_parts: list[str] = []
    posts_records_all: list[PostRecord] = []
    transcript_parts: list[str] = []
    co_founder_parts: list[str] = []
    viral_urls: list[str] = []

    for path in sorted(files):
        cache_key = _file_cache_key(path)
        rel = str(path.relative_to(root))
        cached = cache.get(rel)
        if cached and cached.get("key") == cache_key:
            text = cached.get("text", "")
            extras = cached.get("extras", {})
            role = cached.get("role", "unknown")
            cache_hits += 1
        else:
            sample_head = ""
            if path.suffix.lower() in (".md", ".txt"):
                try:
                    sample_head = path.read_text(encoding="utf-8", errors="replace")[:500]
                except Exception:
                    sample_head = ""
            role = _classify_file(path, sample_head)
            text, extras = _extract_text(path, role)

        new_cache[rel] = {"key": cache_key, "role": role, "text": text, "extras": extras}

        if extras.get("error"):
            bundle["files_skipped"].append({"file": rel, "reason": extras["error"], "role": role})
            continue
        if role == "unknown":
            bundle["files_skipped"].append({"file": rel, "reason": "unrecognised file", "role": role})
            continue

        bundle["files_ingested"].append({"file": rel, "role": role})

        if role == "voice_dna":
            voice_dna_parts.append(text)
            if not bundle["identity"]["voice_dna"] or path.parent.name.lower() == "identity":
                bundle["identity"]["voice_dna"] = text
        elif role == "story_bank":
            story_bank_parts.append(text)
        elif role == "personality_card":
            if not bundle["identity"]["personality_card"]:
                bundle["identity"]["personality_card"] = text
        elif role == "bio":
            bundle["identity"]["bio"] = text
        elif role == "tensions":
            bundle["identity"]["tensions"] = text
        elif role == "posts_text":
            posts_text_parts.append(text)
            records = parse_published_posts(path)
            posts_records_all.extend(records)
        elif role == "posts_xlsx":
            records = parse_published_posts(path)
            posts_records_all.extend(records)
            bundle["extra_xlsx_data"].append({"file": rel, "sheets": extras.get("sheets", [])})
        elif role == "transcript":
            transcript_parts.append(text)
        elif role == "co_founder_post":
            co_founder_parts.append(text)
        elif role == "viral_used":
            rows = extras.get("rows", [])
            for row in rows[1:] if rows else []:
                if row and row[0]:
                    viral_urls.append(row[0])
        elif role == "viral_data":
            bundle["extra_xlsx_data"].append({"file": rel, "sheets": extras.get("sheets", [])})
        elif role == "founder_config":
            bundle["config"]["founder_config"] = extras.get("parsed")
        elif role == "linkedin_account":
            bundle["config"]["linkedin_account"] = extras.get("parsed")
        elif role == "instructions":
            bundle["config"]["instructions"] = (bundle["config"]["instructions"] + "\n\n" + text).strip() if bundle["config"]["instructions"] else text
        elif role == "graph":
            pass  # graph is loaded separately by corpus_reader via load_graph(graph_path)
        elif role == "exclusions":
            pass  # exclusions read separately via load_exclusions()

    bundle["raw_voice_dna"] = "\n\n".join(p for p in voice_dna_parts if p)
    bundle["raw_story_bank"] = "\n\n".join(p for p in story_bank_parts if p)
    bundle["transcripts"] = "\n\n".join(p for p in transcript_parts if p)
    bundle["co_founder_posts"] = "\n\n".join(p for p in co_founder_parts if p)
    bundle["viral_used_urls"] = viral_urls

    if posts_records_all:
        bundle["founder_posts_structured"] = posts_records_all
        bundle["founder_posts_sample"] = flatten_to_text(posts_records_all)
    elif posts_text_parts:
        bundle["founder_posts_sample"] = "\n\n---\n\n".join(posts_text_parts)

    _save_cache(cache_path, new_cache)
    logger.info(
        "[founder_reader] %s: layout=%s, %d ingested, %d skipped, %d cache hits",
        slug, layout, len(bundle["files_ingested"]), len(bundle["files_skipped"]), cache_hits,
    )

    return bundle
