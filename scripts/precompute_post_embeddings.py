"""Pre-compute sentence embeddings for all viral posts in the SQLite database.

Stores embeddings as float32 blobs in the post_embeddings table.
Skips posts that already have embeddings (idempotent).
"""
from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.customizer.post_db import (
    init_db, get_db, init_embeddings_table, store_embeddings, embeddings_count, count_posts,
)

BATCH_SIZE = 64
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2


def _float_list_to_bytes(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def main():
    init_db()
    init_embeddings_table()

    total_posts = count_posts()
    existing = embeddings_count()
    print(f"Posts: {total_posts}, existing embeddings: {existing}")

    conn = get_db()
    rows = conn.execute(
        """SELECT p.post_id, p.content FROM posts p
           LEFT JOIN post_embeddings e ON p.post_id = e.post_id
           WHERE e.post_id IS NULL"""
    ).fetchall()
    conn.close()

    missing = len(rows)
    if missing == 0:
        print("All posts already have embeddings. Done.")
        return

    print(f"Need to embed {missing} posts...")

    from src.vectors.embedder import Embedder
    embedder = Embedder()

    t0 = time.time()
    for i in range(0, missing, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        texts = [r[1][:1000] for r in batch]  # truncate very long posts
        embeddings = embedder.embed(texts)

        pairs = [
            (batch[j][0], _float_list_to_bytes(embeddings[j]))
            for j in range(len(batch))
        ]
        store_embeddings(pairs)

        done = min(i + BATCH_SIZE, missing)
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        print(f"  {done}/{missing} ({rate:.0f} posts/sec)")

    print(f"Done! Embedded {missing} posts in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
