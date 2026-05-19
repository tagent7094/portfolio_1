"""Extract 7-category structured findings from RevSure call transcripts.

Iterates all .md and .docx files in
data/founders/deepinder/RevSure Call Transcripts/, chunks each by speaker
turn (~25K tokens per chunk with 4-turn overlap), runs the v1.0 extraction
prompt via Kimi K2.6 with thinking ON, merges findings across chunks per
client, verifies quotes against the source verbatim, and writes one JSON
file per client to data/founders/deepinder/revsure-extracts/.

Run from project root:
    python scripts/extract_revsure_qa.py
    python scripts/extract_revsure_qa.py --only "Glean,Lyra Health"
    python scripts/extract_revsure_qa.py --max-files 3   # dev smoke

Costs ~$2-5 total across all 51 files at K2.6 prices.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("extract_revsure")

TRANSCRIPTS_DIR = PROJECT_ROOT / "data" / "founders" / "deepinder" / "RevSure Call Transcripts"
EXTRACTS_DIR = PROJECT_ROOT / "data" / "founders" / "deepinder" / "revsure-extracts"

# Per-chunk target. Kimi K2.6 has 128K context; we leave ample room for
# thinking + system prompt + output (~8K). 25K input tokens ≈ 100K chars.
TARGET_CHUNK_CHARS = 100_000
OVERLAP_SPEAKER_TURNS = 4


CATEGORY_KEYS = (
    "pains",
    "tools_switched_from",
    "political_tussles",
    "contrarians",
    "revsure_problems",
    "best_about_revsure",
)


def _read_md(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError:
        logger.error("python-docx not installed; cannot read %s", path.name)
        return ""
    try:
        doc = Document(str(path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        logger.warning("failed to read .docx %s: %s", path.name, e)
        return ""


def read_transcript(path: Path) -> str:
    if path.suffix.lower() == ".md":
        return _read_md(path)
    if path.suffix.lower() == ".docx":
        return _read_docx(path)
    return ""


# Filename patterns:
#   "Glean Initial Calls.md"
#   "RevSure_  Transcript - Glean (All Calls).md"
#   "RevSure_ Glean Transcript - Part 1 (All Calls) (1).md"
_CLIENT_PATTERNS = [
    re.compile(r"^RevSure_\s*Transcript\s*-\s*(.+?)\s*\(", re.IGNORECASE),
    re.compile(r"^RevSure_\s*(.+?)\s*Transcript", re.IGNORECASE),
    re.compile(r"^(.+?)\s+Initial Calls", re.IGNORECASE),
]


def parse_client_name(filename: str) -> tuple[str, str]:
    """Return (client_name, call_type) from a transcript filename."""
    stem = Path(filename).stem
    call_type = "initial_calls" if "initial" in stem.lower() else "all_calls"
    for pat in _CLIENT_PATTERNS:
        m = pat.search(stem)
        if m:
            client = m.group(1).strip().strip("-").strip()
            # Trim trailing "Part 1", "(1)", etc.
            client = re.sub(r"\s*Part\s*\d+.*$", "", client).strip()
            client = re.sub(r"\s*\(\d+\)\s*$", "", client).strip()
            if client:
                return client, call_type
    return stem, call_type


_SPEAKER_LINE = re.compile(r"^[A-Z][a-zA-Z .\-']+\s*\|\s*\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\s*-->", re.MULTILINE)


def chunk_by_speakers(text: str, target_chars: int = TARGET_CHUNK_CHARS,
                      overlap_turns: int = OVERLAP_SPEAKER_TURNS) -> list[str]:
    """Split a transcript into chunks at speaker-turn boundaries.

    Each chunk targets `target_chars` chars; chunks overlap by
    `overlap_turns` speaker turns at each boundary so cross-turn arguments
    aren't bisected.
    """
    if len(text) <= target_chars:
        return [text]

    # Find every speaker-turn start. Each "turn" is from one speaker line
    # to the next speaker line.
    starts = [m.start() for m in _SPEAKER_LINE.finditer(text)]
    if len(starts) < 2:
        # No recognizable turns — fall back to fixed-size chunks.
        return [text[i:i + target_chars] for i in range(0, len(text), target_chars)]

    # Build (start, end) for each turn.
    turns: list[tuple[int, int]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        turns.append((start, end))

    chunks: list[str] = []
    cur_start_idx = 0
    while cur_start_idx < len(turns):
        # Accumulate turns until we hit target_chars.
        acc_start = turns[cur_start_idx][0]
        end_idx = cur_start_idx
        while end_idx < len(turns) and turns[end_idx][1] - acc_start < target_chars:
            end_idx += 1
        if end_idx == cur_start_idx:
            end_idx = cur_start_idx + 1  # ensure progress on a giant turn
        chunk_end = turns[min(end_idx, len(turns) - 1)][1] if end_idx < len(turns) else len(text)
        chunks.append(text[acc_start:chunk_end])
        # Advance, overlapping by `overlap_turns`.
        cur_start_idx = max(end_idx - overlap_turns, cur_start_idx + 1)
    return chunks


def _empty_extract(client_name: str, call_type: str) -> dict:
    return {
        "schema_version": "v1.0.0",
        "client_name": client_name,
        "call_type": call_type,
        "findings": {
            "pains": [], "tools_switched_from": [], "political_tussles": [],
            "contrarians": [], "revsure_problems": [], "best_about_revsure": [],
            "wins": {"immediate": [], "long_term": []},
        },
        "before_state": {"stack": [], "pain_summary": "", "kpis_unhealthy": []},
        "after_state": {"with_revsure": "", "wins_realized": [], "open_issues": []},
    }


def verify_quotes_against_source(extract: dict, full_transcript: str) -> dict:
    """Drop any finding whose `quote` doesn't appear verbatim in the transcript.

    Tolerates whitespace collapse but not paraphrasing. Returns the cleaned
    extract + a `_verification` block summarizing what was dropped.
    """
    normalized_source = re.sub(r"\s+", " ", full_transcript)
    dropped = {k: 0 for k in CATEGORY_KEYS}
    kept = {k: 0 for k in CATEGORY_KEYS}
    dropped["wins_immediate"] = 0
    dropped["wins_long_term"] = 0
    kept["wins_immediate"] = 0
    kept["wins_long_term"] = 0

    def quote_in_source(q: str) -> bool:
        if not q or not isinstance(q, str):
            return False
        normalized_q = re.sub(r"\s+", " ", q).strip()
        if len(normalized_q) < 8:
            return False
        # Use a window: the quote must appear contiguously (whitespace-collapsed).
        return normalized_q in normalized_source

    findings = extract.get("findings") or {}
    for k in CATEGORY_KEYS:
        items = findings.get(k) or []
        keepers = []
        for item in items:
            if isinstance(item, dict) and quote_in_source(item.get("quote", "")):
                keepers.append(item)
                kept[k] += 1
            else:
                dropped[k] += 1
        findings[k] = keepers

    wins = findings.get("wins") or {}
    for horizon_key, drop_key, keep_key in [
        ("immediate", "wins_immediate", "wins_immediate"),
        ("long_term", "wins_long_term", "wins_long_term"),
    ]:
        items = wins.get(horizon_key) or []
        keepers = []
        for item in items:
            if isinstance(item, dict) and quote_in_source(item.get("quote", "")):
                keepers.append(item)
                kept[keep_key] += 1
            else:
                dropped[drop_key] += 1
        wins[horizon_key] = keepers
    findings["wins"] = wins

    extract["findings"] = findings
    extract["_verification"] = {"dropped_by_category": dropped, "kept_by_category": kept}
    return extract


def merge_findings_across_chunks(per_chunk_extracts: list[dict], client_name: str, call_type: str) -> dict:
    """Combine N chunk-level extracts into one file-level extract.

    Dedup by quote prefix (first 80 chars normalized) so the same finding
    repeated across overlapping chunks doesn't appear twice.
    """
    merged = _empty_extract(client_name, call_type)

    def dedup_key(item: dict) -> str:
        return re.sub(r"\s+", " ", str(item.get("quote", ""))).strip()[:80].lower()

    for chunk_extract in per_chunk_extracts:
        if not isinstance(chunk_extract, dict):
            continue
        f = chunk_extract.get("findings") or {}
        for k in CATEGORY_KEYS:
            for item in (f.get(k) or []):
                if not isinstance(item, dict):
                    continue
                existing_keys = {dedup_key(x) for x in merged["findings"][k]}
                if dedup_key(item) not in existing_keys:
                    merged["findings"][k].append(item)
        wins = f.get("wins") or {}
        for horizon in ("immediate", "long_term"):
            for item in (wins.get(horizon) or []):
                if not isinstance(item, dict):
                    continue
                existing_keys = {dedup_key(x) for x in merged["findings"]["wins"][horizon]}
                if dedup_key(item) not in existing_keys:
                    merged["findings"]["wins"][horizon].append(item)

        # State snapshots: union the lists, prefer non-empty summaries.
        bs = chunk_extract.get("before_state") or {}
        if bs:
            for tool in (bs.get("stack") or []):
                if tool and tool not in merged["before_state"]["stack"]:
                    merged["before_state"]["stack"].append(tool)
            for kpi in (bs.get("kpis_unhealthy") or []):
                if kpi and kpi not in merged["before_state"]["kpis_unhealthy"]:
                    merged["before_state"]["kpis_unhealthy"].append(kpi)
            if bs.get("pain_summary") and not merged["before_state"]["pain_summary"]:
                merged["before_state"]["pain_summary"] = bs["pain_summary"]

        a = chunk_extract.get("after_state") or {}
        if a:
            for win in (a.get("wins_realized") or []):
                if win and win not in merged["after_state"]["wins_realized"]:
                    merged["after_state"]["wins_realized"].append(win)
            for issue in (a.get("open_issues") or []):
                if issue and issue not in merged["after_state"]["open_issues"]:
                    merged["after_state"]["open_issues"].append(issue)
            if a.get("with_revsure") and not merged["after_state"]["with_revsure"]:
                merged["after_state"]["with_revsure"] = a["with_revsure"]
    return merged


def slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return s or "client"


def get_llm():
    """Build a Kimi K2.6 provider with the revsure_qa_extract config."""
    from src.llm.task_router import LLMRouter
    router = LLMRouter(founder_slug=None)
    return router.for_task("revsure_qa_extract"), router


def extract_one_file(transcript_path: Path, llm, prompt_template: str) -> dict:
    from src.utils.text_utils import fill_prompt
    from src.utils.json_parser import parse_llm_json

    client_name, call_type = parse_client_name(transcript_path.name)
    logger.info("[%s] reading %s", client_name, transcript_path.name)
    text = read_transcript(transcript_path)
    if not text or len(text) < 200:
        logger.warning("[%s] transcript too short (%d chars), skipping", client_name, len(text))
        return _empty_extract(client_name, call_type)

    chunks = chunk_by_speakers(text)
    logger.info("[%s] split into %d chunk(s) (%.1f K chars total)",
                client_name, len(chunks), len(text) / 1000)

    per_chunk: list[dict] = []
    for i, chunk in enumerate(chunks):
        logger.info("[%s] extracting chunk %d/%d (%.1f K chars)", client_name, i + 1, len(chunks), len(chunk) / 1000)
        prompt = fill_prompt(prompt_template, chunk=chunk, client_name=client_name, call_type=call_type)
        try:
            response = llm.generate(prompt, temperature=0.2, max_tokens=8000)
        except Exception as e:
            logger.warning("[%s] chunk %d LLM error: %s — skipping", client_name, i + 1, e)
            continue
        parsed = parse_llm_json(response)
        if isinstance(parsed, dict):
            per_chunk.append(parsed)
        else:
            logger.warning("[%s] chunk %d returned non-dict: %r", client_name, i + 1, type(parsed).__name__)

    merged = merge_findings_across_chunks(per_chunk, client_name, call_type)
    merged = verify_quotes_against_source(merged, text)
    merged["_meta"] = {
        "source_filename": transcript_path.name,
        "char_count": len(text),
        "chunk_count": len(chunks),
        "extracted_chunk_count": len(per_chunk),
    }
    return merged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=str, default="",
                        help="Comma-separated client name substrings to include (default: all)")
    parser.add_argument("--max-files", type=int, default=0, help="Cap on number of files (smoke test)")
    parser.add_argument("--dry-run", action="store_true", help="List files that would be processed, don't call LLM")
    args = parser.parse_args()

    if not TRANSCRIPTS_DIR.exists():
        logger.error("Transcripts directory not found: %s", TRANSCRIPTS_DIR)
        sys.exit(1)

    EXTRACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Gather transcripts: .md + .docx under both subfolders, dedup by stem.
    transcript_files = []
    for ext in (".md", ".docx"):
        transcript_files.extend(TRANSCRIPTS_DIR.rglob(f"*{ext}"))

    # Filter
    only_terms = [t.strip().lower() for t in args.only.split(",") if t.strip()]
    if only_terms:
        transcript_files = [
            p for p in transcript_files
            if any(term in p.stem.lower() for term in only_terms)
        ]
    transcript_files.sort()
    if args.max_files:
        transcript_files = transcript_files[:args.max_files]

    logger.info("found %d transcript files", len(transcript_files))
    for p in transcript_files:
        logger.info("  %s", p.relative_to(PROJECT_ROOT))

    if args.dry_run:
        return

    # Load prompt template
    from src.utils.text_utils import load_prompt
    prompt_template = load_prompt(PROJECT_ROOT / "src" / "batch" / "prompts" / "revsure_qa_extract.txt")

    llm, _router = get_llm()

    # Group by client so one client = one output JSON even if it has both
    # "Initial Calls" and "All Calls" files.
    per_client: dict[str, list[dict]] = {}
    for path in transcript_files:
        extract = extract_one_file(path, llm, prompt_template)
        client_name = extract.get("client_name", "unknown")
        per_client.setdefault(client_name, []).append(extract)

    # Write per-client merged output.
    for client_name, parts in per_client.items():
        merged = merge_findings_across_chunks(parts, client_name, parts[0].get("call_type", "mixed"))
        merged["_meta"] = {
            "source_files": [p.get("_meta", {}).get("source_filename", "") for p in parts],
            "total_chunks": sum(p.get("_meta", {}).get("chunk_count", 0) for p in parts),
            "extracted_chunks": sum(p.get("_meta", {}).get("extracted_chunk_count", 0) for p in parts),
        }
        # Verify across union of source texts
        full_source = "\n\n".join(read_transcript(TRANSCRIPTS_DIR / "All Calls" / m) if (TRANSCRIPTS_DIR / "All Calls" / m).exists()
                                  else read_transcript(TRANSCRIPTS_DIR / "Initial Calls" / m) if (TRANSCRIPTS_DIR / "Initial Calls" / m).exists()
                                  else "" for m in merged["_meta"]["source_files"])
        if full_source:
            merged = verify_quotes_against_source(merged, full_source)
        out_path = EXTRACTS_DIR / f"{slug(client_name)}.json"
        out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        kept = sum(merged.get("_verification", {}).get("kept_by_category", {}).values())
        dropped = sum(merged.get("_verification", {}).get("dropped_by_category", {}).values())
        logger.info("[%s] wrote %s (%d findings kept, %d dropped at verification)",
                    client_name, out_path.name, kept, dropped)


if __name__ == "__main__":
    main()
