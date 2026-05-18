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

VARIANT_LETTERS = ("A", "B", "C", "D", "E")

_VARIANT_HEADERS: list[str] = []
for _letter in VARIANT_LETTERS:
    _VARIANT_HEADERS += [
        f"Variant {_letter} Opening",
        f"Variant {_letter} Rewrite Type",
        f"Variant {_letter} Key Change",
        f"Variant {_letter} Expected Lift",
    ]

# 42 columns — the canonical schema for a post pack row.
BATCH_HEADERS: list[str] = [
    "Row #", "Source #", "Type", "Entry Door", "Mode",
    "Final Post", "Word Count", "Voice Score", "Violations",
    "Mechanic", "Original Opening", "Final Opening",
    "Rating", "Recommended", "Buried Gold", "Weakness", "Versions Considered",
    *_VARIANT_HEADERS,
    "Argument", "Events Used", "Gates", "Source Post", "Convergence",
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

            row: dict[str, Any] = {
                "Row #": f"{src_num}-{post.get('label', '')}",
                "Source #": src_num,
                "Type": post.get("batch", ""),
                "Entry Door": post.get("entry_door", ""),
                "Mode": post.get("mode", ""),
                "Final Post": post.get("text", ""),
                "Word Count": post.get("word_count", 0),
                "Voice Score": (post.get("voice_validation") or {}).get("voice_score", ""),
                "Violations": "; ".join(post.get("violations", []) or []),
                "Mechanic": amp.get("mechanic", ""),
                "Original Opening": amp.get("original_opening", ""),
                "Final Opening": amp.get("final_opening", ""),
                "Rating": amp.get("rating", 0),
                "Recommended": amp.get("recommended_variant", ""),
                "Buried Gold": amp.get("buried_gold", ""),
                "Weakness": amp.get("weakness", ""),
                "Versions Considered": amp.get("versions_considered", 0),
                "Argument": post.get("argument_compressed", ""),
                "Events Used": events_str,
                "Gates": gates_str,
                "Source Post": source_post,
                "Convergence": conv_str,
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
