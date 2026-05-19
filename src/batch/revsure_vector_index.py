"""Build the askrevsure ChromaDB vector index from per-client extracts.

Each indexed document = one extracted finding's verbatim quote PLUS its
surrounding 200-char window from the source transcript (for retrieval
context). Metadata: client_name, category, speaker, timestamp,
transcript_path, finding_summary.

Run once after extract_revsure_qa.py:
    python src/batch/revsure_vector_index.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.vectors.store import VectorStore  # noqa: E402
from src.vectors.embedder import Embedder  # noqa: E402

EXTRACTS_DIR = PROJECT_ROOT / "data" / "founders" / "deepinder" / "revsure-extracts"
TRANSCRIPTS_DIR = PROJECT_ROOT / "data" / "founders" / "deepinder" / "RevSure Call Transcripts"
CHROMA_DIR = PROJECT_ROOT / "data" / "founders" / "deepinder" / "knowledge-graph" / "revsure_chroma"

logger = logging.getLogger("revsure_vector_index")


def _doc_id(quote: str, speaker: str, ts: str, category: str) -> str:
    return f"rs_{category}_{hashlib.md5(f'{speaker}|{ts}|{quote[:200]}'.encode('utf-8', errors='replace')).hexdigest()[:14]}"


def _find_context_window(transcript_text: str, quote: str, window_chars: int = 200) -> str:
    """Return the quote with `window_chars` of surrounding context on each side."""
    if not transcript_text or not quote:
        return quote
    idx = transcript_text.find(quote.strip())
    if idx < 0:
        return quote
    start = max(0, idx - window_chars)
    end = min(len(transcript_text), idx + len(quote) + window_chars)
    return transcript_text[start:end]


def _load_transcript(filename: str) -> str:
    """Load by source filename, searching both subfolders."""
    for sub in ("All Calls", "Initial Calls"):
        p = TRANSCRIPTS_DIR / sub / filename
        if p.exists():
            if p.suffix.lower() == ".md":
                return p.read_text(encoding="utf-8", errors="replace")
            elif p.suffix.lower() == ".docx":
                try:
                    from docx import Document
                    doc = Document(str(p))
                    return "\n\n".join(par.text for par in doc.paragraphs if par.text.strip())
                except Exception:
                    return ""
    return ""


CATEGORY_TO_FIELD = [
    ("pains", "summary", "pain"),
    ("tools_switched_from", "tool", "tool_switched_from"),
    ("political_tussles", "tension_label", "political_tussle"),
    ("contrarians", "claim", "contrarian"),
    ("revsure_problems", "problem", "revsure_problem"),
    ("best_about_revsure", "summary", "best_about_revsure"),
]


def collect_documents(extracts_dir: Path = EXTRACTS_DIR) -> list[dict]:
    """Walk every extract JSON; produce one doc per finding."""
    docs: list[dict] = []
    json_files = sorted(extracts_dir.glob("*.json"))
    for jpath in json_files:
        try:
            extract = json.loads(jpath.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("failed to load %s: %s", jpath.name, e)
            continue
        client_name = extract.get("client_name") or jpath.stem
        source_files = (extract.get("_meta") or {}).get("source_files", [])
        primary_source_file = source_files[0] if source_files else ""
        transcript_text = _load_transcript(primary_source_file) if primary_source_file else ""

        findings = extract.get("findings") or {}

        # 6 simple categories
        for fkey, label_field, cat_tag in CATEGORY_TO_FIELD:
            for item in findings.get(fkey, []) or []:
                quote = (item.get("quote") or "").strip()
                if not quote:
                    continue
                speaker = item.get("speaker", "unknown") or "unknown"
                ts = item.get("timestamp", "") or ""
                summary = item.get(label_field, "") or ""
                context = _find_context_window(transcript_text, quote)
                docs.append({
                    "id": _doc_id(quote, speaker, ts, cat_tag),
                    "text": context,
                    "metadata": {
                        "client_name": client_name,
                        "category": cat_tag,
                        "speaker": speaker,
                        "timestamp": ts,
                        "summary": summary,
                        "quote": quote,
                        "source_file": primary_source_file,
                    },
                })

        # wins: split by horizon
        wins = findings.get("wins") or {}
        for horizon in ("immediate", "long_term"):
            for item in wins.get(horizon, []) or []:
                quote = (item.get("quote") or "").strip()
                if not quote:
                    continue
                speaker = item.get("speaker", "unknown") or "unknown"
                ts = item.get("timestamp", "") or ""
                summary = item.get("win", "") or ""
                context = _find_context_window(transcript_text, quote)
                cat_tag = f"win_{horizon}"
                docs.append({
                    "id": _doc_id(quote, speaker, ts, cat_tag),
                    "text": context,
                    "metadata": {
                        "client_name": client_name,
                        "category": cat_tag,
                        "horizon": horizon,
                        "speaker": speaker,
                        "timestamp": ts,
                        "summary": summary,
                        "quote": quote,
                        "source_file": primary_source_file,
                    },
                })

    # Dedup by id
    seen: set[str] = set()
    unique: list[dict] = []
    for d in docs:
        if d["id"] in seen:
            continue
        seen.add(d["id"])
        unique.append(d)
    return unique


def build_index() -> None:
    docs = collect_documents()
    if not docs:
        logger.warning("no documents to index — run extract_revsure_qa.py first")
        return

    logger.info("collected %d unique findings", len(docs))
    by_cat: dict[str, int] = {}
    for d in docs:
        c = d["metadata"]["category"]
        by_cat[c] = by_cat.get(c, 0) + 1
    for k, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d", k, v)

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    embedder = Embedder()
    store = VectorStore(persist_dir=str(CHROMA_DIR), collection_name="revsure_qa")

    # Embed + upsert in batches of 64 (avoid sending huge single calls).
    batch_size = 64
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        texts = [d["text"] for d in batch]
        embeddings = embedder.embed(texts)
        store.add(
            ids=[d["id"] for d in batch],
            texts=texts,
            metadatas=[d["metadata"] for d in batch],
            embeddings=embeddings,
        )
        logger.info("indexed batch %d/%d (%d docs)",
                    (i // batch_size) + 1,
                    (len(docs) + batch_size - 1) // batch_size,
                    len(batch))
    logger.info("done. collection now has %d documents", store.count())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    build_index()
