"""Single source of truth for the post-pack tabular schema.

Used by:
  - webapp/pack_routes.py    — batch JSON → table for the admin pack viewer
  - src/batch/json_to_excel  — Excel "Posts" sheet
  - src/batch/compiler       — anywhere that needs to know "what columns are in a pack?"

Schema changes happen ONLY in this file. If you find yourself copy-pasting a
header list elsewhere, fix the duplication: import from here instead.
"""

from __future__ import annotations

from typing import Any

# v6.1: only Variants A and B are populated by the amplifier (best alternative
# + runner-up). C/D/E always came back empty, so we drop them and reclaim that
# space for sub-mechanic + validator-score columns the v6.1 pipeline produces.
VARIANT_LETTERS = ("A", "B")

_VARIANT_HEADERS: list[str] = []
for _letter in VARIANT_LETTERS:
    _VARIANT_HEADERS += [
        f"Variant {_letter} Opening",
        f"Variant {_letter} Rewrite Type",
        f"Variant {_letter} Key Change",
        f"Variant {_letter} Expected Lift",
    ]

# Canonical schema for a post pack row. v6.1 fields appended at the end so
# existing spreadsheet bookmarks/filters don't shift unexpectedly.
BATCH_HEADERS: list[str] = [
    "Row #", "Source #", "Type", "Entry Door", "Mode",
    "Final Post", "Word Count", "Voice Score", "Violations",
    "Mechanic", "Closer Mechanic", "Anchor",
    "Original Opening", "Final Opening",
    "Rating", "Recommended", "Buried Gold", "Weakness", "Versions Considered",
    *_VARIANT_HEADERS,
    "Argument", "Events Used", "Stories Used", "Gates", "Source Post", "Convergence",
    # v6.1 validator surface
    "Passes 9/7 Floor",
    "Voice Marker", "Opener Rhythm", "Formatting", "Register", "Posture",
    "Anchor Grounding", "First-Degree Truth",
    "Required Sub-Mechanic", "Actual Sub-Mechanic", "Sub-Mechanic Match",
    "Param 1 Hard Veto", "Regen Count",
]

# Columns whose contents are typically long-form prose; consumers may wrap text.
LONG_TEXT_COLUMNS: set[str] = {
    "Final Post",
    "Source Post",
    "Original Opening",
    "Final Opening",
    "Buried Gold",
    "Weakness",
    "Argument",
}


def to_readme(data: dict) -> dict[str, str]:
    """Pack-level metadata for the README sheet / table preamble."""
    metadata = data.get("metadata", {}) or {}
    return {
        "Founder": str(metadata.get("founder", "")),
        "Date": str(metadata.get("generated_at", ""))[:10],
        "Posts": str(metadata.get("total_posts", 0)),
        "Sources": str(metadata.get("sources_count", 0)),
        "Platform": str(metadata.get("platform", "linkedin")),
        "Median word count": str(metadata.get("median_word_count", "")),
        "Pack": "Batch Cowork",
    }


def to_rows(data: dict) -> list[dict[str, Any]]:
    """Flatten the nested batch JSON into one row per post, keyed by BATCH_HEADERS."""
    rows: list[dict[str, Any]] = []
    for pack in data.get("packs", []) or []:
        src_num = pack.get("source_number", 0)
        source_post = str(pack.get("source_post", ""))
        conv = pack.get("convergence_test", {}) or {}
        conv_str = (
            "PASS"
            if conv.get("passed", True)
            else f"FAIL: {conv.get('recommendation', '')}"
        )

        for post in pack.get("posts", []) or []:
            amp = post.get("amplifier", {}) or {}
            gates = amp.get("gates", {}) or {}
            gates_str = (
                "; ".join(f"{k}={'pass' if v else 'fail'}" for k, v in gates.items())
                if gates else ""
            )

            events = post.get("events_used", [])
            events_str = (
                "; ".join(events) if isinstance(events, list) else str(events or "")
            )

            stories = post.get("stories_used", [])
            stories_str = (
                "; ".join(stories) if isinstance(stories, list) else str(stories or "")
            )

            vv = post.get("voice_validation") or {}

            row: dict[str, Any] = {
                "Row #": f"{src_num}-{post.get('label', '')}",
                "Source #": src_num,
                "Type": post.get("batch", ""),
                "Entry Door": post.get("entry_door", ""),
                "Mode": post.get("mode", ""),
                "Final Post": post.get("text", ""),
                "Word Count": post.get("word_count", 0),
                "Voice Score": vv.get("voice_score", ""),
                "Violations": "; ".join(post.get("violations", []) or []),
                # Prefer top-level field (transpose sets it on every post incl.
                # regens); fall back to amplifier sub-dict for legacy packs.
                "Mechanic": post.get("mechanic") or amp.get("mechanic", ""),
                "Closer Mechanic": post.get("closer_mechanic", ""),
                "Anchor": post.get("anchor_consumed_id")
                           or post.get("authority_anchor", ""),
                "Original Opening": amp.get("original_opening", ""),
                "Final Opening": amp.get("final_opening", ""),
                "Rating": amp.get("rating", 0),
                "Recommended": amp.get("recommended_variant", ""),
                "Buried Gold": amp.get("buried_gold", ""),
                "Weakness": amp.get("weakness", ""),
                "Versions Considered": amp.get("versions_considered", 0),
                "Argument": post.get("argument_compressed", ""),
                "Events Used": events_str,
                "Stories Used": stories_str,
                "Gates": gates_str,
                "Source Post": source_post,
                "Convergence": conv_str,
                # v6.1 validator surface
                "Passes 9/7 Floor": "yes" if vv.get("passes_9_7_floor") else "no",
                "Voice Marker": vv.get("voice_marker_score", ""),
                "Opener Rhythm": vv.get("opener_rhythm_score", ""),
                "Formatting": vv.get("formatting_score", ""),
                "Register": vv.get("register_score", ""),
                "Posture": vv.get("posture_score", ""),
                "Anchor Grounding": vv.get("anchor_grounding_score", ""),
                "First-Degree Truth": vv.get("first_degree_truth_score", ""),
                "Required Sub-Mechanic": vv.get("required_sub_mechanic", ""),
                "Actual Sub-Mechanic": vv.get("actual_sub_mechanic_used", ""),
                "Sub-Mechanic Match": "yes" if vv.get("sub_mechanic_match") else "no",
                "Param 1 Hard Veto": "yes" if vv.get("parameter_1_hard_veto_triggered") else "no",
                "Regen Count": post.get("regen_count", 0),
            }

            variants = amp.get("variants", []) or []
            variant_map = {
                v.get("variant", ""): v for v in variants if isinstance(v, dict)
            }
            for letter in VARIANT_LETTERS:
                v = variant_map.get(letter, {}) or {}
                row[f"Variant {letter} Opening"] = v.get("opening", "")
                row[f"Variant {letter} Rewrite Type"] = v.get("mechanic", "")
                row[f"Variant {letter} Key Change"] = v.get("key_change", "")
                row[f"Variant {letter} Expected Lift"] = v.get("expected_lift", "")

            rows.append(row)
    return rows


def to_tabular(data: dict) -> dict[str, Any]:
    """Return the standard {readme, headers, posts} envelope used by the pack API."""
    return {
        "readme": to_readme(data),
        "headers": list(BATCH_HEADERS),
        "posts": to_rows(data),
    }
