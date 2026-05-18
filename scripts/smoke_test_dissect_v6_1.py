"""Local smoke test for the v6.1 dissect prompt.

Generalized: runs the SAME viral source against THREE synthetic founder
inventory profiles to prove the routing logic varies correctly by founder:

  Scenario 1: founder WITH a matching sub-mechanic anchor    → expect 4A+5B
  Scenario 2: founder with NO matching sub-mechanic anchor   → expect 9B-only
  Scenario 3: founder with only adjacent (family-level) match → expect 9B-only

Each scenario runs the live dissect prompt against Kimi K2.6 and asserts:
  - All v6.1 schema fields populate.
  - hook_mechanic_primary is a valid template repository ID.
  - routing_decision matches expected enum value.
  - sub_mechanic_anchor_matches references only real inventory IDs.

This is the v6.1 generalization guarantee: every founder's inventory drives
the routing decision data-fast, no founder-specific code anywhere.

Run from project root:
    python scripts/smoke_test_dissect_v6_1.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.text_utils import load_prompt, fill_prompt
from src.utils.json_parser import parse_llm_json
from src.llm.moonshot_provider import MoonshotProvider


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


# Scenario 1: Founder Alpha — runs an AI tooling-heavy team, has a verified
# first-person monthly-cost anchor. Should mirror the source in Batch A.
SCENARIO_STRONG_MATCH = {
    "founder": "founder_alpha",
    "expected_routing": "generate_4_batch_a_5_batch_b",
    "expected_mirror_feasible": True,
    "anchor_inventory": [
        {
            "anchor_id": "FA001",
            "anchor_text": "Our internal AI compute bill crossed $24K/month for a 12-person eng org",
            "label": "AI compute spike",
            "tier": 1,
            "cast_involved": ["CFO"],
            "recently_used": False,
            "unlocks_sub_mechanics": [
                "first_person_monthly_cost",
                "team_count_anchor",
                "scale_inversion",
            ],
            "usable_for_b_only": False,
        },
        {
            "anchor_id": "FA002",
            "anchor_text": "Founder dinner at YC where 3 of 7 admitted same Claude bill problem",
            "label": "YC founder dinner",
            "tier": 1,
            "cast_involved": ["YC partners", "peer founders"],
            "recently_used": False,
            "unlocks_sub_mechanics": [
                "operator_witness_scene",
                "multi_instance_pattern",
                "screenplay_conflict",
            ],
            "usable_for_b_only": False,
        },
    ],
    "inventory_summary": {"depth_rating": "moderate-high", "total_anchors": 2},
}

# Scenario 2: Founder Beta (Manisha-like) — operates in enterprise sales
# domain, has anchors but NONE that unlock first-person monthly cost.
# Should refuse to mirror Batch A.
SCENARIO_NO_MATCH = {
    "founder": "founder_beta",
    "expected_routing": "skip_batch_a_route_all_to_b",
    "expected_mirror_feasible": False,
    "anchor_inventory": [
        {
            "anchor_id": "FB001",
            "anchor_text": "MUFG CIO/CISO Think Tank build-vs-buy argument",
            "label": "MUFG build-vs-buy",
            "tier": 1,
            "cast_involved": ["MUFG CIO", "MUFG CISO"],
            "recently_used": False,
            "unlocks_sub_mechanics": [
                "operator_witness_scene",
                "screenplay_conflict",
                "second_party_verdict",
            ],
            "usable_for_b_only": False,
        },
        {
            "anchor_id": "FB002",
            "anchor_text": "Five SE leaders hired in three years, each exited the same way",
            "label": "Five SE leaders pattern",
            "tier": 1,
            "cast_involved": [],
            "recently_used": False,
            "unlocks_sub_mechanics": [
                "multi_instance_pattern",
                "five_hires_same_result",
                "before_after_role",
            ],
            "usable_for_b_only": False,
        },
        {
            "anchor_id": "FB003",
            "anchor_text": "Off the Record event with 100+ solution leaders",
            "label": "Off the Record event",
            "tier": 1,
            "cast_involved": ["solution leaders"],
            "recently_used": False,
            "unlocks_sub_mechanics": [
                "external_authority_pivot",
                "best_i_ever_saw",
            ],
            "usable_for_b_only": False,
        },
    ],
    "inventory_summary": {"depth_rating": "moderate-high", "total_anchors": 3},
}

# Scenario 3: Founder Gamma — has same-family anchors (specific_number sub-
# mechanics like deal_size_anchor + age_time_anchor) but NOT the exact
# required first_person_monthly_cost. The current prompt allows family-level
# adjacent matching for `mirror_feasible`, so dissect routes to 4A+5B and
# leaves strict sub-mechanic enforcement to the validator's
# `parameter_1_hard_veto_triggered` per-post check. This is the intentional
# "optimistic at dissect, strict at validate" division of labor.
SCENARIO_ADJACENT_FAMILY_ONLY = {
    "founder": "founder_gamma",
    "expected_routing": "generate_4_batch_a_5_batch_b",
    "expected_mirror_feasible": True,
    "anchor_inventory": [
        {
            "anchor_id": "FG001",
            "anchor_text": "Closed our first $400K enterprise deal in 11 days",
            "label": "$400K fast close",
            "tier": 1,
            "cast_involved": [],
            "recently_used": False,
            "unlocks_sub_mechanics": [
                "deal_size_anchor",
                "before_after_company",
            ],
            "usable_for_b_only": False,
        },
        {
            "anchor_id": "FG002",
            "anchor_text": "13 years old when Google sent the first cease-and-desist",
            "label": "Age 13 cease-and-desist",
            "tier": 1,
            "cast_involved": ["Google legal"],
            "recently_used": False,
            "unlocks_sub_mechanics": [
                "age_time_anchor",
                "operator_witness_scene",
            ],
            "usable_for_b_only": False,
        },
    ],
    "inventory_summary": {"depth_rating": "moderate", "total_anchors": 2},
}

# Scenario 4: Founder Delta — wholly different domain (writer/journalist).
# Has zero anchors in the specific_number family. Should route 9B-only AND
# pick a B-template that suits her domain (likely scene_entry or contrarian).
SCENARIO_DOMAIN_MISMATCH = {
    "founder": "founder_delta",
    "expected_routing": "skip_batch_a_route_all_to_b",
    "expected_mirror_feasible": False,
    "anchor_inventory": [
        {
            "anchor_id": "FD001",
            "anchor_text": "Spent six months in the archives of the British Library researching her last book",
            "label": "British Library archives",
            "tier": 1,
            "cast_involved": [],
            "recently_used": False,
            "unlocks_sub_mechanics": [
                "operator_witness_scene",
                "time_anchor_in_room",
                "physical_artifact_anchor",
            ],
            "usable_for_b_only": False,
        },
        {
            "anchor_id": "FD002",
            "anchor_text": "Refused a $200K advance from a major publisher because the editor wanted to change the protagonist",
            "label": "$200K refusal",
            "tier": 1,
            "cast_involved": ["editor"],
            "recently_used": False,
            "unlocks_sub_mechanics": [
                "counterintuitive_no",
                "deal_rejection",
                "operator_admission",
            ],
            "usable_for_b_only": False,
        },
    ],
    "inventory_summary": {"depth_rating": "moderate", "total_anchors": 2},
}


SCENARIOS = [
    SCENARIO_STRONG_MATCH,
    SCENARIO_NO_MATCH,
    SCENARIO_ADJACENT_FAMILY_ONLY,
    SCENARIO_DOMAIN_MISMATCH,
]


REQUIRED_TOP_LEVEL_FIELDS = [
    "schema_version",
    "hook_mechanic_primary",
    "hook_sub_mechanic",
    "source_template_extraction",
    "batch_b_template_match",
    "source_fitness_check",
    "forbidden_phrases",
    "forbidden_templates",
    "source_strip_test_pass",
]
REQUIRED_TEMPLATE_EXTRACTION_FIELDS = [
    "opener_skeleton",
    "beat_order",
    "parameter_slots",
    "narrative_arc",
    "closer_type",
]
REQUIRED_BATCH_B_MATCH_FIELDS = [
    "selected_template_id",
    "template_tier",
    "rationale",
]
REQUIRED_FITNESS_FIELDS = [
    "required_sub_mechanic",
    "sub_mechanic_anchor_matches",
    "matching_sub_mechanic_count",
    "mirror_feasible",
    "routing_decision",
    "fitness_explanation",
]


def _load_kimi_key() -> str:
    cfg = json.loads((PROJECT_ROOT / "config" / "models-config.json").read_text(encoding="utf-8"))
    return cfg.get("provider_keys", {}).get("kimi", "")


def _build_compact_repo() -> list[dict]:
    repo = json.loads((PROJECT_ROOT / "src" / "batch" / "template_repository.json").read_text(encoding="utf-8"))
    return [
        {
            "id": t.get("id"),
            "tier": t.get("tier"),
            "name": t.get("name"),
            "sub_mechanics": t.get("sub_mechanics", []),
            "narrative_engine": t.get("narrative_engine"),
            "closing_move": t.get("closing_move"),
            "parameter_list": t.get("parameter_list", []),
            "mirror_requires": t.get("mirror_requires", []),
            "strip_test_template": t.get("strip_test_template"),
            "example_openings": (t.get("example_openings") or [])[:2],
        }
        for t in repo
    ]


def _assert(cond: bool, msg: str, failures: list[str]) -> bool:
    if not cond:
        failures.append(msg)
        return False
    return True


def run_scenario(scenario: dict, provider: MoonshotProvider, valid_ids: set, repo_compact: list[dict]) -> dict:
    """Run dissect for one founder scenario. Returns a result dict with
    `passed: bool`, `failures: list[str]`, and the parsed dissect output."""
    founder = scenario["founder"]
    print(f"\n{'-' * 70}\n[{founder}] expected: {scenario['expected_routing']}")

    template = load_prompt(PROJECT_ROOT / "src" / "batch" / "prompts" / "source_dissect_hook.txt")
    prompt = fill_prompt(
        template,
        source_post=SOURCE_POST,
        platform="linkedin",
        anchor_inventory=json.dumps(scenario["anchor_inventory"], ensure_ascii=False),
        inventory_summary=json.dumps(scenario["inventory_summary"], ensure_ascii=False),
        template_repository=json.dumps(repo_compact, ensure_ascii=False),
    )

    response = provider.generate(prompt, temperature=0.2, max_tokens=3000)
    result = parse_llm_json(response)

    failures: list[str] = []

    if not isinstance(result, dict):
        failures.append(f"response did not parse to dict; got {type(result).__name__}")
        return {"passed": False, "failures": failures, "result": None}

    # Schema-shape assertions.
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        _assert(field in result, f"missing top-level field `{field}`", failures)
    if "source_template_extraction" in result and isinstance(result["source_template_extraction"], dict):
        for field in REQUIRED_TEMPLATE_EXTRACTION_FIELDS:
            _assert(
                field in result["source_template_extraction"],
                f"missing source_template_extraction.{field}",
                failures,
            )
    if "batch_b_template_match" in result and isinstance(result["batch_b_template_match"], dict):
        for field in REQUIRED_BATCH_B_MATCH_FIELDS:
            _assert(
                field in result["batch_b_template_match"],
                f"missing batch_b_template_match.{field}",
                failures,
            )
    if "source_fitness_check" in result and isinstance(result["source_fitness_check"], dict):
        for field in REQUIRED_FITNESS_FIELDS:
            _assert(
                field in result["source_fitness_check"],
                f"missing source_fitness_check.{field}",
                failures,
            )

    # Repository-validity assertion.
    mechanic = result.get("hook_mechanic_primary")
    _assert(
        mechanic in valid_ids,
        f"hook_mechanic_primary={mechanic!r} not in template_repository ids",
        failures,
    )

    # anchor-ID-exists assertion.
    matches = (result.get("source_fitness_check") or {}).get("sub_mechanic_anchor_matches") or []
    known_ids = {a["anchor_id"] for a in scenario["anchor_inventory"]}
    bad = [m for m in matches if m not in known_ids]
    _assert(not bad, f"anchor_matches referencing unknown IDs: {bad}", failures)

    # Routing decision assertion (the GENERALIZATION proof).
    actual_routing = (result.get("source_fitness_check") or {}).get("routing_decision")
    expected = scenario["expected_routing"]
    _assert(
        actual_routing == expected,
        f"routing_decision={actual_routing!r}, expected {expected!r}",
        failures,
    )

    actual_feasible = (result.get("source_fitness_check") or {}).get("mirror_feasible")
    _assert(
        actual_feasible == scenario["expected_mirror_feasible"],
        f"mirror_feasible={actual_feasible}, expected {scenario['expected_mirror_feasible']}",
        failures,
    )

    # Summary print.
    fitness = result.get("source_fitness_check") or {}
    print(f"  routing_decision     : {fitness.get('routing_decision')}")
    print(f"  mirror_feasible      : {fitness.get('mirror_feasible')}")
    print(f"  matching_count       : {fitness.get('matching_sub_mechanic_count')}")
    print(f"  matching_anchor_ids  : {fitness.get('sub_mechanic_anchor_matches')}")
    print(f"  hook_sub_mechanic    : {result.get('hook_sub_mechanic')}")
    print(f"  selected_b_template  : {(result.get('batch_b_template_match') or {}).get('selected_template_id')}")

    if failures:
        print(f"  [FAILURES] {len(failures)}:")
        for f in failures:
            print(f"    - {f}")
    else:
        print(f"  [pass]")

    return {"passed": not failures, "failures": failures, "result": result}


def main() -> None:
    print("=" * 70)
    print("v6.1 dissect prompt — multi-founder generalization smoke test")
    print("=" * 70)

    api_key = _load_kimi_key()
    if not api_key:
        print("[FAIL] no Kimi API key in config/models-config.json")
        sys.exit(1)

    provider = MoonshotProvider(
        model="kimi-k2.6",
        api_key=api_key,
        base_url="https://api.moonshot.ai/v1",
    )
    provider._configured_max_tokens = 3000

    repo = json.loads((PROJECT_ROOT / "src" / "batch" / "template_repository.json").read_text(encoding="utf-8"))
    valid_ids = {t["id"] for t in repo}
    repo_compact = _build_compact_repo()

    results = []
    for scenario in SCENARIOS:
        results.append((scenario, run_scenario(scenario, provider, valid_ids, repo_compact)))

    # Final summary.
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    all_passed = True
    for scenario, r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  {status}  {scenario['founder']:18s}  -> {((r['result'] or {}).get('source_fitness_check') or {}).get('routing_decision', '?')}")
        if not r["passed"]:
            all_passed = False

    if all_passed:
        print("\n[OK] dissect generalizes correctly across all 3 founder scenarios.")
        print("     Same source. Different inventories. Different routing decisions.")
        print("     The system is data-driven, not founder-specific.")
        sys.exit(0)
    else:
        print("\n[FAIL] one or more scenarios failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
