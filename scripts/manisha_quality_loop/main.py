"""Top-level orchestrator for the Manisha Batch A iterative quality loop.

Runs up to 10 iterations of generate → audit → diagnose → tweak,
saving artifacts per iteration and writing a final report.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

from src.batch.state import AmplifiedPost, BatchState
from src.batch.corpus_reader import (
    load_founder_state,
    internalize_corpus,
    calibration_check,
)
from src.batch.pack_generator import dissect_source, verify_opener_tests
from src.batch.tracer import BatchTracer
from src.llm.task_router import LLMRouter

from .runner import generate_batch_a
from .auditor import audit_pack
from .diagnoser import diagnose_failures, find_worst_unfixed_parameter
from .tweaker import (
    PROMPT_FILE,
    BACKUP_FILE,
    apply_tweak,
    save_preloop_backup,
    restore_preloop_backup,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("quality_loop")

# Configuration
LOOP_CONFIG = {
    "founder_slug": "manisha",
    "platform": "linkedin",
    "source_post_path": "data/quality-loop/chris_degnan_source.txt",
    "output_dir": "data/founders/manisha/quality-loop",
    "max_iterations": 10,
    "target_avg_score": 9.5,
    "regression_stop_threshold": 2,
}

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_source() -> str:
    return (REPO_ROOT / LOOP_CONFIG["source_post_path"]).read_text(encoding="utf-8")


def _output_dir() -> Path:
    p = REPO_ROOT / LOOP_CONFIG["output_dir"]
    p.mkdir(parents=True, exist_ok=True)
    return p


def _iteration_dir(n: int) -> Path:
    p = _output_dir() / f"iteration_{n}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _post_to_dict(p: AmplifiedPost) -> dict:
    return {
        "label": p.label,
        "batch": p.batch,
        "entry_door": p.entry_door,
        "mode": p.mode,
        "text": p.text,
        "word_count": p.word_count,
        "original_opening": p.original_opening,
        "final_opening": p.final_opening,
        "mechanic": p.mechanic,
        "actual_mechanic": p.actual_mechanic,
        "gates": p.gates,
        "rating": p.rating,
        "buried_gold": p.buried_gold,
        "weakness": p.weakness,
        "recommended_variant": p.recommended_variant,
        "voice_score": p.voice_score,
        "validation_result": p.validation_result,
        "quality_flags": p.quality_flags,
        "regen_count": p.regen_count,
        "argument_compressed": p.argument_compressed,
    }


def _save_iteration_artifacts(
    n: int,
    posts: list[AmplifiedPost],
    audit: dict,
    diagnoses: list[dict],
    tweak_decision: dict,
    posts_kept: list[str],
    duration_s: float,
) -> None:
    """Write all 7 artifact files for the iteration."""
    d = _iteration_dir(n)

    # posts.json
    (d / "posts.json").write_text(
        json.dumps([_post_to_dict(p) for p in posts], indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    # scores.json
    (d / "scores.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    # audit_reasoning.md
    lines = [f"# Iteration {n} — Audit Reasoning\n",
             f"Pack avg: **{audit['pack_avg']:.2f}/10**, all_pass: **{audit['all_pass']}**",
             f"Unique posts: {audit['unique_post_count']}/3\n"]
    for post_audit in audit["per_post"]:
        lines.append(f"\n## {post_audit['label']} — avg {post_audit['avg']:.2f}, failing: {post_audit['failing']}")
        for k in ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"]:
            cell = post_audit.get(k, {})
            lines.append(f"- **{k}**: {cell.get('score', '?')}/10 — {cell.get('reason', '')}")
    (d / "audit_reasoning.md").write_text("\n".join(lines), encoding="utf-8")

    # root_cause.md
    rc_lines = [f"# Iteration {n} — Root Cause Diagnoses\n"]
    if diagnoses:
        for diag in diagnoses:
            rc_lines.append(
                f"## {diag['param']} (current avg: {diag['current_score']:.1f}/10)\n"
                f"- **Root cause**: {diag['root_cause']}\n"
                f"- **Fix location**: {diag['fix_location']}\n"
                f"- **Trajectory**: {diag['trajectory']}\n"
            )
    else:
        rc_lines.append("All parameters passing.\n")
    (d / "root_cause.md").write_text("\n".join(rc_lines), encoding="utf-8")

    # prompt_diff.md
    pd_lines = [f"# Iteration {n} — Prompt Tweak\n"]
    if tweak_decision:
        pd_lines.append(f"- **Parameter targeted**: {tweak_decision.get('param', '-')}\n"
                        f"- **Status**: {tweak_decision.get('status', '-')}\n"
                        f"- **Summary**: {tweak_decision.get('summary', '-')}\n")
    else:
        pd_lines.append("No tweak applied this iteration.\n")
    (d / "prompt_diff.md").write_text("\n".join(pd_lines), encoding="utf-8")

    # regen_decision.md
    regen_lines = [f"# Iteration {n} — Regeneration Decisions\n",
                   f"Posts carried forward (passing all 10): {posts_kept or 'none'}\n",
                   f"Posts regenerated this iteration: {[p.label for p in posts if p.label not in posts_kept]}\n"]
    (d / "regen_decision.md").write_text("\n".join(regen_lines), encoding="utf-8")

    # cost_and_time.json (rough estimate)
    n_llm_calls = (
        3 +  # transpose A (or partial)
        1 +  # amplify_batch_v2
        12   # audit judges (3 posts × 4 LLM params)
    )
    est_cost = n_llm_calls * 0.005  # conservative Haiku estimate
    (d / "cost_and_time.json").write_text(
        json.dumps({
            "iteration": n,
            "duration_seconds": round(duration_s, 2),
            "estimated_llm_calls": n_llm_calls,
            "estimated_usd": round(est_cost, 4),
        }, indent=2),
        encoding="utf-8",
    )


def _write_final_report(history: list[dict], tweaks_applied: list[str], final_posts, total_duration: float) -> None:
    d = _output_dir()
    lines: list[str] = []
    lines.append("# Manisha Batch A Quality Loop — Final Report\n")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"Iterations run: {len(history)}\n")
    lines.append(f"Total duration: {total_duration:.1f}s\n")
    lines.append(f"Tweaks applied (in order): {tweaks_applied}\n")
    lines.append("\n## Iteration Trajectory\n")
    lines.append("| N | Avg | All Pass | Unique | Tweak Applied |")
    lines.append("|---|---|---|---|---|")
    for i, it in enumerate(history, 1):
        audit = it["audit"]
        lines.append(
            f"| {i} | {audit['pack_avg']:.2f} | {audit['all_pass']} | "
            f"{audit['unique_post_count']}/3 | {it.get('tweak', '-')} |"
        )

    lines.append("\n## Final 3 Batch A Posts\n")
    for p in (final_posts or []):
        lines.append(f"\n### {p.label} (avg {next((a['avg'] for it in history for a in it['audit']['per_post'] if a['label'] == p.label), 0):.2f}/10)\n")
        lines.append(f"**Mechanic**: {p.mechanic} (actual: {p.actual_mechanic})  ")
        lines.append(f"**Word count**: {p.word_count}\n")
        lines.append(f"```\n{p.text}\n```")

    lines.append("\n## Final Score Matrix (last iteration)\n")
    if history:
        last_audit = history[-1]["audit"]
        lines.append("| Post | " + " | ".join(f"P{i}" for i in range(1, 11)) + " | Avg |")
        lines.append("|" + "---|" * 12)
        for post_audit in last_audit["per_post"]:
            row = [post_audit["label"]] + [
                str(post_audit.get(f"P{i}", {}).get("score", "-"))
                for i in range(1, 11)
            ] + [f"{post_audit['avg']:.2f}"]
            lines.append("| " + " | ".join(row) + " |")

    lines.append("\n## Persistent Failures\n")
    if history:
        last_audit = history[-1]["audit"]
        failing_in_final = set()
        for post_audit in last_audit["per_post"]:
            for k in post_audit.get("failing", []):
                failing_in_final.add(k)
        if failing_in_final:
            lines.append(f"Parameters that did not reach 9/10 across all posts in final iteration: {sorted(failing_in_final)}\n")
            lines.append("These may need founder card enrichment, framework changes, or threshold review.\n")
        else:
            lines.append("None — all parameters passing in the final iteration.\n")

    lines.append("\n## Recommendation\n")
    if history and history[-1]["audit"]["all_pass"]:
        lines.append(f"**Promote** iteration {len(history)}'s prompt state to production.\n")
        lines.append(f"Source: {BACKUP_FILE} contains pre-loop state. Compare against current `{PROMPT_FILE}` for the diff to ship.\n")
    else:
        lines.append("**Do NOT auto-promote**. Loop did not converge to 10/10. Review persistent failures.\n")
        lines.append(f"Prompt has been restored to pre-loop state from `{BACKUP_FILE}`.\n")

    (d / "final_report.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("[loop] Final report written to %s", d / "final_report.md")


def setup_state() -> tuple[BatchState, str, dict, object, object]:
    """One-time setup: load founder state, internalize, dissect source."""
    router = LLMRouter(config_path="config/llm-config.yaml", founder_slug=LOOP_CONFIG["founder_slug"])
    llm_gen = router.for_task("generate_a")
    llm_prep = router.for_task("dissect")
    llm_judge = router.for_task("voice_validation")  # Haiku — repurposed for judging

    # Disable thinking and lower effort across all LLM instances for loop speed.
    # Iteration speed > per-call depth here; we'll evaluate ~10 iterations to
    # spot prompt-evolution signal, not produce a single perfect output.
    for _llm in (llm_gen, llm_prep, llm_judge):
        if hasattr(_llm, "enable_thinking"):
            _llm.enable_thinking = False
        if hasattr(_llm, "effort"):
            _llm.effort = "medium"

    logger.info("[loop] Loading founder state for %s...", LOOP_CONFIG["founder_slug"])
    state = load_founder_state(LOOP_CONFIG["founder_slug"], LOOP_CONFIG["platform"])
    state.tracer = BatchTracer(
        model=getattr(llm_gen, "_model_name", "unknown"),
        provider=getattr(llm_gen, "_provider_name", "unknown"),
    )
    state.llm_router = router

    logger.info("[loop] Internalizing corpus...")
    intern = internalize_corpus(llm_gen, state)
    state.founder_internalization = intern
    state.voice_markers = intern.get("voice_markers", [])
    state.formatting_habits = intern.get("formatting_habits", {})
    if intern.get("word_count_range"):
        wc = intern["word_count_range"]
        if isinstance(wc, list) and len(wc) == 2:
            state.word_count_range = (min(int(wc[0]), int(wc[1])), max(int(wc[0]), int(wc[1])))
    if intern.get("median_word_count"):
        state.median_word_count = int(intern["median_word_count"])

    logger.info("[loop] Running calibration check...")
    cal = calibration_check(llm_gen, state)
    state.calibration_paragraph = cal.get("calibration_paragraph", "")

    source = _load_source()
    logger.info("[loop] Dissecting source post (%d chars)...", len(source))
    dissection = dissect_source(llm_prep, source, state, pack_num=0)
    dissection = verify_opener_tests(dissection)

    return state, source, dissection, llm_gen, llm_judge


def run_loop() -> None:
    save_preloop_backup()

    state, source, dissection, llm_gen, llm_judge = setup_state()

    history: list[dict] = []
    posts_keep: list[tuple[str, AmplifiedPost]] = []
    tweaks_applied: set[str] = set()
    last_posts: list[AmplifiedPost] = []

    t0 = time.time()
    for n in range(1, LOOP_CONFIG["max_iterations"] + 1):
        iter_t0 = time.time()
        logger.info("[loop] === Iteration %d ===", n)

        posts = generate_batch_a(
            state, source, dissection, llm_gen,
            posts_to_keep=posts_keep, pack_number=n,
        )
        last_posts = posts

        audit = audit_pack(posts, source, dissection, state, llm_judge)
        logger.info(
            "[loop] Iter %d: avg=%.2f, all_pass=%s, unique=%d/3",
            n, audit["pack_avg"], audit["all_pass"], audit["unique_post_count"],
        )

        diagnoses = diagnose_failures(audit, history, tweaks_applied)

        # Success check
        success = (
            audit["all_pass"]
            and audit["pack_avg"] >= LOOP_CONFIG["target_avg_score"]
            and audit["unique_post_count"] == 3
        )

        # Determine tweak (only if not done)
        tweak_decision: dict = {}
        if not success:
            worst = find_worst_unfixed_parameter(audit, tweaks_applied)
            if worst:
                tweak_decision = apply_tweak(worst)
                tweaks_applied.add(worst)
                logger.info("[loop] Iter %d: tweaked %s — %s", n, worst, tweak_decision.get("summary", ""))
            else:
                logger.warning("[loop] Iter %d: no unfixed parameters left to tweak", n)

        # Determine carry-forward set
        kept_labels = [a["label"] for a in audit["per_post"] if a["all_pass"]]
        posts_keep = [(a["label"], p) for a, p in zip(audit["per_post"], posts) if a["all_pass"]]

        duration = time.time() - iter_t0
        _save_iteration_artifacts(
            n, posts, audit, diagnoses, tweak_decision, kept_labels, duration,
        )

        history.append({
            "N": n,
            "audit": audit,
            "tweak": tweak_decision.get("param", "-") if tweak_decision else "-",
        })

        if success:
            logger.info("[loop] SUCCESS at iteration %d — all 3 posts ≥9 on all 10 params", n)
            break

        # Regression check: 2 consecutive avg drops → revert + stop
        if len(history) >= 3:
            recent = [h["audit"]["pack_avg"] for h in history[-3:]]
            if recent[-1] < recent[-2] < recent[-3]:
                logger.warning(
                    "[loop] 2 consecutive avg regressions (%.2f → %.2f → %.2f) — restoring pre-loop prompt and stopping",
                    recent[-3], recent[-2], recent[-1],
                )
                restore_preloop_backup()
                break

        # All tweaks exhausted
        if not tweak_decision and not success:
            logger.warning("[loop] All tweaks exhausted, stopping at iter %d", n)
            break

    total = time.time() - t0

    # If loop did NOT succeed, restore the production prompt.
    if not history or not history[-1]["audit"]["all_pass"]:
        logger.info("[loop] Loop did not converge — restoring pre-loop prompt")
        restore_preloop_backup()

    _write_final_report(history, sorted(tweaks_applied), last_posts, total)


if __name__ == "__main__":
    run_loop()
