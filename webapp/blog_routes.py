"""Blog & Narrative routes — Content Studio API endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import re

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

blog_router = APIRouter()

# ── Background task state ────────────────────────────────────────────────

_blog_tasks: dict[str, dict] = {}
_MAX_FINISHED = 20


def _cleanup_old():
    finished = [k for k, v in _blog_tasks.items() if v["status"] in ("done", "error", "cancelled")]
    if len(finished) > _MAX_FINISHED:
        by_time = sorted(finished, key=lambda k: _blog_tasks[k].get("finished_at", ""))
        for k in by_time[: len(finished) - _MAX_FINISHED]:
            del _blog_tasks[k]


# ── Request models ───────────────────────────────────────────────────────

class TopicDiscoveryRequest(BaseModel):
    founder_slug: str
    n_topics: int = 10


class BlogGenerateRequest(BaseModel):
    founder_slug: str
    topic: str
    tone: str = "conversational"
    target_word_count: int = 1500
    seo_focus: bool = True
    custom_instructions: str = ""
    document_ids: list[str] = []
    podcast_ids: list[str] = []
    mode: str = "auto"


class NarrativeAnalyzeRequest(BaseModel):
    founder_slug: str
    podcast_ids: list[str] = []


class NarrativeGenerateRequest(BaseModel):
    founder_slug: str
    podcast_ids: list[str] = []
    narrative_angle: str
    format_type: str = "thought_leadership"
    tone: str = "conversational"
    target_word_count: int = 1500


class BlogStatusUpdate(BaseModel):
    status: str


class YouTubeTranscriptRequest(BaseModel):
    founder_slug: str
    youtube_url: str
    title: str = ""
    host: str = ""
    date: str = ""


class PasteTranscriptRequest(BaseModel):
    founder_slug: str
    text: str
    title: str = "Pasted Transcript"
    host: str = ""
    date: str = ""


class CreateCategoryRequest(BaseModel):
    founder_slug: str
    name: str
    description: str = ""


class UpdateCategoryRequest(BaseModel):
    name: str
    description: str = ""


class UpdateDocCategoryRequest(BaseModel):
    category_id: str | None = None


PROJECT_ROOT = Path(__file__).parent.parent


# ── Topic Discovery ─────────────────────────────────────────────────────

@blog_router.post("/api/blog/discover-topics")
async def discover_topics_endpoint(data: TopicDiscoveryRequest):
    """Run topic discovery and return ranked topics."""
    logger.info("[blog] discover-topics founder=%s n=%d", data.founder_slug, data.n_topics)

    from src.blog.session import BlogSession
    from src.blog.topic_discovery import discover_topics
    from src.blog.state import BlogState
    from src.batch.corpus_reader import load_founder_state
    from src.llm.task_router import LLMRouter

    try:
        router = LLMRouter(config_path="config/llm-config.yaml", founder_slug=data.founder_slug)
        llm = router.for_task("blog_topic_discovery")

        batch_state = await asyncio.to_thread(load_founder_state, data.founder_slug, "linkedin")
        state = BlogState(
            founder_slug=data.founder_slug,
            personality_card=batch_state.personality_card,
            founder_ctx=batch_state.founder_ctx,
            raw_data=batch_state.raw_data,
            llm_router=router,
        )

        topics = await asyncio.to_thread(discover_topics, llm, state, data.n_topics)
        return {"topics": topics}
    except Exception as e:
        logger.exception("[blog] topic discovery failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Blog Generation ─────────────────────────────────────────────────────

@blog_router.post("/api/blog/generate/background")
async def generate_blog_background(data: BlogGenerateRequest):
    """Start blog generation as a background task."""
    logger.info("[blog_bg] founder=%s topic=%s tone=%s", data.founder_slug, data.topic, data.tone)

    from src.generation.pipeline_events import PipelineEventBus
    from src.blog.session import BlogSession, CancelledError

    task_id = uuid.uuid4().hex[:10]
    event_bus = PipelineEventBus()
    session = BlogSession(event_bus=event_bus)

    task_state: dict = {
        "task_id": task_id,
        "type": "blog",
        "founder_slug": data.founder_slug,
        "topic": data.topic,
        "status": "running",
        "progress": 0.0,
        "stage": "starting",
        "log": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "error": None,
        "blog_id": None,
        "result": None,
        "_session": session,
    }
    _blog_tasks[task_id] = task_state
    _cleanup_old()

    source_documents_text = ""
    source_document_names: list[str] = []
    podcast_transcripts_text = ""
    podcast_names: list[str] = []

    if data.document_ids:
        from src.blog import db as blogdb
        blogdb.init_db()
        docs = blogdb.get_documents_by_ids(data.document_ids)
        for d in docs:
            source_document_names.append(d["filename"])
            if d.get("text_content"):
                source_documents_text += f"\n\n--- {d['filename']} ---\n{d['text_content']}"

    if data.podcast_ids:
        from src.blog import db as blogdb
        blogdb.init_db()
        for pid in data.podcast_ids:
            pod = blogdb.get_podcast(pid)
            if pod:
                podcast_names.append(pod["title"])
                fp = Path(pod["transcript_path"])
                if fp.exists():
                    podcast_transcripts_text += f"\n\n--- {pod['title']} ---\n{fp.read_text(encoding='utf-8', errors='replace')}"

    async def _run():
        try:
            gen_future = asyncio.ensure_future(asyncio.to_thread(
                session.run,
                founder_slug=data.founder_slug,
                topic=data.topic,
                tone=data.tone,
                target_word_count=data.target_word_count,
                seo_focus=data.seo_focus,
                custom_instructions=data.custom_instructions,
                source_documents_text=source_documents_text,
                source_document_names=source_document_names,
                podcast_transcripts_text=podcast_transcripts_text,
                podcast_names=podcast_names,
                generation_mode=data.mode,
            ))

            async for chunk in event_bus.stream():
                if not chunk.startswith("data:"):
                    continue
                try:
                    ev = json.loads(chunk[5:].strip())
                except Exception:
                    continue
                task_state["progress"] = ev.get("progress", task_state["progress"])
                task_state["stage"] = ev.get("stage", task_state["stage"])
                llm_text = ev.get("llm_text", "")
                if llm_text:
                    task_state["current_llm_text"] = llm_text
                if ev.get("status") == "llm_chunk":
                    continue
                task_state["log"].append({
                    "stage": ev.get("stage", ""),
                    "status": ev.get("status", ""),
                    "data": ev.get("data", {}),
                })
                blog_id = (ev.get("data") or {}).get("blog_id")
                if blog_id:
                    task_state["blog_id"] = blog_id
                err = (ev.get("data") or {}).get("error")
                if err:
                    task_state["error"] = err
                if ev.get("status") == "pipeline_done":
                    break

            result = await gen_future
            task_state["result"] = {k: v for k, v in result.items() if k != "markdown"}

            if task_state["error"]:
                task_state["status"] = "error"
            elif task_state["status"] == "running":
                task_state["status"] = "done"
                task_state["progress"] = 1.0

        except CancelledError:
            task_state["status"] = "cancelled"
        except Exception as e:
            logger.exception("[blog_bg] failed: %s", e)
            task_state["status"] = "error"
            task_state["error"] = str(e)
        finally:
            task_state["finished_at"] = datetime.now(timezone.utc).isoformat()

    asyncio.create_task(_run())
    return {"task_id": task_id}


@blog_router.get("/api/blog/generate/status/{task_id}")
async def get_blog_task_status(task_id: str, since: int = 0):
    """Poll blog generation task status."""
    task = _blog_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task["task_id"],
        "type": task.get("type", "blog"),
        "founder_slug": task["founder_slug"],
        "topic": task.get("topic", ""),
        "status": task["status"],
        "progress": task["progress"],
        "stage": task["stage"],
        "log": task["log"][since:],
        "log_offset": len(task["log"]),
        "started_at": task["started_at"],
        "finished_at": task["finished_at"],
        "error": task["error"],
        "blog_id": task.get("blog_id"),
        "result": task.get("result"),
        "current_llm_text": task.get("current_llm_text", ""),
    }


@blog_router.post("/api/blog/generate/cancel/{task_id}")
async def cancel_blog_task(task_id: str):
    """Cancel a running blog generation task."""
    task = _blog_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    session = task.get("_session")
    if session and hasattr(session, "cancel_event"):
        session.cancel_event.set()
    task["status"] = "cancelled"
    task["finished_at"] = datetime.now(timezone.utc).isoformat()
    return {"status": "cancelled"}


# ── Narrative Analysis & Generation ──────────────────────────────────────

@blog_router.post("/api/blog/narrative/analyze")
async def analyze_narrative_endpoint(data: NarrativeAnalyzeRequest):
    """Analyze transcripts and return narrative angles."""
    logger.info("[narrative] analyze founder=%s podcast_ids=%s", data.founder_slug, data.podcast_ids)

    from src.blog.narrative_session import NarrativeSession

    podcast_transcript_text = ""
    if data.podcast_ids:
        from src.blog.db import get_podcast
        from pathlib import Path as _Path
        parts = []
        for pid in data.podcast_ids:
            pod = get_podcast(pid)
            if pod and pod.get("transcript_path"):
                p = _Path(pod["transcript_path"])
                if p.exists():
                    parts.append(p.read_text(encoding="utf-8", errors="replace"))
        podcast_transcript_text = "\n\n---\n\n".join(parts)

    try:
        session = NarrativeSession()
        result = await asyncio.to_thread(
            session.analyze, data.founder_slug,
            override_transcript=podcast_transcript_text or None,
        )
        return result
    except Exception as e:
        logger.exception("[narrative] analysis failed")
        raise HTTPException(status_code=500, detail=str(e))


@blog_router.post("/api/blog/narrative/generate/background")
async def generate_narrative_background(data: NarrativeGenerateRequest):
    """Start narrative blog generation as a background task."""
    logger.info("[narrative_bg] founder=%s angle=%s format=%s podcast_ids=%s",
                data.founder_slug, data.narrative_angle[:50], data.format_type, data.podcast_ids)

    from src.generation.pipeline_events import PipelineEventBus
    from src.blog.narrative_session import NarrativeSession
    from src.blog.session import CancelledError

    podcast_transcript_text = ""
    if data.podcast_ids:
        from src.blog.db import get_podcast
        from pathlib import Path as _Path
        parts = []
        for pid in data.podcast_ids:
            pod = get_podcast(pid)
            if pod and pod.get("transcript_path"):
                p = _Path(pod["transcript_path"])
                if p.exists():
                    parts.append(p.read_text(encoding="utf-8", errors="replace"))
        podcast_transcript_text = "\n\n---\n\n".join(parts)

    task_id = uuid.uuid4().hex[:10]
    event_bus = PipelineEventBus()
    session = NarrativeSession(event_bus=event_bus)

    task_state: dict = {
        "task_id": task_id,
        "type": "narrative",
        "founder_slug": data.founder_slug,
        "topic": data.narrative_angle,
        "status": "running",
        "progress": 0.0,
        "stage": "starting",
        "log": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "error": None,
        "blog_id": None,
        "result": None,
        "_session": session,
    }
    _blog_tasks[task_id] = task_state
    _cleanup_old()

    async def _run():
        try:
            gen_future = asyncio.ensure_future(asyncio.to_thread(
                session.run,
                founder_slug=data.founder_slug,
                narrative_angle=data.narrative_angle,
                format_type=data.format_type,
                tone=data.tone,
                target_word_count=data.target_word_count,
                override_transcript=podcast_transcript_text or None,
            ))

            async for chunk in event_bus.stream():
                if not chunk.startswith("data:"):
                    continue
                try:
                    ev = json.loads(chunk[5:].strip())
                except Exception:
                    continue
                task_state["progress"] = ev.get("progress", task_state["progress"])
                task_state["stage"] = ev.get("stage", task_state["stage"])
                llm_text = ev.get("llm_text", "")
                if llm_text:
                    task_state["current_llm_text"] = llm_text
                if ev.get("status") == "llm_chunk":
                    continue
                task_state["log"].append({
                    "stage": ev.get("stage", ""),
                    "status": ev.get("status", ""),
                    "data": ev.get("data", {}),
                })
                blog_id = (ev.get("data") or {}).get("blog_id")
                if blog_id:
                    task_state["blog_id"] = blog_id
                err = (ev.get("data") or {}).get("error")
                if err:
                    task_state["error"] = err
                if ev.get("status") == "pipeline_done":
                    break

            result = await gen_future
            task_state["result"] = {k: v for k, v in result.items() if k != "markdown"}

            if task_state["error"]:
                task_state["status"] = "error"
            elif task_state["status"] == "running":
                task_state["status"] = "done"
                task_state["progress"] = 1.0

        except CancelledError:
            task_state["status"] = "cancelled"
        except Exception as e:
            logger.exception("[narrative_bg] failed: %s", e)
            task_state["status"] = "error"
            task_state["error"] = str(e)
        finally:
            task_state["finished_at"] = datetime.now(timezone.utc).isoformat()

    asyncio.create_task(_run())
    return {"task_id": task_id}


# ── Blog CRUD ────────────────────────────────────────────────────────────

@blog_router.get("/api/blog/list/{founder_slug}")
async def list_blogs_endpoint(founder_slug: str, limit: int = 20, offset: int = 0):
    """List generated blogs for a founder."""
    from src.blog import db
    db.init_db()
    blogs = db.list_blogs(founder_slug, limit, offset)
    total = db.count_blogs(founder_slug)
    return {"blogs": blogs, "total": total}


@blog_router.get("/api/blog/{blog_id}")
async def get_blog_endpoint(blog_id: str):
    """Get a single blog with its content."""
    from src.blog import db
    db.init_db()
    blog = db.get_blog(blog_id)
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")

    content = ""
    fp = Path(blog["file_path"])
    if fp.exists():
        content = fp.read_text(encoding="utf-8")

    return {**blog, "content": content}


@blog_router.put("/api/blog/{blog_id}/status")
async def update_blog_status_endpoint(blog_id: str, data: BlogStatusUpdate):
    """Update blog status (draft/published/archived)."""
    from src.blog import db
    db.init_db()
    if data.status not in ("draft", "published", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status")
    ok = db.update_blog_status(blog_id, data.status)
    if not ok:
        raise HTTPException(status_code=404, detail="Blog not found")
    return {"status": data.status}


@blog_router.delete("/api/blog/{blog_id}")
async def delete_blog_endpoint(blog_id: str):
    """Delete a blog and its file."""
    from src.blog import db
    db.init_db()
    ok = db.delete_blog(blog_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Blog not found")
    return {"deleted": True}


# ── Podcast Management ──────────────────────────────────────────────────

def _sanitize_filename(name: str) -> str:
    return re.sub(r'[^\w\s-]', '', name).strip().replace(' ', '_')[:50]


@blog_router.post("/api/studio/podcasts/upload")
async def upload_podcast_transcript(
    file: UploadFile = File(...),
    founder_slug: str = Form(...),
    title: str = Form(""),
    host: str = Form(""),
    date: str = Form(""),
    episode_url: str = Form(""),
):
    """Upload a transcript file with metadata."""
    from src.blog import db
    db.init_db()

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".txt", ".md", ".docx"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    podcast_id = uuid.uuid4().hex[:10]
    safe_name = _sanitize_filename(title or Path(file.filename).stem)
    dest_dir = PROJECT_ROOT / "data" / "founders" / founder_slug / "podcast-data"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"{podcast_id}_{safe_name}{suffix}"

    content = await file.read()
    dest_file.write_bytes(content)

    text = ""
    if suffix in (".txt", ".md"):
        text = dest_file.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".docx":
        from src.ingestion.docx_reader import read_docx
        doc = read_docx(dest_file)
        text = doc.get("plain_text", "")

    db.insert_podcast(
        podcast_id=podcast_id,
        founder_slug=founder_slug,
        title=title or Path(file.filename).stem,
        host=host,
        episode_url=episode_url,
        source_type="upload",
        youtube_url="",
        transcript_path=str(dest_file),
        transcript_length=len(text),
        date=date,
        notes="",
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    return {"podcast_id": podcast_id, "title": title, "transcript_length": len(text)}


@blog_router.post("/api/studio/podcasts/youtube")
async def extract_youtube_podcast(data: YouTubeTranscriptRequest):
    """Extract transcript from a YouTube URL, then structure it via LLM."""
    from src.blog.youtube_transcript import extract_youtube_transcript, structure_transcript, structured_text_from_result
    from src.llm.task_router import LLMRouter
    from src.blog import db
    db.init_db()

    result = await asyncio.to_thread(extract_youtube_transcript, data.youtube_url)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    raw_text = result["text"]
    if not raw_text:
        raise HTTPException(status_code=400, detail="No transcript content extracted")

    # Structure the raw captions via LLM
    def _structure():
        router = LLMRouter(founder_slug=data.founder_slug)
        llm = router.for_task("transcript_structure")
        return structure_transcript(raw_text, result["language"], result["video_id"], llm)

    structured = await asyncio.to_thread(_structure)

    # Use structured text for storage, fall back to raw if structuring failed
    if structured.get("structured"):
        text = structured_text_from_result(structured)
        title = data.title or structured.get("title") or f"YouTube {result['video_id']}"
    else:
        text = raw_text
        title = data.title or f"YouTube {result['video_id']}"

    podcast_id = uuid.uuid4().hex[:10]
    safe_name = _sanitize_filename(title)
    dest_dir = PROJECT_ROOT / "data" / "founders" / data.founder_slug / "podcast-data"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"{podcast_id}_{safe_name}.txt"
    dest_file.write_text(text, encoding="utf-8")

    # Also save the structured JSON alongside for rich UI display
    if structured.get("structured"):
        json_file = dest_dir / f"{podcast_id}_{safe_name}.json"
        json_file.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")

    db.insert_podcast(
        podcast_id=podcast_id,
        founder_slug=data.founder_slug,
        title=title,
        host=data.host,
        episode_url=data.youtube_url,
        source_type="youtube",
        youtube_url=data.youtube_url,
        transcript_path=str(dest_file),
        transcript_length=len(text),
        date=data.date,
        notes=structured.get("summary", ""),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    return {
        "podcast_id": podcast_id,
        "title": title,
        "transcript_length": len(text),
        "video_id": result["video_id"],
        "structured": structured.get("structured", False),
        "summary": structured.get("summary", ""),
        "speakers": structured.get("speakers", []),
        "segments_count": len(structured.get("segments", [])),
    }


@blog_router.post("/api/studio/podcasts/paste")
async def paste_podcast_transcript(data: PasteTranscriptRequest):
    """Save a pasted transcript."""
    from src.blog import db
    db.init_db()

    if not data.text.strip():
        raise HTTPException(status_code=400, detail="Empty transcript text")

    podcast_id = uuid.uuid4().hex[:10]
    safe_name = _sanitize_filename(data.title)
    dest_dir = PROJECT_ROOT / "data" / "founders" / data.founder_slug / "podcast-data"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"{podcast_id}_{safe_name}.txt"
    dest_file.write_text(data.text, encoding="utf-8")

    db.insert_podcast(
        podcast_id=podcast_id,
        founder_slug=data.founder_slug,
        title=data.title,
        host=data.host,
        episode_url="",
        source_type="paste",
        youtube_url="",
        transcript_path=str(dest_file),
        transcript_length=len(data.text),
        date=data.date,
        notes="",
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    return {"podcast_id": podcast_id, "title": data.title, "transcript_length": len(data.text)}


@blog_router.get("/api/studio/podcasts/{founder_slug}")
async def list_podcasts_endpoint(founder_slug: str):
    """List all podcasts for a founder."""
    from src.blog import db
    db.init_db()
    return {"podcasts": db.list_podcasts(founder_slug)}


@blog_router.get("/api/studio/podcasts/{podcast_id}/transcript")
async def get_podcast_transcript(podcast_id: str):
    """Return the full transcript text for a podcast."""
    from src.blog import db
    from pathlib import Path as _Path
    db.init_db()
    pod = db.get_podcast(podcast_id)
    if not pod:
        raise HTTPException(status_code=404, detail="Podcast not found")
    p = _Path(pod["transcript_path"])
    if not p.exists():
        raise HTTPException(status_code=404, detail="Transcript file not found")
    text = p.read_text(encoding="utf-8", errors="replace")
    structured = None
    json_path = p.with_suffix(".json")
    if json_path.exists():
        try:
            structured = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"podcast_id": podcast_id, "text": text, "structured": structured}


@blog_router.delete("/api/studio/podcasts/{podcast_id}")
async def delete_podcast_endpoint(podcast_id: str):
    """Delete a podcast and its transcript file."""
    from src.blog import db
    db.init_db()
    ok = db.delete_podcast(podcast_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Podcast not found")
    return {"deleted": True}


# ── Document Category Management ────────────────────────────────────────

@blog_router.post("/api/studio/categories")
async def create_category_endpoint(data: CreateCategoryRequest):
    """Create a new document category."""
    from src.blog import db
    db.init_db()

    category_id = uuid.uuid4().hex[:10]
    try:
        db.insert_category(
            category_id=category_id,
            founder_slug=data.founder_slug,
            name=data.name,
            description=data.description,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail=f"Category '{data.name}' already exists")
        raise

    return {"category_id": category_id, "name": data.name}


@blog_router.get("/api/studio/categories/{founder_slug}")
async def list_categories_endpoint(founder_slug: str):
    """List document categories for a founder."""
    from src.blog import db
    db.init_db()
    return {"categories": db.list_categories(founder_slug)}


@blog_router.put("/api/studio/categories/{category_id}")
async def update_category_endpoint(category_id: str, data: UpdateCategoryRequest):
    """Update a category name/description."""
    from src.blog import db
    db.init_db()
    ok = db.update_category(category_id, data.name, data.description)
    if not ok:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"updated": True}


@blog_router.delete("/api/studio/categories/{category_id}")
async def delete_category_endpoint(category_id: str):
    """Delete a category (orphans its documents)."""
    from src.blog import db
    db.init_db()
    ok = db.delete_category(category_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"deleted": True}


# ── Studio Document Management ──────────────────────────────────────────

@blog_router.post("/api/studio/documents/upload")
async def upload_studio_document(
    file: UploadFile = File(...),
    founder_slug: str = Form(...),
    category_id: str = Form(""),
):
    """Upload a source document for blog generation."""
    from src.blog import db
    db.init_db()

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = Path(file.filename).suffix.lower()
    supported = {".txt", ".md", ".docx", ".xlsx", ".xls", ".csv", ".pdf", ".json", ".yaml", ".yml"}
    if suffix not in supported:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    document_id = uuid.uuid4().hex[:10]
    dest_dir = PROJECT_ROOT / "data" / "founders" / founder_slug / "studio-docs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"{document_id}_{file.filename}"

    content = await file.read()
    dest_file.write_bytes(content)

    text = ""
    file_type = suffix.lstrip(".")

    if suffix in (".txt", ".md"):
        text = dest_file.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".docx":
        from src.ingestion.docx_reader import read_docx
        doc = read_docx(dest_file)
        text = doc.get("plain_text", "")
    elif suffix in (".xlsx", ".xls"):
        from src.ingestion.xlsx_reader import read_xlsx
        sheets = read_xlsx(dest_file)
        parts = []
        for sheet in sheets:
            for row in sheet["rows"]:
                for v in row.values():
                    if isinstance(v, str) and len(v) > 20:
                        parts.append(v)
        text = "\n\n".join(parts)
    elif suffix == ".csv":
        import csv as csv_mod
        with dest_file.open(encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv_mod.reader(f))
        text = "\n".join(",".join(r) for r in rows)
    elif suffix == ".pdf":
        from src.blog.pdf_reader import read_pdf
        pdf = read_pdf(dest_file)
        text = pdf.get("plain_text", "")
    elif suffix in (".json", ".yaml", ".yml"):
        text = dest_file.read_text(encoding="utf-8", errors="replace")

    cat_id = category_id if category_id else None

    db.insert_document(
        document_id=document_id,
        founder_slug=founder_slug,
        category_id=cat_id,
        filename=file.filename,
        file_path=str(dest_file),
        file_type=file_type,
        file_size=len(content),
        text_content=text,
        text_length=len(text),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    return {"document_id": document_id, "filename": file.filename, "text_length": len(text)}


@blog_router.get("/api/studio/documents/{founder_slug}")
async def list_documents_endpoint(founder_slug: str, category_id: str = Query(default="")):
    """List documents for a founder, optionally filtered by category."""
    from src.blog import db
    db.init_db()
    cat = category_id if category_id else None
    return {"documents": db.list_documents(founder_slug, cat)}


@blog_router.put("/api/studio/documents/{document_id}/category")
async def update_document_category_endpoint(document_id: str, data: UpdateDocCategoryRequest):
    """Move a document to a different category."""
    from src.blog import db
    db.init_db()
    ok = db.update_document_category(document_id, data.category_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"updated": True}


@blog_router.delete("/api/studio/documents/{document_id}")
async def delete_document_endpoint(document_id: str):
    """Delete a document and its file."""
    from src.blog import db
    db.init_db()
    ok = db.delete_document(document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True}
