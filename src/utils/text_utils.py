"""Text utility functions."""

import re
import unicodedata


def slugify(text: str) -> str:
    """Convert text to a snake_case identifier."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "_", text).strip("_")
    return text[:80]


def truncate(text: str, max_length: int = 200, suffix: str = "...") -> str:
    """Truncate text at a word boundary."""
    if len(text) <= max_length:
        return text
    truncated = text[: max_length - len(suffix)]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + suffix


def split_sentences(text: str) -> list[str]:
    """Split text into sentences using regex."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def load_prompt(prompt_path) -> str:
    """Load a prompt template from a file path."""
    from pathlib import Path

    return Path(prompt_path).read_text(encoding="utf-8")


def fill_prompt(template: str, **kwargs) -> str:
    """Fill placeholders in a prompt template."""
    return template.format(**kwargs)


def save_to_history(text: str, platform: str = "linkedin", folder: str = "data/output") -> str:
    """Save a generated post to the history folder."""
    import time
    from pathlib import Path
    
    if not text or not text.strip():
        return ""
        
    # Get project root — assuming this is in src/utils
    project_root = Path(__file__).parent.parent.parent
    output_dir = project_root / folder
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    filename = f"post_{platform}_{timestamp}.txt"
    file_path = output_dir / filename
    
    # Avoid collisions if two saves happen in same second
    if file_path.exists():
        filename = f"post_{platform}_{timestamp}_{int(time.time()*1000)%1000}.txt"
        file_path = output_dir / filename
        
    file_path.write_text(text, encoding="utf-8")
    return filename
