#!/usr/bin/env python3
"""Index all of Sharath's content into ChromaDB for RAG retrieval.

Chunks and embeds:
  - LinkedIn posts (~145)
  - Voice DNA document
  - Story bank
  - Personality card
  - Knowledge graph nodes (beliefs, stories, thinking models, contrast pairs)
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SHARATH_DATA = PROJECT_ROOT / "data" / "founders" / "sharath" / "founder-data"
GRAPH_PATH = PROJECT_ROOT / "data" / "founders" / "sharath" / "knowledge-graph" / "graph.json"
CHROMA_DIR = PROJECT_ROOT / "data" / "founders" / "sharath" / "knowledge-graph" / "chroma"


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks at paragraph boundaries."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            # Keep last bit for overlap
            words = current.split()
            overlap_words = words[-min(len(words), overlap // 5):]
            current = " ".join(overlap_words) + "\n\n" + para
        else:
            current = (current + "\n\n" + para) if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks


def parse_posts(path: Path) -> list[dict]:
    """Parse LinkedIn posts file into structured records."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    posts: list[dict] = []
    i = 0
    if lines and lines[0].strip() == "Post":
        i = 4

    content_lines: list[str] = []
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\t\d+$", line):
            likes = int(line.strip())
            comments = int(lines[i + 1].strip()) if i + 1 < len(lines) else 0
            reposts = int(lines[i + 2].strip()) if i + 2 < len(lines) else 0
            content = "\n".join(content_lines).strip()
            if content:
                posts.append({"content": content, "likes": likes, "comments": comments, "reposts": reposts})
            content_lines = []
            i += 3
            continue
        if line.startswith("\t") and not content_lines:
            content_lines.append(line[1:])
        else:
            content_lines.append(line)
        i += 1

    content = "\n".join(content_lines).strip()
    if content:
        posts.append({"content": content, "likes": 0, "comments": 0, "reposts": 0})
    return posts


def stable_id(prefix: str, text: str) -> str:
    return f"{prefix}_{hashlib.md5(text[:200].encode()).hexdigest()[:12]}"


def main():
    from src.vectors.embedder import Embedder
    from src.vectors.store import VectorStore

    print("Loading embedder...")
    embedder = Embedder()
    store = VectorStore(persist_dir=str(CHROMA_DIR))

    all_ids: list[str] = []
    all_texts: list[str] = []
    all_metas: list[dict] = []

    # 1. LinkedIn posts
    posts_file = SHARATH_DATA / "sharath-linkedin-posts.txt"
    if posts_file.exists():
        posts = parse_posts(posts_file)
        print(f"Parsed {len(posts)} LinkedIn posts")
        for idx, post in enumerate(posts):
            doc_id = stable_id("post", post["content"])
            all_ids.append(doc_id)
            all_texts.append(post["content"])
            all_metas.append({
                "source_type": "post",
                "post_index": idx,
                "likes": post["likes"],
                "comments": post["comments"],
                "reposts": post["reposts"],
            })

    # 2. Voice DNA
    voice_dna_file = SHARATH_DATA / "voice-dna-sharath-v2.md"
    if voice_dna_file.exists():
        chunks = chunk_text(voice_dna_file.read_text(encoding="utf-8"))
        print(f"Voice DNA: {len(chunks)} chunks")
        for chunk in chunks:
            all_ids.append(stable_id("voice", chunk))
            all_texts.append(chunk)
            all_metas.append({"source_type": "voice_dna"})

    # 3. Story bank
    story_bank_file = SHARATH_DATA / "story-bank-sharath.md"
    if story_bank_file.exists():
        chunks = chunk_text(story_bank_file.read_text(encoding="utf-8"))
        print(f"Story bank: {len(chunks)} chunks")
        for chunk in chunks:
            all_ids.append(stable_id("story", chunk))
            all_texts.append(chunk)
            all_metas.append({"source_type": "story_bank"})

    # 4. Personality card
    card_file = PROJECT_ROOT / "data" / "founders" / "sharath" / "knowledge-graph" / "personality-card.md"
    if card_file.exists():
        card_text = card_file.read_text(encoding="utf-8")
        all_ids.append(stable_id("card", card_text))
        all_texts.append(card_text)
        all_metas.append({"source_type": "personality_card"})

    # 5. Knowledge graph nodes
    if GRAPH_PATH.exists():
        import json
        import networkx as nx
        from networkx.readwrite import json_graph

        with open(GRAPH_PATH) as f:
            graph = json_graph.node_link_graph(json.load(f))

        node_count = 0
        for node_id, data in graph.nodes(data=True):
            node_type = data.get("node_type", "")
            if node_type not in ("belief", "story", "thinking_model", "contrast_pair", "style_rule"):
                continue

            # Build a text representation
            parts = [f"[{node_type.upper()}]"]
            for key in ("topic", "title", "name", "description", "rule_type", "content",
                        "belief", "narrative", "rule", "example", "when_to_use"):
                val = data.get(key)
                if val:
                    parts.append(f"{key}: {val}" if isinstance(val, str) else f"{key}: {val}")

            text = "\n".join(str(p) for p in parts)
            if len(text) < 20:
                continue

            all_ids.append(stable_id(f"graph_{node_type}", text))
            all_texts.append(text)
            all_metas.append({"source_type": node_type, "node_id": node_id})
            node_count += 1

        print(f"Knowledge graph: {node_count} nodes indexed")

    # Deduplicate by ID
    seen = set()
    deduped = {"ids": [], "texts": [], "metas": []}
    for doc_id, text, meta in zip(all_ids, all_texts, all_metas):
        if doc_id not in seen:
            seen.add(doc_id)
            deduped["ids"].append(doc_id)
            deduped["texts"].append(text)
            deduped["metas"].append(meta)

    total = len(deduped["ids"])
    print(f"\nTotal documents to embed: {total}")

    # Embed in batches
    batch_size = 64
    all_embeddings: list[list[float]] = []
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch_texts = deduped["texts"][start:end]
        print(f"  Embedding batch {start}-{end}...")
        embs = embedder.embed(batch_texts)
        all_embeddings.extend(embs)

    # Upsert into ChromaDB (delete existing collection first for clean state)
    print("Writing to ChromaDB...")
    try:
        store.client.delete_collection("founder_content")
    except Exception:
        pass
    store = VectorStore(persist_dir=str(CHROMA_DIR))
    store.add(
        ids=deduped["ids"],
        texts=deduped["texts"],
        metadatas=deduped["metas"],
        embeddings=all_embeddings,
    )

    print(f"\nDone! {store.count()} documents in ChromaDB.")


if __name__ == "__main__":
    main()
