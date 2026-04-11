"""Load raw founder files (voice-dna, story-bank, linkedin posts) at generation time."""

from __future__ import annotations

from pathlib import Path


def load_raw_founder_data(founder_slug: str) -> dict:
    """Read voice-dna, story-bank, and linkedin-posts from founder's data dir.

    Returns dict with keys: raw_voice_dna, raw_story_bank, founder_posts_sample.
    Falls back to empty strings if files don't exist.
    """
    import yaml
    from ..config.founders import get_founder_paths

    config_path = Path(__file__).parent.parent.parent / "config" / "llm-config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    paths = get_founder_paths(config, founder_slug)
    data_dir = Path(paths["data_dir"])

    result = {"raw_voice_dna": "", "raw_story_bank": "", "founder_posts_sample": ""}

    if not data_dir.exists():
        return result

    # Voice DNA file (voice-dna-*.md)
    for f in data_dir.glob("*voice-dna*.md"):
        result["raw_voice_dna"] = f.read_text(encoding="utf-8")
        break

    # Story bank file (story-bank-*.md)
    for f in data_dir.glob("*story-bank*.md"):
        result["raw_story_bank"] = f.read_text(encoding="utf-8")
        break

    # LinkedIn posts file (*.txt with "posts" in name, or linkedin-posts)
    for f in data_dir.glob("*linkedin*posts*.txt"):
        result["founder_posts_sample"] = f.read_text(encoding="utf-8")
        break
    if not result["founder_posts_sample"]:
        for f in data_dir.glob("*posts*.txt"):
            result["founder_posts_sample"] = f.read_text(encoding="utf-8")
            break

    return result
