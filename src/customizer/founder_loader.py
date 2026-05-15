"""Founder data loader — thin wrapper around the universal ingestion reader.

Historically this read only `voice-dna-*.md`, `story-bank-*.md`, and `*posts*.txt`
from `data/founders/<slug>/founder-data/`. Now backed by `src/ingestion/founder_reader`
which understands docx/xlsx/csv/yaml/json and both the legacy and new layouts.

The legacy three-key contract is preserved so existing callers in
`src/batch/corpus_reader.py` (including `_verify_founder_identity`) keep working
unchanged. New keys are additive.
"""

from __future__ import annotations

from ..ingestion.founder_reader import read_founder


def load_raw_founder_data(founder_slug: str) -> dict:
    """Return the founder bundle dict.

    Guaranteed keys (legacy contract):
        raw_voice_dna: str
        raw_story_bank: str
        founder_posts_sample: str

    Additive keys (new — consumers that don't know about them ignore them):
        slug, layout, founder_posts_structured, identity{bio, personality_card,
        tensions, voice_dna}, config{founder_config, linkedin_account,
        instructions}, transcripts, co_founder_posts, viral_used_urls,
        extra_xlsx_data, files_ingested, files_skipped
    """
    return read_founder(founder_slug)
