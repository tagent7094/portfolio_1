"""Parse viral LinkedIn posts CSV into structured records."""

from __future__ import annotations

import csv
import hashlib
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _parse_int(val: str) -> int:
    """Parse an integer from potentially messy CSV data."""
    if not val:
        return 0
    val = re.sub(r"[,%\s]", "", str(val))
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _parse_float(val: str) -> float:
    if not val:
        return 0.0
    val = re.sub(r"[%\s]", "", str(val))
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def parse_viral_csv(csv_path: str | Path) -> list[dict]:
    """Parse the viral LinkedIn posts CSV into structured records.

    CSV columns: LinkedIn Profile of Creator, Comments (Nitesh / Vaishali),
    Number of followers, Post URL, Content type, Recent, Applicable for,
    Likes vs followers ratio, Likes, Comments, Reposts, Post content

    Returns list of dicts with: post_id, content, likes, comments, reposts,
    followers, likes_ratio, engagement_score, content_type, creator_url
    """
    path = Path(csv_path)
    if not path.exists():
        logger.error("CSV/XLSX not found: %s", path)
        return []

    # Handle Excel files via pandas
    if path.suffix.lower() in ('.xlsx', '.xls'):
        return _parse_xlsx(path)

    records = []
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return []

        for row_num, row in enumerate(reader, start=2):
            if len(row) < 12:
                continue

            content = row[11].strip() if len(row) > 11 else ""
            if not content or len(content) < 50:
                continue

            likes = _parse_int(row[8])
            comments = _parse_int(row[9])
            reposts = _parse_int(row[10])
            followers = _parse_int(row[2])
            likes_ratio = _parse_float(row[7])

            # Engagement score: weighted sum
            engagement = likes + (comments * 3) + (reposts * 2)

            post_id = hashlib.md5(content[:200].encode()).hexdigest()[:12]

            records.append({
                "post_id": post_id,
                "content": content,
                "likes": likes,
                "comments": comments,
                "reposts": reposts,
                "followers": followers,
                "likes_ratio": likes_ratio,
                "engagement_score": engagement,
                "content_type": row[4].strip() if len(row) > 4 else "",
                "creator_url": row[0].strip() if row[0] else "",
            })

    logger.info("Parsed %d posts from %s", len(records), path)
    return records


def _parse_xlsx(path: Path) -> list[dict]:
    """Parse an Excel file with the same column structure as the CSV."""
    import pandas as pd

    logger.info("Parsing Excel file: %s", path)
    df = pd.read_excel(path, sheet_name=0)  # First sheet = data

    records = []
    for _, row in df.iterrows():
        content = str(row.get("Post content", "") or "").strip()
        if not content or len(content) < 50:
            continue

        likes = _parse_int(str(row.get("Likes", 0)))
        comments = _parse_int(str(row.get("Comments", 0)))
        reposts = _parse_int(str(row.get("Reposts", 0)))
        followers = _parse_int(str(row.get("Number of followers", 0)))
        likes_ratio = _parse_float(str(row.get("Likes vs followers ratio", 0)))
        engagement = likes + (comments * 3) + (reposts * 2)
        post_id = hashlib.md5(content[:200].encode()).hexdigest()[:12]

        records.append({
            "post_id": post_id,
            "content": content,
            "likes": likes,
            "comments": comments,
            "reposts": reposts,
            "followers": followers,
            "likes_ratio": likes_ratio,
            "engagement_score": engagement,
            "content_type": str(row.get("Content type", "")).strip(),
            "creator_url": str(row.get("LinkedIn Profile of Creator", "")).strip(),
        })

    logger.info("Parsed %d posts from Excel %s", len(records), path)
    return records


def get_top_posts(records: list[dict], top_pct: float = 0.05) -> list[dict]:
    """Return top N% posts by engagement score."""
    sorted_records = sorted(records, key=lambda r: r["engagement_score"], reverse=True)
    n = max(1, int(len(sorted_records) * top_pct))
    return sorted_records[:n]
