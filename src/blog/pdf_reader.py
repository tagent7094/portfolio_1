"""PDF text extraction for Content Studio document uploads."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_pdf(path: str | Path) -> dict:
    """Extract text from a PDF file. Returns {plain_text, pages, error}."""
    path = Path(path)
    try:
        import pdfplumber
    except ImportError:
        return {"plain_text": "", "pages": [], "error": "pdfplumber not installed"}

    try:
        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
        plain_text = "\n\n".join(pages)
        return {"plain_text": plain_text, "pages": pages, "error": ""}
    except Exception as e:
        logger.warning("[pdf_reader] failed to read %s: %s", path.name, e)
        return {"plain_text": "", "pages": [], "error": str(e)}
