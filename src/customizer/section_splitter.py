"""Split posts into opening / body / closing sections."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PostSections:
    opening: str
    body: str
    closing: str
    raw: str


def split_post(content: str) -> PostSections:
    """Split a post into opening, body, and closing sections.

    Strategy:
    - Split by double newlines into paragraphs
    - First paragraph = opening
    - Last paragraph = closing
    - Everything between = body
    - Edge cases: single paragraph splits by sentences
    """
    content = content.strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]

    if len(paragraphs) == 0:
        return PostSections(opening="", body="", closing="", raw=content)

    if len(paragraphs) == 1:
        # Single paragraph — split by sentences
        sentences = re.split(r"(?<=[.!?])\s+", paragraphs[0])
        if len(sentences) <= 2:
            return PostSections(
                opening=sentences[0],
                body="",
                closing=sentences[-1] if len(sentences) > 1 else "",
                raw=content,
            )
        return PostSections(
            opening=sentences[0],
            body=" ".join(sentences[1:-1]),
            closing=sentences[-1],
            raw=content,
        )

    if len(paragraphs) == 2:
        return PostSections(
            opening=paragraphs[0],
            body="",
            closing=paragraphs[1],
            raw=content,
        )

    return PostSections(
        opening=paragraphs[0],
        body="\n\n".join(paragraphs[1:-1]),
        closing=paragraphs[-1],
        raw=content,
    )
