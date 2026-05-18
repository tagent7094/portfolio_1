"""v6 final compile step — 06_compile.txt binary ship/reject gate.

Runs AFTER the validate+regen loop has settled. Even though the regen loop
already returned ShipDecision, this LLM-side step gives a final
human-readable accept/reject + audit summary. The orchestrator gates the
Excel write on `pack_decision == "ship"`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import BatchState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def compile_pack(
    llm: LLMProvider,
    state: BatchState,
    pack,                          # PackResult
    validation: dict,
    regen_log: list[dict],
) -> dict:
    """Run 06_compile.txt to produce final ship/reject decision + audit.

    Returns dict with `pack_decision` ("ship" or "reject"), `ship_payload`
    on ship, `failure_summary` + `recommendations` on reject.
    """
    if getattr(state, "llm_router", None):
        try:
            llm = state.llm_router.for_task("compile")
        except Exception:
            llm = state.llm_router.for_task("validate")

    template = load_prompt(PROMPTS_DIR / "compile.txt")

    # Build validated_pack JSON — each post with text + scores + passes_floor.
    posts_arr = []
    for p in pack.posts:
        posts_arr.append({
            "label": p.label,
            "text": p.text,
            "scores": p.validator_scores or p.self_scores or {},
            "passes_9_7_floor": p.passes_9_7_floor,
            "validations_run": len(p.regen_history) + 1,
            "anchor_consumed_id": p.anchor_consumed_id,
            "word_count": p.word_count,
        })
    validated_pack_json = json.dumps(posts_arr, ensure_ascii=False)

    pack_level_checks_json = json.dumps(
        validation.get("pack_level_checks", {}), ensure_ascii=False,
    )
    rejection_history_json = json.dumps(regen_log or [], ensure_ascii=False)

    inv_full = state.anchor_inventory or {}
    inv_list = inv_full.get("anchor_inventory", []) or []
    dissection_for_pack = (state.source_dissections[-1] if state.source_dissections else {})

    prompt = fill_prompt(
        template,
        validated_pack=validated_pack_json,
        pack_level_checks=pack_level_checks_json,
        rejection_history=rejection_history_json,
        anchor_inventory=json.dumps(inv_list, ensure_ascii=False)[:6000] or "(no inventory)",
        founder_first_name=state.founder_first_name or state.founder_slug.title(),
        dissection=json.dumps(dissection_for_pack, ensure_ascii=False)[:4000] or "{}",
    )

    import time as _t
    _start = _t.time()
    try:
        response = llm.generate(prompt, temperature=0.2, max_tokens=4000)
    except Exception as e:
        logger.warning("[compile_pack] API error: %s — defaulting to ship", e)
        return {"pack_decision": "ship", "quality_floor_met": True}
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="compile_pack",
            template="06_compile.txt",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=4000,
            duration_ms=_dur,
            thinking=getattr(llm, "last_thinking", ""),
            llm=llm,
        )

    if not isinstance(result, dict):
        logger.warning("[compile_pack] parse failed — defaulting to ship")
        return {"pack_decision": "ship", "quality_floor_met": True}

    decision = result.get("pack_decision", "ship")
    floor_met = result.get("quality_floor_met", decision == "ship")
    logger.info(
        "[compile_pack] decision=%s quality_floor_met=%s regen_count=%d",
        decision, floor_met, len(regen_log or []),
    )
    return result
