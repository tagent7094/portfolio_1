"""Tests for the ingestion pipeline."""

import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def test_read_markdown():
    from src.ingestion.file_reader import read_markdown

    chunks = read_markdown(FIXTURES / "sample_voice_dna.md")
    assert len(chunks) >= 1
    assert "founder" in chunks[0].text.lower()


def test_read_csv():
    from src.ingestion.file_reader import read_csv

    chunks = read_csv(FIXTURES / "sample_posts.csv")
    assert len(chunks) == 5
    assert chunks[0].platform == "linkedin"


def test_chunker_markdown():
    from src.ingestion.chunker import chunk_markdown

    text = (FIXTURES / "sample_voice_dna.md").read_text()
    chunks = chunk_markdown(text, "test.md")
    assert len(chunks) >= 3  # At least 3 sections


def test_chunker_plaintext():
    from src.ingestion.chunker import chunk_plaintext

    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = chunk_plaintext(text, "test.txt")
    assert len(chunks) == 3


def test_style_extractor():
    from src.ingestion.style_extractor import extract_style_stats

    text = "I believe hiring for attitude is key. We raised $5M. Our team grew 300% in two years."
    stats = extract_style_stats(text)
    assert "word_count" in stats
    assert stats["word_count"] > 0
    assert "dollar_count" in stats


def test_detect_platform():
    from src.ingestion.file_reader import detect_platform

    assert detect_platform("linkedin-posts.csv") == "linkedin"
    assert detect_platform("twitter_data.json") == "twitter"
    assert detect_platform("notes.txt") == "general"
