"""Chat routes — RAG context retrieval, chat stream proxy, posts feed, admin config."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
SHARATH_DATA = PROJECT_ROOT / "data" / "founders" / "sharath" / "founder-data"
SHARATH_CHROMA = PROJECT_ROOT / "data" / "founders" / "sharath" / "knowledge-graph" / "chroma"

router = APIRouter()
admin_chat_router = APIRouter()

# ── Cached data ──────────────────────────────────────────────────────────────

_posts_cache: list[dict] | None = None
_embedder_instance = None


def _get_embedder():
    global _embedder_instance
    if _embedder_instance is None:
        from src.vectors.embedder import Embedder
        _embedder_instance = Embedder()
    return _embedder_instance


def _parse_posts() -> list[dict]:
    global _posts_cache
    if _posts_cache is not None:
        return _posts_cache

    posts_file = SHARATH_DATA / "sharath-linkedin-posts.txt"
    if not posts_file.exists():
        _posts_cache = []
        return _posts_cache

    text = posts_file.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Skip header line
    posts: list[dict] = []
    i = 0
    if lines and lines[0].strip() == "Post":
        i = 4  # skip "Post", "Number of likes", "Number of comments", "Reposts"

    current_content_lines: list[str] = []
    while i < len(lines):
        line = lines[i]
        # Engagement line: tab + digits only
        if re.match(r"^\t\d+$", line):
            likes = int(line.strip())
            comments = int(lines[i + 1].strip()) if i + 1 < len(lines) else 0
            reposts = int(lines[i + 2].strip()) if i + 2 < len(lines) else 0

            content = "\n".join(current_content_lines).strip()
            if content:
                posts.append({
                    "content": content,
                    "likes": likes,
                    "comments": comments,
                    "reposts": reposts,
                })
            current_content_lines = []
            i += 3
            continue

        # Content line (strip leading tab that separates posts)
        if line.startswith("\t") and not current_content_lines:
            current_content_lines.append(line[1:])
        else:
            current_content_lines.append(line)
        i += 1

    # Last post if no trailing metrics
    content = "\n".join(current_content_lines).strip()
    if content:
        posts.append({"content": content, "likes": 0, "comments": 0, "reposts": 0})

    _posts_cache = posts
    logger.info("[chat] Parsed %d LinkedIn posts", len(posts))
    return _posts_cache


def _load_system_prompt() -> str:
    path = SHARATH_DATA / "chat-system-prompt.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "You are Sharath Keshava Narayana. Respond as he would, drawing on his experiences and beliefs."


# ── Public endpoints ─────────────────────────────────────────────────────────

class ChatContextRequest(BaseModel):
    query: str
    n_results: int = 8


@router.post("/api/chat/context")
async def chat_context(data: ChatContextRequest):
    """Embed query, search ChromaDB, return relevant chunks + system prompt."""
    if not data.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    system_prompt = _load_system_prompt()
    chunks: list[dict] = []

    # RAG retrieval — gracefully degrade if embedder/vectorstore unavailable
    try:
        from src.vectors.store import VectorStore
        embedder = _get_embedder()
        store = VectorStore(persist_dir=str(SHARATH_CHROMA))

        if store.count() > 0:
            query_embedding = embedder.embed([data.query])[0]
            results = store.search(query_embedding, n_results=data.n_results)

            if results and results.get("documents"):
                docs = results["documents"][0]
                metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
                distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
                for doc, meta, dist in zip(docs, metas, distances):
                    chunks.append({
                        "text": doc,
                        "source_type": meta.get("source_type", "unknown"),
                        "distance": round(dist, 4),
                    })
        else:
            logger.warning("[chat] ChromaDB collection is empty — run scripts/index_sharath_rag.py")
    except Exception as e:
        logger.warning("[chat] RAG retrieval failed (chatbot will work without context): %s", e)

    return {"chunks": chunks, "system_prompt": system_prompt}


class ChatStreamRequest(BaseModel):
    messages: list[dict]
    model: str = "claude-sonnet-4-6"
    api_key: str
    system: str = ""


@router.post("/api/chat/stream")
async def chat_stream(data: ChatStreamRequest):
    """Proxy streaming chat to Claude API. API key comes from the client."""
    if not data.api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    if not data.messages:
        raise HTTPException(status_code=400, detail="Messages are required")

    import anthropic

    client = anthropic.Anthropic(api_key=data.api_key)

    async def generate():
        try:
            with client.messages.stream(
                model=data.model,
                max_tokens=4096,
                system=data.system,
                messages=data.messages,
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except anthropic.AuthenticationError:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Invalid API key'})}\n\n"
        except anthropic.RateLimitError:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Rate limit exceeded. Please try again in a moment.'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/chat/posts")
async def chat_posts():
    """Return parsed LinkedIn posts as JSON for the feed."""
    posts = _parse_posts()
    return {"posts": posts, "total": len(posts)}


# ── Admin endpoints (protected by admin auth) ───────────────────────────────

class ChatConfigUpdate(BaseModel):
    system_prompt: str | None = None
    post_writing_instructions: str | None = None
    opening_line_amplifier: str | None = None


@admin_chat_router.get("/api/admin/chat-config")
async def get_chat_config():
    """Return all editable instruction files."""
    system_prompt = ""
    sp_path = SHARATH_DATA / "chat-system-prompt.md"
    if sp_path.exists():
        system_prompt = sp_path.read_text(encoding="utf-8")

    post_writing = ""
    pw_path = SHARATH_DATA / "linkedin-ghostwriting-system-instruction.md"
    if pw_path.exists():
        post_writing = pw_path.read_text(encoding="utf-8")

    opening_line = ""
    ol_path = SHARATH_DATA / "opening-line-amplifier.md"
    if ol_path.exists():
        opening_line = ol_path.read_text(encoding="utf-8")

    return {
        "system_prompt": system_prompt,
        "post_writing_instructions": post_writing,
        "opening_line_amplifier": opening_line,
    }


@admin_chat_router.put("/api/admin/chat-config")
async def update_chat_config(data: ChatConfigUpdate):
    """Save editable instruction files."""
    if data.system_prompt is not None:
        (SHARATH_DATA / "chat-system-prompt.md").write_text(data.system_prompt, encoding="utf-8")
        logger.info("[chat-admin] Updated chat-system-prompt.md (%d chars)", len(data.system_prompt))

    if data.post_writing_instructions is not None:
        (SHARATH_DATA / "linkedin-ghostwriting-system-instruction.md").write_text(
            data.post_writing_instructions, encoding="utf-8"
        )
        logger.info("[chat-admin] Updated linkedin-ghostwriting-system-instruction.md (%d chars)",
                     len(data.post_writing_instructions))

    if data.opening_line_amplifier is not None:
        (SHARATH_DATA / "opening-line-amplifier.md").write_text(
            data.opening_line_amplifier, encoding="utf-8"
        )
        logger.info("[chat-admin] Updated opening-line-amplifier.md (%d chars)", len(data.opening_line_amplifier))

    return {"status": "ok"}
