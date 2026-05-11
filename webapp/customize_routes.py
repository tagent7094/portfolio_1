"""Post customizer routes — blend selected opener with post body via LLM stream."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

customize_router = APIRouter()


class CustomizePostRequest(BaseModel):
    original_post: str
    selected_opener: str
    variant_letter: str = "A"
    founder_slug: str = ""
    voice_markers: str = ""
    api_key: str = ""
    effort: str = "high"


class CustomizeChatRequest(BaseModel):
    current_post: str
    message: str
    founder_slug: str = ""
    voice_markers: str = ""
    api_key: str = ""
    effort: str = "medium"


BLEND_SYSTEM = """You are a LinkedIn post editor for a B2B founder. Your job:

1. KEEP the selected opening line EXACTLY as provided — do not change a single word.
2. Adapt the body paragraphs so they flow naturally from this new opener.
3. Preserve the founder's voice markers: {voice_markers}
4. Keep roughly the same post length (±10%).
5. Do NOT add hashtags, emojis, or calls-to-action unless the original had them.
6. Return ONLY the final post text — no commentary, no labels, no explanation."""

CHAT_SYSTEM = """You are editing a LinkedIn post for a B2B founder. Apply the user's requested change while preserving voice and structure. The founder's voice markers: {voice_markers}

Return ONLY the updated post text — no commentary, no labels, no explanation."""


@customize_router.post("/api/customize-post")
async def customize_post(data: CustomizePostRequest):
    if not data.api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    if not data.original_post or not data.selected_opener:
        raise HTTPException(status_code=400, detail="Post and opener are required")

    import anthropic

    client = anthropic.Anthropic(api_key=data.api_key)
    system = BLEND_SYSTEM.format(voice_markers=data.voice_markers or "none provided")

    user_msg = (
        f"## SELECTED OPENING LINE (keep exactly as-is)\n{data.selected_opener}\n\n"
        f"## ORIGINAL POST (body to adapt)\n{data.original_post}\n\n"
        f"## VARIANT\n{data.variant_letter}\n\n"
        "Now produce the final blended post."
    )

    kwargs: dict = dict(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    if data.effort in ("low", "medium", "high"):
        kwargs["output_config"] = {"effort": data.effort}

    async def generate():
        full_text = []
        try:
            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    full_text.append(text)
                    yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'full_text': ''.join(full_text)})}\n\n"
        except anthropic.AuthenticationError:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Invalid API key'})}\n\n"
        except anthropic.RateLimitError:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Rate limit exceeded'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@customize_router.post("/api/customize-chat")
async def customize_chat(data: CustomizeChatRequest):
    if not data.api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    if not data.current_post or not data.message:
        raise HTTPException(status_code=400, detail="Post and message are required")

    import anthropic

    client = anthropic.Anthropic(api_key=data.api_key)
    system = CHAT_SYSTEM.format(voice_markers=data.voice_markers or "none provided")

    user_msg = (
        f"## CURRENT POST\n{data.current_post}\n\n"
        f"## EDIT INSTRUCTION\n{data.message}\n\n"
        "Apply the edit and return the full updated post."
    )

    kwargs: dict = dict(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    if data.effort in ("low", "medium", "high"):
        kwargs["output_config"] = {"effort": data.effort}

    async def generate():
        full_text = []
        try:
            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    full_text.append(text)
                    yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'full_text': ''.join(full_text)})}\n\n"
        except anthropic.AuthenticationError:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Invalid API key'})}\n\n"
        except anthropic.RateLimitError:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Rate limit exceeded'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
