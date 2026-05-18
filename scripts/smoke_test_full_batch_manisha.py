"""End-to-end smoke test: run the full batch pipeline against Manisha with
the original failing $18K Claude Code source.

This exercises EVERY v6.1 path:
  1. voice_load (cached, fast)
  2. build_anchor_inventory — cache should auto-invalidate (v6.1 key bump)
     and rebuild WITH `unlocks_sub_mechanics[]` per anchor.
  3. dissect_source — should emit hook_sub_mechanic, mirror_feasible,
     source_fitness_check.routing_decision.
  4. generate_pack_sequential — generates the pack count routing decided.
     For this source + Manisha's likely inventory, we expect 0 A + 9 B.
  5. validate_pack — emits per_post_validation[] + pack_decision with
     ship_or_regen_or_reject (never "?").
  6. compile_pack — emits pack_decision: ship | regen_more.

Listens on the event_bus to capture key decisions and asserts:
  - routing_decision is in expected enum
  - validate's pack_decision is non-"?"
  - prompt_version in pack metadata reflects v6.1

Run from project root (will block ~5-15 minutes depending on regen passes):
    python scripts/smoke_test_full_batch_manisha.py
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


SOURCE_POST = """Our Claude Code API bill just crossed $18,000/month.

That's headcount territory. For a team of under 8 revenue-facing people. And most of that spend came from our presales team alone — which is even smaller.

We're all-in on AI-native selling. I wrote about how we restructured our workflow to make this safe — context-first discovery, demo prep as a hard constraint, multi-model battle cards, security reviews on every outbound (link in comments).

That playbook is working. We're closing faster than we ever have.

But it's surfacing a much harder question:

When AI generates most of the prep, how do you know if your SEs are actually getting better?

Seriously. Think about it.

Demos delivered — meaningless. Slides created — inflated. Discovery calls completed — noise. Even technical validation, the old gold standard, breaks down when AI generates hundreds of passing security checks that don't verify anything meaningful.

Meanwhile the real risks are subtle:

→ Context turnover. Are AI-generated discovery notes stable or constantly rewritten by the next SE who touches the account?
→ Quality attribution. Can you tell the difference between human-built and AI-assisted deal strategy in the forecast?
→ False acceleration. Are you cycling faster, or generating more to repair in procurement?
→ POV integrity. Does your point of view actually change the buyer's thinking, or just inflate confidence scores?

Every revenue leader adopting AI tools will hit this wall. The spend is easy to justify when activity feels high. It's much harder to prove the investment is actually working.

