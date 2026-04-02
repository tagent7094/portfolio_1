"""SQLite database for viral posts — search, filter, paginate 43K posts."""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "posts.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables and indexes if they don't exist."""
    print(f"\033[35m[PostDB]\033[0m Initializing database at {DB_PATH}", file=sys.stderr, flush=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            post_id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            reposts INTEGER DEFAULT 0,
            followers INTEGER DEFAULT 0,
            likes_ratio REAL DEFAULT 0,
            engagement_score INTEGER DEFAULT 0,
            content_type TEXT DEFAULT '',
            creator_url TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_engagement ON posts(engagement_score DESC);
        CREATE INDEX IF NOT EXISTS idx_content_type ON posts(content_type);
        CREATE INDEX IF NOT EXISTS idx_followers ON posts(followers);

        CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
            content, content_type,
            content='posts',
            content_rowid='rowid'
        );
    """)
    conn.commit()
    conn.close()
    print(f"\033[35m[PostDB]\033[0m \033[32m→ Database initialized\033[0m", file=sys.stderr, flush=True)


def import_from_csv(csv_path: str | Path | None = None, force: bool = False) -> int:
    """Import viral posts from CSV into SQLite. Idempotent (INSERT OR IGNORE)."""
    if csv_path is None:
        from ..config.founders import get_viral_csv_path
        csv_path = get_viral_csv_path()

    print(f"\033[35m[PostDB]\033[0m Importing from {csv_path}...", file=sys.stderr, flush=True)

    from ..ingestion.viral_csv_parser import parse_viral_csv
    records = parse_viral_csv(csv_path)

    if not records:
        print(f"\033[35m[PostDB]\033[0m \033[31m→ No records parsed\033[0m", file=sys.stderr, flush=True)
        return 0

    init_db()
    conn = get_db()

    if force:
        conn.execute("DELETE FROM posts")
        conn.execute("DELETE FROM posts_fts")

    inserted = 0
    for r in records:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO posts
                   (post_id, content, likes, comments, reposts, followers,
                    likes_ratio, engagement_score, content_type, creator_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r["post_id"], r["content"], r["likes"], r["comments"],
                 r["reposts"], r["followers"], r["likes_ratio"],
                 r["engagement_score"], r["content_type"], r["creator_url"]),
            )
            if conn.total_changes > inserted:
                inserted = conn.total_changes
        except Exception as e:
            logger.debug("Skip row: %s", e)

    # Rebuild FTS index
    conn.execute("INSERT INTO posts_fts(posts_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()

    print(f"\033[35m[PostDB]\033[0m \033[32m→ Imported {inserted} posts\033[0m", file=sys.stderr, flush=True)
    return inserted


def count_posts() -> int:
    init_db()
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    conn.close()
    return count


def browse_posts(
    page: int = 1,
    page_size: int = 20,
    min_engagement: int | None = None,
    max_engagement: int | None = None,
    content_type: str | None = None,
    min_followers: int | None = None,
    max_followers: int | None = None,
    min_likes: int | None = None,
    max_likes: int | None = None,
    min_comments: int | None = None,
    max_comments: int | None = None,
    min_reposts: int | None = None,
    max_reposts: int | None = None,
    sort_by: str = "engagement_score",
    sort_dir: str = "DESC",
) -> dict:
    """Browse posts with filters and pagination."""
    init_db()

    # Auto-import on first use
    if count_posts() == 0:
        import_from_csv()

    conditions = []
    params: list = []

    if min_engagement is not None:
        conditions.append("engagement_score >= ?")
        params.append(min_engagement)
    if max_engagement is not None:
        conditions.append("engagement_score <= ?")
        params.append(max_engagement)
    if content_type:
        conditions.append("content_type = ?")
        params.append(content_type)
    if min_followers is not None:
        conditions.append("followers >= ?")
        params.append(min_followers)
    if max_followers is not None:
        conditions.append("followers <= ?")
        params.append(max_followers)
    if min_likes is not None:
        conditions.append("likes >= ?")
        params.append(min_likes)
    if max_likes is not None:
        conditions.append("likes <= ?")
        params.append(max_likes)
    if min_comments is not None:
        conditions.append("comments >= ?")
        params.append(min_comments)
    if max_comments is not None:
        conditions.append("comments <= ?")
        params.append(max_comments)
    if min_reposts is not None:
        conditions.append("reposts >= ?")
        params.append(min_reposts)
    if max_reposts is not None:
        conditions.append("reposts <= ?")
        params.append(max_reposts)

    where = " AND ".join(conditions) if conditions else "1=1"
    allowed_sorts = {"engagement_score", "likes", "comments", "reposts", "followers", "likes_ratio"}
    sort_col = sort_by if sort_by in allowed_sorts else "engagement_score"
    sort_direction = "ASC" if sort_dir.upper() == "ASC" else "DESC"

    conn = get_db()

    total = conn.execute(f"SELECT COUNT(*) FROM posts WHERE {where}", params).fetchone()[0]
    offset = (page - 1) * page_size

    rows = conn.execute(
        f"SELECT * FROM posts WHERE {where} ORDER BY {sort_col} {sort_direction} LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()

    conn.close()

    return {
        "posts": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def search_posts(query: str, page: int = 1, page_size: int = 20) -> dict:
    """Full-text search in post content."""
    init_db()
    if count_posts() == 0:
        import_from_csv()

    conn = get_db()
    offset = (page - 1) * page_size

    # FTS5 search
    try:
        rows = conn.execute(
            """SELECT p.* FROM posts p
               JOIN posts_fts f ON p.rowid = f.rowid
               WHERE posts_fts MATCH ?
               ORDER BY rank
               LIMIT ? OFFSET ?""",
            (query, page_size, offset),
        ).fetchall()

        total = conn.execute(
            "SELECT COUNT(*) FROM posts_fts WHERE posts_fts MATCH ?", (query,)
        ).fetchone()[0]
    except sqlite3.OperationalError:
        # Fallback to LIKE if FTS fails
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM posts WHERE content LIKE ? ORDER BY engagement_score DESC LIMIT ? OFFSET ?",
            (like, page_size, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM posts WHERE content LIKE ?", (like,)).fetchone()[0]

    conn.close()

    return {
        "posts": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def get_post(post_id: str) -> dict | None:
    init_db()
    conn = get_db()
    row = conn.execute("SELECT * FROM posts WHERE post_id = ?", (post_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
