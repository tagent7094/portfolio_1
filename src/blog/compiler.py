"""Blog compiler — assembles markdown with YAML frontmatter and saves to disk + SQLite."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .state import BlogState
from . import db

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).parent.parent.parent


def compile_blog(state: BlogState) -> str:
    """Assemble final markdown from outline + drafted sections."""
    parts = []

    title = state.seo_data.get("seo_title") or state.outline.get("title", state.topic)

    # Title
    parts.append(f"# {title}\n")

    # Intro hook
    intro = state.outline.get("intro_hook", "")
    if intro:
        parts.append(f"{intro}\n")

    # Sections
    sections = state.outline.get("sections", [])
    for i, section in enumerate(sections):
        heading = section.get("heading", f"Section {i + 1}")

        # Apply SEO-optimized heading if available
        optimized = state.seo_data.get("optimized_headings", [])
        for opt in optimized:
            if isinstance(opt, dict) and opt.get("changed") and opt.get("original") == heading:
                heading = opt.get("optimized", heading)
                break

        parts.append(f"## {heading}\n")
        if i < len(state.sections):
            parts.append(f"{state.sections[i]}\n")

    # Conclusion
    conclusion = state.outline.get("conclusion_cta", "")
    if conclusion:
        parts.append(f"---\n\n{conclusion}\n")

    content = "\n".join(parts)

    # Build frontmatter
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    voice_score = 0
    validation = state.voice_validation
    if isinstance(validation, dict):
        scores = [
            validation.get("voice_marker_score", 0),
            validation.get("register_score", 0),
            validation.get("consistency_score", 0),
            validation.get("authenticity_score", 0),
        ]
        voice_score = int(sum(scores) / max(len(scores), 1))

    beliefs_used = []
    stories_used = []
    for section in sections:
        beliefs_used.extend(section.get("beliefs_used", []))
        stories_used.extend(section.get("stories_used", []))

    format_type = getattr(state, "format_type", "blog")
    source_type = "transcript" if hasattr(state, "transcript_text") and state.transcript_text else "topic"

    frontmatter = (
        f"---\n"
        f"title: \"{title}\"\n"
        f"founder: {state.founder_slug}\n"
        f"topic: {state.topic}\n"
        f"tone: {state.tone}\n"
        f"format: {format_type}\n"
        f"word_count: {len(content.split())}\n"
        f"seo_title: \"{state.seo_data.get('seo_title', title)}\"\n"
        f"meta_description: \"{state.seo_data.get('meta_description', '')}\"\n"
        f"voice_score: {voice_score}\n"
        f"generated_at: {now}\n"
        f"beliefs_used: {beliefs_used}\n"
        f"stories_used: {stories_used}\n"
        f"---\n\n"
    )

    state.final_markdown = frontmatter + content
    return state.final_markdown


def save_blog(state: BlogState) -> str:
    """Save blog to disk and register in SQLite. Returns blog_id."""
    db.init_db()

    blog_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Determine output path
    founder_dir = PROJECT_ROOT / "data" / "founders" / state.founder_slug / "blog-data"
    founder_dir.mkdir(parents=True, exist_ok=True)

    # Find next counter for today
    existing = list(founder_dir.glob(f"{state.founder_slug}_blog_{date_str}_*.md"))
    counter = len(existing) + 1
    filename = f"{state.founder_slug}_blog_{date_str}_{counter}.md"
    filepath = founder_dir / filename

    if not state.final_markdown:
        compile_blog(state)

    filepath.write_text(state.final_markdown, encoding="utf-8")
    logger.info("[blog] Saved blog to %s", filepath)

    # Extract metadata
    title = state.seo_data.get("seo_title") or state.outline.get("title", state.topic)
    word_count = len(state.final_markdown.split())
    format_type = getattr(state, "format_type", "blog")
    source_type = "transcript" if hasattr(state, "transcript_text") and state.transcript_text else "topic"

    voice_score = 0
    validation = state.voice_validation
    if isinstance(validation, dict):
        scores = [
            validation.get("voice_marker_score", 0),
            validation.get("register_score", 0),
            validation.get("consistency_score", 0),
            validation.get("authenticity_score", 0),
        ]
        voice_score = int(sum(scores) / max(len(scores), 1))

    db.insert_blog(
        blog_id=blog_id,
        founder_slug=state.founder_slug,
        title=title,
        topic=state.topic,
        tone=state.tone,
        format_type=format_type,
        source_type=source_type,
        word_count=word_count,
        seo_title=state.seo_data.get("seo_title", ""),
        meta_description=state.seo_data.get("meta_description", ""),
        file_path=str(filepath),
        voice_score=voice_score,
        created_at=now_iso,
    )

    state.blog_id = blog_id
    return blog_id
