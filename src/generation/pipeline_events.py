"""SSE event bus for real-time pipeline progress streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PipelineEvent:
    """A single pipeline progress event."""

    stage: str        # generate_all_posts, audience_vote, refine, humanize, quality_gate, done
    status: str       # started, progress, completed, pipeline_done
    data: dict = field(default_factory=dict)
    progress: float = 0.0  # 0.0 to 1.0
    agent_id: str = ""     # which agent is working (for voting stage)


class PipelineEventBus:
    """Thread-safe event bus backed by asyncio.Queue for SSE streaming."""

    def __init__(self):
        self._queue: asyncio.Queue[PipelineEvent] = asyncio.Queue()
        self._closed = False

    def emit(self, event: PipelineEvent):
        """Emit an event (thread-safe via put_nowait)."""
        if not self._closed:
            try:
                self._queue.put_nowait(event)
            except Exception:
                logger.warning("Failed to emit event: %s", event.stage)

    def emit_simple(self, stage: str, status: str, data: dict | None = None, progress: float = 0.0, agent_id: str = ""):
        """Convenience method to emit without constructing PipelineEvent."""
        self.emit(PipelineEvent(
            stage=stage,
            status=status,
            data=data or {},
            progress=progress,
            agent_id=agent_id,
        ))

    async def stream(self):
        """Async generator yielding SSE-formatted strings."""
        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=300)
            except asyncio.TimeoutError:
                # Send keepalive
                yield ": keepalive\n\n"
                continue

            event_dict = asdict(event)
            yield f"data: {json.dumps(event_dict)}\n\n"

            if event.status == "pipeline_done":
                self._closed = True
                break

    def close(self):
        """Force-close the bus."""
        self._closed = True
        self.emit(PipelineEvent(stage="done", status="pipeline_done"))
