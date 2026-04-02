"""Split text into meaningful chunks."""

from __future__ import annotations

import re
import sys
import uuid
from dataclasses import dataclass, field


@dataclass
class TextChunk:
    chunk_id: str
    text: str
    source_file: str
    position: int
    char_count: int
    metadata: dict = field(default_factory=dict)


MAX_CHUNK_SIZE = 2000  # Default for local models. Overridden by adaptive_chunk_size()


def adaptive_chunk_size(provider: str = "", model: str = "") -> int:
    """Calculate optimal chunk size based on provider's context window.

    Larger context = larger chunks = fewer LLM calls = richer extraction.
    Uses ~25% of context for input (rest for prompt template + output).
    """
    if not provider:
        return MAX_CHUNK_SIZE

    try:
        from ..llm.rate_limiter import get_spec
        spec = get_spec(provider, model)
        # Use 25% of context window for the text chunk (in chars)
        # Reserve rest for prompt template (~1500 tokens) + output
        available_tokens = spec.context_window - 2000  # prompt template overhead
        available_for_input = int(available_tokens * 0.25)
        chunk_chars = int(available_for_input * spec.chars_per_token)
        # Clamp between 2000 (local minimum) and 50000 (practical max)
        result = max(2000, min(50000, chunk_chars))
        return result
    except Exception:
        return MAX_CHUNK_SIZE


def _split_at_sentence_boundary(text: str, max_len: int) -> list[str]:
    """Split text at sentence boundaries to stay under max_len."""
    if len(text) <= max_len:
        return [text]
    pieces = []
    current = ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        if len(current) + len(sentence) + 1 > max_len and current:
            pieces.append(current.strip())
            current = sentence
        else:
            current = current + " " + sentence if current else sentence
    if current.strip():
        pieces.append(current.strip())
    return pieces


def chunk_markdown(text: str, source_file: str) -> list[TextChunk]:
    """Split markdown by ## headers."""
    sections = re.split(r"\n(?=##\s)", text)
    chunks = []
    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue
        for sub in _split_at_sentence_boundary(section, MAX_CHUNK_SIZE):
            chunks.append(
                TextChunk(
                    chunk_id=str(uuid.uuid4())[:8],
                    text=sub,
                    source_file=source_file,
                    position=i,
                    char_count=len(sub),
                )
            )
    return chunks


def chunk_plaintext(text: str, source_file: str) -> list[TextChunk]:
    """Split plain text into chunks, merging small paragraphs together up to MAX_CHUNK_SIZE."""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    current = ""
    chunk_idx = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # If adding this paragraph would exceed max size, flush current
        if current and len(current) + len(para) + 2 > MAX_CHUNK_SIZE:
            chunks.append(
                TextChunk(
                    chunk_id=str(uuid.uuid4())[:8],
                    text=current.strip(),
                    source_file=source_file,
                    position=chunk_idx,
                    char_count=len(current.strip()),
                )
            )
            chunk_idx += 1
            current = ""
        current += para + "\n\n"

    # Flush remaining
    if current.strip():
        chunks.append(
            TextChunk(
                chunk_id=str(uuid.uuid4())[:8],
                text=current.strip(),
                source_file=source_file,
                position=chunk_idx,
                char_count=len(current.strip()),
            )
        )

    return chunks


def chunk_csv_row(text: str, source_file: str, position: int) -> TextChunk:
    """Each CSV row is one chunk."""
    return TextChunk(
        chunk_id=str(uuid.uuid4())[:8],
        text=text.strip(),
        source_file=source_file,
        position=position,
        char_count=len(text.strip()),
    )


def chunk_content(text: str, source_file: str, max_size: int | None = None) -> list[TextChunk]:
    """Auto-detect content type and chunk accordingly.

    Args:
        text: Raw text content
        source_file: Source file path
        max_size: Override MAX_CHUNK_SIZE. Use adaptive_chunk_size() for cloud models.
    """
    global MAX_CHUNK_SIZE
    effective_max = max_size or MAX_CHUNK_SIZE
    print(f"\033[35m[Chunker]\033[0m chunk_content(source={source_file!r}, input={len(text)} chars, max_size={effective_max})", file=sys.stderr, flush=True)

    # Temporarily override global for the chunking functions
    original = MAX_CHUNK_SIZE
    MAX_CHUNK_SIZE = effective_max

    if source_file.endswith(".md"):
        result = chunk_markdown(text, source_file)
    else:
        result = chunk_plaintext(text, source_file)

    MAX_CHUNK_SIZE = original
    print(f"\033[35m[Chunker]\033[0m \033[32m→ {len(result)} chunks created\033[0m", file=sys.stderr, flush=True)
    return result
