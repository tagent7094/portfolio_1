"""SQLite database for blog post metadata — list, search, status tracking."""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "blogs.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    print(f"\033[36m[BlogDB]\033[0m Initializing database at {DB_PATH}", file=sys.stderr, flush=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS blogs (
            blog_id TEXT PRIMARY KEY,
            founder_slug TEXT NOT NULL,
            title TEXT NOT NULL,
            topic TEXT NOT NULL,
            tone TEXT DEFAULT 'conversational',
            format_type TEXT DEFAULT 'blog',
            source_type TEXT DEFAULT 'topic',
            word_count INTEGER DEFAULT 0,
            seo_title TEXT DEFAULT '',
            meta_description TEXT DEFAULT '',
            file_path TEXT NOT NULL,
            voice_score INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'draft'
        );

        CREATE INDEX IF NOT EXISTS idx_blog_founder ON blogs(founder_slug);
        CREATE INDEX IF NOT EXISTS idx_blog_created ON blogs(created_at DESC);

        CREATE TABLE IF NOT EXISTS podcasts (
            podcast_id TEXT PRIMARY KEY,
            founder_slug TEXT NOT NULL,
            title TEXT NOT NULL,
            host TEXT DEFAULT '',
            episode_url TEXT DEFAULT '',
            source_type TEXT DEFAULT 'upload',
            youtube_url TEXT DEFAULT '',
            transcript_path TEXT NOT NULL,
            transcript_length INTEGER DEFAULT 0,
            date TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_podcast_founder ON podcasts(founder_slug);

        CREATE TABLE IF NOT EXISTS document_categories (
            category_id TEXT PRIMARY KEY,
            founder_slug TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE(founder_slug, name)
        );

        CREATE INDEX IF NOT EXISTS idx_doccat_founder ON document_categories(founder_slug);

        CREATE TABLE IF NOT EXISTS studio_documents (
            document_id TEXT PRIMARY KEY,
            founder_slug TEXT NOT NULL,
            category_id TEXT,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            text_content TEXT DEFAULT '',
            text_length INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES document_categories(category_id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_studiodoc_founder ON studio_documents(founder_slug);
        CREATE INDEX IF NOT EXISTS idx_studiodoc_category ON studio_documents(category_id);
    """)
    conn.commit()
    conn.close()
    print(f"\033[36m[BlogDB]\033[0m \033[32m→ Database initialized\033[0m", file=sys.stderr, flush=True)


def insert_blog(blog_id: str, founder_slug: str, title: str, topic: str,
                tone: str, format_type: str, source_type: str,
                word_count: int, seo_title: str, meta_description: str,
                file_path: str, voice_score: int, created_at: str) -> None:
    conn = get_db()
    conn.execute(
        """INSERT INTO blogs (blog_id, founder_slug, title, topic, tone,
           format_type, source_type, word_count, seo_title, meta_description,
           file_path, voice_score, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (blog_id, founder_slug, title, topic, tone, format_type, source_type,
         word_count, seo_title, meta_description, file_path, voice_score, created_at),
    )
    conn.commit()
    conn.close()


def list_blogs(founder_slug: str, limit: int = 20, offset: int = 0) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM blogs WHERE founder_slug = ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (founder_slug, limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_blog(blog_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM blogs WHERE blog_id = ?", (blog_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_blog_status(blog_id: str, status: str) -> bool:
    conn = get_db()
    cursor = conn.execute(
        "UPDATE blogs SET status = ? WHERE blog_id = ?", (status, blog_id),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def delete_blog(blog_id: str) -> bool:
    conn = get_db()
    row = conn.execute("SELECT file_path FROM blogs WHERE blog_id = ?", (blog_id,)).fetchone()
    if row:
        fp = Path(row["file_path"])
        if fp.exists():
            fp.unlink()
    cursor = conn.execute("DELETE FROM blogs WHERE blog_id = ?", (blog_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def count_blogs(founder_slug: str) -> int:
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM blogs WHERE founder_slug = ?", (founder_slug,),
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


# ── Podcast CRUD ────────────────────────────────────────────────────────

def insert_podcast(podcast_id: str, founder_slug: str, title: str,
                   host: str, episode_url: str, source_type: str,
                   youtube_url: str, transcript_path: str,
                   transcript_length: int, date: str, notes: str,
                   created_at: str) -> None:
    conn = get_db()
    conn.execute(
        """INSERT INTO podcasts (podcast_id, founder_slug, title, host, episode_url,
           source_type, youtube_url, transcript_path, transcript_length, date, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (podcast_id, founder_slug, title, host, episode_url, source_type,
         youtube_url, transcript_path, transcript_length, date, notes, created_at),
    )
    conn.commit()
    conn.close()


def list_podcasts(founder_slug: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM podcasts WHERE founder_slug = ? ORDER BY created_at DESC",
        (founder_slug,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_podcast(podcast_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM podcasts WHERE podcast_id = ?", (podcast_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_podcast(podcast_id: str) -> bool:
    conn = get_db()
    row = conn.execute("SELECT transcript_path FROM podcasts WHERE podcast_id = ?", (podcast_id,)).fetchone()
    if row:
        fp = Path(row["transcript_path"])
        if not fp.is_absolute():
            fp = PROJECT_ROOT / fp
        if fp.exists():
            fp.unlink()
    cursor = conn.execute("DELETE FROM podcasts WHERE podcast_id = ?", (podcast_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# ── Document Category CRUD ──────────────────────────────────────────────

def insert_category(category_id: str, founder_slug: str, name: str,
                    description: str, created_at: str) -> None:
    conn = get_db()
    conn.execute(
        """INSERT INTO document_categories (category_id, founder_slug, name, description, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (category_id, founder_slug, name, description, created_at),
    )
    conn.commit()
    conn.close()


def list_categories(founder_slug: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM document_categories WHERE founder_slug = ? ORDER BY name",
        (founder_slug,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_category(category_id: str, name: str, description: str) -> bool:
    conn = get_db()
    cursor = conn.execute(
        "UPDATE document_categories SET name = ?, description = ? WHERE category_id = ?",
        (name, description, category_id),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def delete_category(category_id: str) -> bool:
    conn = get_db()
    conn.execute(
        "UPDATE studio_documents SET category_id = NULL WHERE category_id = ?",
        (category_id,),
    )
    cursor = conn.execute("DELETE FROM document_categories WHERE category_id = ?", (category_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


# ── Studio Document CRUD ────────────────────────────────────────────────

def insert_document(document_id: str, founder_slug: str, category_id: str | None,
                    filename: str, file_path: str, file_type: str,
                    file_size: int, text_content: str, text_length: int,
                    created_at: str) -> None:
    conn = get_db()
    conn.execute(
        """INSERT INTO studio_documents (document_id, founder_slug, category_id, filename,
           file_path, file_type, file_size, text_content, text_length, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (document_id, founder_slug, category_id, filename, file_path,
         file_type, file_size, text_content, text_length, created_at),
    )
    conn.commit()
    conn.close()


def list_documents(founder_slug: str, category_id: str | None = None) -> list[dict]:
    conn = get_db()
    if category_id:
        rows = conn.execute(
            """SELECT document_id, founder_slug, category_id, filename, file_path,
               file_type, file_size, text_length, created_at
               FROM studio_documents WHERE founder_slug = ? AND category_id = ?
               ORDER BY created_at DESC""",
            (founder_slug, category_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT document_id, founder_slug, category_id, filename, file_path,
               file_type, file_size, text_length, created_at
               FROM studio_documents WHERE founder_slug = ?
               ORDER BY created_at DESC""",
            (founder_slug,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document(document_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM studio_documents WHERE document_id = ?", (document_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_documents_by_ids(document_ids: list[str]) -> list[dict]:
    if not document_ids:
        return []
    conn = get_db()
    placeholders = ",".join("?" for _ in document_ids)
    rows = conn.execute(
        f"SELECT * FROM studio_documents WHERE document_id IN ({placeholders})",
        document_ids,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_document_category(document_id: str, category_id: str | None) -> bool:
    conn = get_db()
    cursor = conn.execute(
        "UPDATE studio_documents SET category_id = ? WHERE document_id = ?",
        (category_id, document_id),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def delete_document(document_id: str) -> bool:
    conn = get_db()
    row = conn.execute("SELECT file_path FROM studio_documents WHERE document_id = ?", (document_id,)).fetchone()
    if row:
        fp = Path(row["file_path"])
        if fp.exists():
            fp.unlink()
    cursor = conn.execute("DELETE FROM studio_documents WHERE document_id = ?", (document_id,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