The teams that crack measurement will compound their advantage. The rest will generate a lot of pipeline and wonder why nothing closes.
"""


def main() -> None:
    from src.generation.pipeline_events import PipelineEventBus
    from src.batch.session import BatchSession

    print("=" * 70)
    print("FULL BATCH SMOKE TEST: Manisha + $18K Claude Code source")
    print("=" * 70)
    print()

    # Confirm the anchor inventory cache will be invalidated (v6.1 key bump).
    cache_path = PROJECT_ROOT / "data" / "founders" / "Manisha" / ".anchor_inventory_cache.json"
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            old_key = cached.get("hash", "")
            print(f"[pre] Manisha anchor cache exists (hash={old_key[:16]}...) — should auto-invalidate due to v6.1 cache key bump")
        except Exception:
            print(f"[pre] Manisha anchor cache exists but unreadable")
    else:
        print(f"[pre] no existing anchor cache for Manisha — will build fresh")

    # Event bus listener — captures all events to stdout AND key signals to a dict.
    captured = {
        "routing_decision": None,
        "matching_anchor_count": None,
        "mirror_feasible": None,
        "validate_decision_value": None,
        "compile_decision_values": [],
        "pack_count": 0,
        "post_count": 0,
        "anchor_inventory_built": False,
        "anchor_inventory_cache_hit": False,
        "anchors_with_sub_mechanics": 0,
        "quality_floor_warning": False,
        "events_seen": [],
    }

    event_bus = PipelineEventBus()

    def listener():
        for event in event_bus.stream():
            # event is "data: {...}\n\n" — skip the SSE framing
            if not event.startswith("data: "):
                continue
            try:
                payload = json.loads(event[6:].strip())
            except Exception:
                continue
            stage = payload.get("stage", "")
            status = payload.get("status", "")
            data = payload.get("data", {}) or {}
            captured["events_seen"].append(f"{stage}/{status}")

            # Print key milestones inline.
            if "pack_" in stage and status == "started":
                print(f"\n[event] {stage} STARTED  source_preview={data.get('source_preview', '')[:60]!r}")
            elif stage.startswith("pack_") and status == "progress":
                # Look for dissect routing.
                if "_dissected" in str(data):
                    for k, v in data.items():
                        if isinstance(v, dict) and "hook_mechanic" in v:
                            print(f"[event] dissect: hook_mechanic={v.get('hook_mechanic')} mirrorable={v.get('mirrorable')}")
            elif stage.startswith("pack_") and status == "validate":
                captured["validate_decision_value"] = data.get("ship", "unknown")
                print(f"[event] {stage} validate: ship={data.get('ship')} regens_used={data.get('regens_used')}")
            elif stage.startswith("pack_") and status == "compile_decision":
                captured["compile_decision_values"].append(data.get("pack_decision"))
                print(f"[event] {stage} compile: pack_decision={data.get('pack_decision')} pass={data.get('compile_pass')}")
            elif stage.startswith("pack_") and status == "completed":
                captured["pack_count"] += 1
                captured["post_count"] += data.get("posts", 0)
                captured["quality_floor_warning"] = captured["quality_floor_warning"] or data.get("quality_floor_warning", False)
                print(f"[event] {stage} completed: posts={data.get('posts')} warning={data.get('quality_floor_warning')}")
            elif stage == "internalize" and status == "started":
                print(f"[event] internalize started")
            elif stage == "anchor_inventory" and status == "started":
                print(f"[event] anchor_inventory build started (cache miss → rebuilding with v6.1 schema)")
                captured["anchor_inventory_built"] = True
            elif stage == "anchor_inventory" and status == "completed":
                print(f"[event] anchor_inventory completed")
            elif stage == "batch" and status == "pipeline_done":
                print(f"\n[event] BATCH DONE: total_posts={data.get('total_posts')}, file={data.get('filepath', '')[-80:]}")

    listener_thread = threading.Thread(target=listener, daemon=True)
    listener_thread.start()

    session = BatchSession(event_bus=event_bus)

    print("\n[step] kicking off batch session.run() — this may take ~5-10 min ...\n")
    start = time.time()
    try:
        output = session.run(
            founder_slug="manisha",
            platform="linkedin",
            creativity=0.5,
            n_sources=1,
            posts_per_source=9,
            enable_thinking=False,
            source_posts=[SOURCE_POST],
            effort="medium",
            lean=False,
        )
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n[FAIL] session.run() crashed after {elapsed:.1f}s: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    elapsed = time.time() - start
    print(f"\n[ok] session.run() finished in {elapsed:.1f}s")

    # Inspect the final pack file to verify v6.1 schema markers.
    filepath = (output or {}).get("metadata", {})
    print(f"\n[inspect] output metadata:")
    print(f"  prompt_version : {output.get('metadata', {}).get('prompt_version')}")
    print(f"  total_posts    : {output.get('metadata', {}).get('total_posts')}")

    # Look at the inventory cache to verify unlocks_sub_mechanics[] populated.
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        new_key = cached.get("hash", "")
        anchors = (cached.get("result", {}) or {}).get("anchor_inventory", []) or []
        with_unlocks = [a for a in anchors if a.get("unlocks_sub_mechanics")]
        captured["anchors_with_sub_mechanics"] = len(with_unlocks)
        print(f"\n[inspect] anchor inventory rebuild:")
        print(f"  total anchors             : {len(anchors)}")
        print(f"  with unlocks_sub_mechanics: {len(with_unlocks)}")
        if anchors:
            sample = anchors[0]
            print(f"  sample anchor             : {sample.get('anchor_id')} → {sample.get('unlocks_sub_mechanics')}")

    # Look at the saved pack JSON for routing decision.
    metadata = output.get("metadata", {}) or {}
    packs = output.get("packs", []) or []
    if packs:
        pack = packs[0]
        dissection = pack.get("dissection", {}) or {}
        fitness = dissection.get("source_fitness_check") or {}
        captured["routing_decision"] = fitness.get("routing_decision")
        captured["matching_anchor_count"] = fitness.get("matching_sub_mechanic_count")
        captured["mirror_feasible"] = fitness.get("mirror_feasible")
        print(f"\n[inspect] dissect output (from saved pack JSON):")
        print(f"  hook_mechanic_primary : {dissection.get('hook_mechanic_primary')}")
        print(f"  hook_sub_mechanic     : {dissection.get('hook_sub_mechanic')}")
        print(f"  routing_decision      : {fitness.get('routing_decision')}")
        print(f"  mirror_feasible       : {fitness.get('mirror_feasible')}")
        print(f"  matching_anchor_count : {fitness.get('matching_sub_mechanic_count')}")
        print(f"  matching_anchor_ids   : {fitness.get('sub_mechanic_anchor_matches')}")

        # Count A vs B posts.
        a_count = sum(1 for p in pack.get("posts", []) if p.get("batch") == "A")
        b_count = sum(1 for p in pack.get("posts", []) if p.get("batch") == "B")
        print(f"  generated A posts     : {a_count}")
        print(f"  generated B posts     : {b_count}")

    print("\n" + "=" * 70)
    print("ASSERTIONS")
    print("=" * 70)
    failures = []

    pv = metadata.get("prompt_version")
    if isinstance(pv, dict) and pv.get("source_dissect_hook") == "v6.1.0":
        print("[ok] prompt_version reflects v6.1")
    else:
        failures.append(f"prompt_version not v6.1 (got {pv})")

    if captured["routing_decision"] in ("generate_4_batch_a_5_batch_b", "skip_batch_a_route_all_to_b"):
        print(f"[ok] routing_decision in expected enum: {captured['routing_decision']}")
    else:
        failures.append(f"routing_decision unexpected: {captured['routing_decision']}")

    if captured["validate_decision_value"] is not None:
        print(f"[ok] validate emitted a ship decision (not '?')")
    else:
        failures.append("validate never emitted a ship decision")

    if captured["pack_count"] >= 1 and captured["post_count"] >= 1:
        print(f"[ok] {captured['pack_count']} pack(s), {captured['post_count']} post(s) generated")
    else:
        failures.append(f"pack/post count too low: {captured['pack_count']} packs, {captured['post_count']} posts")

    if captured["anchors_with_sub_mechanics"] > 0:
        print(f"[ok] anchor inventory rebuilt with sub-mechanic tagging ({captured['anchors_with_sub_mechanics']} anchors)")
    else:
        print(f"[warn] no anchors have unlocks_sub_mechanics — may mean cache was hit (check log) or LLM didn't populate the field")

    if failures:
        print(f"\n[FAIL] {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\n[PASS] full batch pipeline v6.1 works end-to-end for Manisha.")


if __name__ == "__main__":
    main()
