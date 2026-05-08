"""Full traceability for batch pipeline — captures every LLM call, web search, and decision."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict


@dataclass
class TraceEntry:
    id: str
    timestamp: float
    type: str                  # "llm_call", "web_search", "decision", "step"
    stage: str                 # e.g. "internalize", "pack_3_b2", "amplifier_diagnose"
    template: str = ""         # prompt template filename
    prompt_preview: str = ""   # first 500 chars of rendered prompt
    prompt_length: int = 0     # full prompt char count
    response_preview: str = "" # first 500 chars of response
    response_length: int = 0   # full response char count
    temperature: float = 0.0
    max_tokens: int = 0
    model: str = ""
    provider: str = ""
    duration_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    search_query: str = ""
    search_results: list = field(default_factory=list)
    decision: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("id", None)
        return {"id": self.id, **d}


class BatchTracer:
    """Collects trace entries across the entire batch pipeline run."""

    def __init__(self, model: str = "", provider: str = ""):
        self.model = model
        self.provider = provider
        self.entries: list[TraceEntry] = []
        self._active_spans: dict[str, float] = {}

    def start_span(self, span_id: str) -> str:
        self._active_spans[span_id] = time.time()
        return span_id

    def end_span(self, span_id: str) -> int:
        start = self._active_spans.pop(span_id, time.time())
        return int((time.time() - start) * 1000)

    def trace_llm_call(
        self,
        stage: str,
        template: str,
        prompt: str,
        response: str,
        temperature: float = 0.0,
        max_tokens: int = 0,
        duration_ms: int = 0,
        metadata: dict | None = None,
    ) -> TraceEntry:
        entry = TraceEntry(
            id=f"llm_{uuid.uuid4().hex[:8]}",
            timestamp=time.time(),
            type="llm_call",
            stage=stage,
            template=template,
            prompt_preview=prompt[:500],
            prompt_length=len(prompt),
            response_preview=response[:500],
            response_length=len(response),
            temperature=temperature,
            max_tokens=max_tokens,
            model=self.model,
            provider=self.provider,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self.entries.append(entry)
        return entry

    def trace_web_search(
        self,
        stage: str,
        query: str,
        results: list[dict],
        duration_ms: int = 0,
    ) -> TraceEntry:
        entry = TraceEntry(
            id=f"ws_{uuid.uuid4().hex[:8]}",
            timestamp=time.time(),
            type="web_search",
            stage=stage,
            search_query=query,
            search_results=results,
            model=self.model,
            provider=self.provider,
            duration_ms=duration_ms,
        )
        self.entries.append(entry)
        return entry

    def trace_decision(
        self,
        stage: str,
        decision: str,
        metadata: dict | None = None,
    ) -> TraceEntry:
        entry = TraceEntry(
            id=f"dec_{uuid.uuid4().hex[:8]}",
            timestamp=time.time(),
            type="decision",
            stage=stage,
            decision=decision,
            metadata=metadata or {},
        )
        self.entries.append(entry)
        return entry

    def trace_step(
        self,
        stage: str,
        description: str,
        duration_ms: int = 0,
        metadata: dict | None = None,
    ) -> TraceEntry:
        entry = TraceEntry(
            id=f"step_{uuid.uuid4().hex[:8]}",
            timestamp=time.time(),
            type="step",
            stage=stage,
            decision=description,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self.entries.append(entry)
        return entry

    def get_summary(self) -> dict:
        llm_calls = [e for e in self.entries if e.type == "llm_call"]
        searches = [e for e in self.entries if e.type == "web_search"]
        decisions = [e for e in self.entries if e.type == "decision"]
        total_duration = sum(e.duration_ms for e in self.entries)
        return {
            "total_traces": len(self.entries),
            "llm_calls": len(llm_calls),
            "web_searches": len(searches),
            "decisions": len(decisions),
            "total_duration_ms": total_duration,
            "total_prompt_chars": sum(e.prompt_length for e in llm_calls),
            "total_response_chars": sum(e.response_length for e in llm_calls),
            "templates_used": sorted(set(e.template for e in llm_calls if e.template)),
            "model": self.model,
            "provider": self.provider,
        }

    def to_list(self) -> list[dict]:
        return [e.to_dict() for e in self.entries]
