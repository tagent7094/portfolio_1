"""v6 validation-regen loop — the critical FAIL enforcement.

Per ORCHESTRATOR_SPEC §3. This is the change that closes v5.1's ceiling
problem (validator marked posts FAIL but orchestrator shipped anyway).

`run_validation_regen_loop` calls the validator, and if any post fails the
9.7+ floor, regenerates that post (up to MAX_REGEN_ATTEMPTS_PER_POST times)
using the validator's `explicit_regen_instructions`. Returns ShipDecision
indicating whether the pack qualifies for ship.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

MAX_REGEN_ATTEMPTS_PER_POST = 3
MAX_TOTAL_REGENS_PER_PACK = 10  # pack-level cost ceiling


def _empty_instructions() -> dict:
    """The canonical empty shape of explicit_regen_instructions."""
    return {
        "explicit_avoid": [],
        "required_sub_mechanic": "",
        "anchor_to_use": "",
        "fallback_strategy": "",
        "regenerate_with_mechanic": "",
    }


def safe_get_regen_instructions(raw) -> dict:
    """v6.1 bulletproof coercion of `explicit_regen_instructions` to a dict.

    Per ORCHESTRATOR_SPEC §"Fix the regen loop crash" — accepts None/str/list/dict
    and always returns a dict with the 5 expected keys (empty strings/lists
    where not provided). The prompt forbids non-dict shapes but a model may
    still misbehave; defensive coercion prevents AttributeError crashes like
    the one v6 hit on the Manisha/Alok $18K run.
    """
    if raw is None:
        return _empty_instructions()
    if isinstance(raw, str):
        # Validator returned a string instead of dict — wrap as fallback strategy.
        return {
            "explicit_avoid": [raw],
            "required_sub_mechanic": "",
            "anchor_to_use": "",
            "fallback_strategy": raw,
            "regenerate_with_mechanic": "",
        }
    if isinstance(raw, list):
        # Validator returned a list — assume it's the explicit_avoid items.
        return {
            "explicit_avoid": [str(x) for x in raw],
            "required_sub_mechanic": "",
            "anchor_to_use": "",
            "fallback_strategy": "",
            "regenerate_with_mechanic": "",
        }
    if isinstance(raw, dict):
        # Normal case — ensure all 5 expected keys exist + coerce avoid items.
        avoid_raw = raw.get("explicit_avoid", []) or []
        avoid: list[str] = []
        for item in avoid_raw:
            if isinstance(item, str):
                avoid.append(item)
            elif isinstance(item, dict):
                text = item.get("instruction") or item.get("avoid") or json.dumps(item, ensure_ascii=False)
                avoid.append(text)
            else:
                avoid.append(str(item))
        return {
            "explicit_avoid": avoid,
            "required_sub_mechanic": str(raw.get("required_sub_mechanic", "") or ""),
            "anchor_to_use": str(raw.get("anchor_to_use", "") or ""),
            "fallback_strategy": str(raw.get("fallback_strategy", "") or ""),
            "regenerate_with_mechanic": str(raw.get("regenerate_with_mechanic", "") or ""),
        }
    # Unknown type — return empty + record what we saw.
    return {
        "explicit_avoid": [],
        "required_sub_mechanic": "",
        "anchor_to_use": "",
        "fallback_strategy": f"Unexpected type from validator: {type(raw).__name__}",
        "regenerate_with_mechanic": "",
    }


@dataclass
class ShipDecision:
    """Return value of `run_validation_regen_loop`.

    `ship=True` means every post passed the 9.7+ floor; caller proceeds to
    compile + Excel write. `ship=False` means at least one post exhausted
    its regen budget; caller writes a rejection report instead of Excel.
    """
    ship: bool
    pack: object | None = None       # PackResult — kept typed loose to avoid import cycle
    rejection_reason: str = ""
    detailed_failures: dict = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    total_regens_used: int = 0


def generate_recommendations(validation: dict) -> list[str]:
    """v6 recommendations generator. Per ORCHESTRATOR_SPEC §5."""
    decision = validation.get("pack_decision", {}) if isinstance(validation, dict) else {}
    cats = set(decision.get("failure_categories", []) or [])

    recs: list[str] = []
    if "fabricated_specific_numbers" in cats:
        recs.append(
            "Add 3-5 verified specific-number anchors to founder card "
            "(specific SaaS bills, customer ARRs, infrastructure costs)"
        )
    if "voice_marker_saturation" in cats:
        recs.append(
            "Founder's voice marker variety may be insufficient. "
            "Add 3-5 more distinct voice markers from corpus."
        )
    if "anchor_saturation_cross_pack" in cats or "scene_overlap" in cats:
        recs.append(
            "Top anchors have been used in recent packs. Either wait 30 days "
            "or enrich founder card with new anchors."
        )
    if "surprise_quotient_missing" in cats:
        recs.append(
            "Source may not have sufficient hook to deliver surprise. "
            "Consider a different source with stronger psychological move."
        )
    if "anchor_insufficiency" in cats:
        recs.append(
            "Anchor inventory has too few verified anchors of the required type "
            "for this source's mechanic. Either pick a different source or "
            "enrich founder card with anchors of that type."
        )
    recs.append(
        "Alternative: lower quality threshold from 9.7 to 9.0 in 06_compile.txt "
        "if you accept lower quality this pack."
    )
    return recs


def run_validation_regen_loop(
    state,                                # BatchState
    pack,                                 # PackResult
    validator_fn: Callable,               # (state, pack_posts) -> validation dict
    regenerator_fn: Callable,             # see signature below
) -> ShipDecision:
    """Main validate-regen loop.

    `validator_fn(state, pack.posts)` runs 05_validate.txt and returns the
    parsed dict (with `pack_decision.ship_or_regen_or_reject` and
    `regen_targets[]`).

    `regenerator_fn(state, post_label, regen_attempt, failed_parameters,
                    explicit_avoid, prior_attempt_text)` returns a new
    AmplifiedPost (or None on hard failure).

    Returns ShipDecision indicating whether to ship or reject the pack.
    """
    post_regen_counts: dict[str, int] = {p.label: 0 for p in pack.posts}
    total_regens = 0

    while True:
        validation = validator_fn(state, pack.posts)
        if not isinstance(validation, dict):
            logger.warning("[regen_loop] validator returned non-dict; defaulting to ship")
            return ShipDecision(ship=True, pack=pack, total_regens_used=total_regens)

        decision = validation.get("pack_decision", {}) or {}
        ship_or = decision.get("ship_or_regen_or_reject", "ship")
        quality_floor_met = bool(decision.get("quality_floor_met", False))

        # Persist the latest validator output on state for compile + audit.
        state.regen_log.append({
            "iteration": len(state.regen_log) + 1,
            "ship_or_regen_or_reject": ship_or,
            "quality_floor_met": quality_floor_met,
            "regen_targets": [t.get("label") for t in (decision.get("regen_targets") or []) if isinstance(t, dict)],
        })

        # Happy path — pack passes.
        if quality_floor_met or ship_or == "ship":
            logger.info("[regen_loop] pack passes 9.7+ floor (regens used: %d)", total_regens)
            return ShipDecision(
                ship=True, pack=pack,
                detailed_failures=validation,
                total_regens_used=total_regens,
            )

        # v6.1: Batch A mirror-integrity early reject. If 0 of 4 Batch A posts
        # match the source sub-mechanic, regens won't help — the upstream
        # dissect routing decision was wrong. Reject immediately to save
        # 3 regens × 4 posts = 12 wasted calls per ORCHESTRATOR_SPEC §4.
        #
        # EXCEPTION: when state.force_4a_5b_applied is True, the user
        # KNOWINGLY overrode skip_batch_a routing to force 4A+5B. The
        # mirror mismatch is expected and accepted; let the unfixable-Param-1
        # softening logic below ship the pack at best-effort instead of
        # rejecting it.
        pack_checks = validation.get("pack_level_checks", {}) or {}
        mirror_integrity = pack_checks.get("batch_a_mirror_integrity", {}) or {}
        a_post_count = sum(1 for p in pack.posts if getattr(p, "batch", "") == "A")
        force_override = bool(getattr(state, "force_4a_5b_applied", False))
        if (
            a_post_count > 0
            and mirror_integrity.get("matches_count", a_post_count) == 0
            and not force_override
        ):
            system_alert = mirror_integrity.get(
                "system_alert",
                "Total mirror collapse — 0/4 Batch A posts match source sub-mechanic. "
                "Upstream dissect routing produced a false positive.",
            )
            logger.warning("[regen_loop] mirror-integrity early reject: %s", system_alert)
            recs = [
                "Upstream dissect step should have routed to skip_batch_a_route_all_to_b. "
                "Check 02_dissect.txt is v6.1 with sub-mechanic granularity, and that the "
                "anchor inventory cache contains by_sub_mechanic counts.",
                *generate_recommendations(validation),
            ]
            return ShipDecision(
                ship=False, pack=None,
                rejection_reason=system_alert,
                detailed_failures=validation,
                recommendations=recs,
                total_regens_used=total_regens,
            )
        elif a_post_count > 0 and mirror_integrity.get("matches_count", a_post_count) == 0 and force_override:
            logger.warning(
                "[regen_loop] mirror collapse detected (0/%d Batch A match sub-mechanic) "
                "but force_4a_5b_applied is True — proceeding to softening logic instead "
                "of early-reject. Pack will ship at best-effort.",
                a_post_count,
            )

        # Validator says reject outright (e.g., source_fitness_check rejected upstream).
        # EXCEPTION: when force_4a_5b_applied, the reject is likely Param 1 sub-mechanic
        # mismatch — which is the user's accepted trade-off. Demote to "regen" and let
        # the unfixable-Param-1 softening logic decide. Without this demotion the pack
        # rejects before softening runs, even though force_override is set.
        if ship_or == "reject":
            force_override_flag = bool(getattr(state, "force_4a_5b_applied", False))
            if force_override_flag:
                logger.warning(
                    "[regen_loop] validator returned reject but force_4a_5b_applied is True — "
                    "demoting to regen and letting unfixable-Param-1 softening decide"
                )
                ship_or = "regen"
                # Fall through to regen_targets processing below.
            else:
                recs = generate_recommendations(validation)
                return ShipDecision(
                    ship=False, pack=None,
                    rejection_reason=decision.get("reasoning") or "Validator returned reject",
                    detailed_failures=validation,
                    recommendations=recs,
                    total_regens_used=total_regens,
                )

        regen_targets = decision.get("regen_targets", []) or []
        if not regen_targets:
            # Floor not met but no targets — probably parse drift; ship-as-warn.
            logger.warning("[regen_loop] floor not met but no regen_targets; shipping as warning")
            return ShipDecision(
                ship=True, pack=pack,
                detailed_failures=validation,
                total_regens_used=total_regens,
            )

        # USER OVERRIDE: skip regen for Batch A posts that fail Parameter 1
        # (opener mechanic mirror) ONLY because the founder has 0 anchors at
        # the required sub-mechanic. These can't be fixed by regen — the data
        # isn't there. Ship at best-effort instead of looping until rejection.
        anchor_inv = getattr(state, "anchor_inventory", {}) or {}
        inv_list = anchor_inv.get("anchor_inventory", []) or []
        unfixable_targets: list[str] = []
        for tgt in list(regen_targets):
            label = tgt.get("label", "")
            failure_reason = (tgt.get("failure_reason") or "").lower()
            if "p1" not in failure_reason and "parameter 1" not in failure_reason and "mirror" not in failure_reason:
                continue
            # Find the per_post entry to read required_sub_mechanic.
            per_post = validation.get("per_post_validation", []) or []
            required_sm = ""
            for entry in per_post:
                if isinstance(entry, dict) and entry.get("label") == label:
                    required_sm = (entry.get("required_sub_mechanic") or "").strip()
                    break
            if not required_sm:
                continue
            # Count matching anchors in inventory.
            matches = 0
            for a in inv_list:
                for sm in (a.get("supported_mechanics") or []):
                    if isinstance(sm, dict) and sm.get("sub_mechanic") == required_sm:
                        matches += 1
                        break
            if matches == 0:
                logger.warning(
                    "[regen_loop] %s: Parameter 1 fail on sub-mechanic %r — but 0 anchors "
                    "in inventory support that sub-mechanic. Regen won't fix this; "
                    "shipping post at best-effort (Parameter 1 may be ~9.0 not 10.0).",
                    label, required_sm,
                )
                unfixable_targets.append(label)

        # Drop unfixable targets from the regen list.
        if unfixable_targets:
            regen_targets = [t for t in regen_targets if t.get("label") not in unfixable_targets]
            if not regen_targets:
                logger.info(
                    "[regen_loop] all failing posts are unfixable Parameter 1 mismatches — shipping pack as-is"
                )
                return ShipDecision(
                    ship=True, pack=pack,
                    detailed_failures=validation,
                    total_regens_used=total_regens,
                )

        # Check if any target has exhausted its regen budget.
        for tgt in regen_targets:
            label = tgt.get("label", "")
            if not label:
                continue
            if post_regen_counts.get(label, 0) >= MAX_REGEN_ATTEMPTS_PER_POST:
                logger.warning(
                    "[regen_loop] post %s exhausted %d regens — rejecting pack",
                    label, MAX_REGEN_ATTEMPTS_PER_POST,
                )
                recs = generate_recommendations(validation)
                return ShipDecision(
                    ship=False, pack=None,
                    rejection_reason=(
                        f"Post {label} failed validation after "
                        f"{MAX_REGEN_ATTEMPTS_PER_POST} regens — "
                        f"{tgt.get('failure_reason', 'unknown')}"
                    ),
                    detailed_failures=validation,
                    recommendations=recs,
                    total_regens_used=total_regens,
                )

        # Pack-level total regen cap (cost guardrail).
        if total_regens >= MAX_TOTAL_REGENS_PER_PACK:
            logger.warning(
                "[regen_loop] pack hit total regen cap (%d) — rejecting",
                MAX_TOTAL_REGENS_PER_PACK,
            )
            recs = generate_recommendations(validation)
            return ShipDecision(
                ship=False, pack=None,
                rejection_reason=(
                    f"Total regens exceeded budget ({MAX_TOTAL_REGENS_PER_PACK}). "
                    "Multiple posts unable to reach 9.7+ floor."
                ),
                detailed_failures=validation,
                recommendations=recs,
                total_regens_used=total_regens,
            )

        # Regen each failing post.
        for tgt in regen_targets:
            label = tgt.get("label", "")
            if not label:
                continue
            post_regen_counts[label] = post_regen_counts.get(label, 0) + 1
            total_regens += 1
            attempt = post_regen_counts[label]

            existing = next((p for p in pack.posts if p.label == label), None)
            if existing is None:
                logger.warning("[regen_loop] target %s not in pack — skipping", label)
                continue

            failure_reason = tgt.get("failure_reason", "")
            # v6.1: explicit_regen_instructions MUST be a dict per the
            # 05_validate.txt schema invariant. But we coerce defensively in
            # case a model produces None/str/list — see safe_get_regen_instructions().
            instructions = safe_get_regen_instructions(
                tgt.get("explicit_regen_instructions")
            )
            # v6 fallback: if validator emitted a string pointer like
            # "see per_post_validation.A2.regen_instructions" and the nested
            # entry has structured guidance, prefer that.
            if (
                not instructions["explicit_avoid"]
                and not instructions["required_sub_mechanic"]
            ):
                per_post = validation.get("per_post_validation", []) or []
                for entry in per_post:
                    if isinstance(entry, dict) and entry.get("label") == label:
                        nested = entry.get("regen_instructions") or entry.get("explicit_regen_instructions")
                        if nested:
                            instructions = safe_get_regen_instructions(nested)
                        break

            explicit_avoid = instructions["explicit_avoid"]
            required_sub_mechanic = instructions["required_sub_mechanic"]
            anchor_to_use = instructions["anchor_to_use"]
            regenerate_with_mechanic = instructions["regenerate_with_mechanic"]
            fallback_strategy = instructions["fallback_strategy"]

            logger.info(
                "[regen_loop] regenerating %s attempt %d (failure: %s, "
                "required_sub_mechanic=%r, anchor_to_use=%r)",
                label, attempt, failure_reason,
                required_sub_mechanic, anchor_to_use,
            )

            new_post = regenerator_fn(
                state=state,
                post_label=label,
                regen_attempt=attempt,
                failed_parameters=failure_reason,
                explicit_avoid=explicit_avoid,
                required_sub_mechanic=required_sub_mechanic,
                anchor_to_use=anchor_to_use,
                regenerate_with_mechanic=regenerate_with_mechanic,
                fallback_strategy=fallback_strategy,
                prior_attempt_text=existing.text,
            )

            if new_post is None:
                logger.warning(
                    "[regen_loop] regen %s attempt %d returned None — keeping prior",
                    label, attempt,
                )
                existing.regen_history.append({
                    "attempt": attempt,
                    "outcome": "fail",
                    "reason": "regenerator returned None",
                })
                continue

            # Track regen history on the new post.
            new_post.regen_count = attempt
            new_post.regen_history = list(existing.regen_history) + [{
                "attempt": attempt,
                "failed_parameters": failure_reason,
                "explicit_avoid": explicit_avoid,
            }]

            # Replace in pack.
            for i, p in enumerate(pack.posts):
                if p.label == label:
                    pack.posts[i] = new_post
                    break

        # Loop back to validate.
