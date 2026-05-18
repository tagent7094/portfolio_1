"""Standalone JSON-to-Excel converter for batch output files.

Usage:
    python -m src.batch.json_to_excel <path_to_batch_json>

Produces an .xlsx file alongside the input JSON with a single "Posts" sheet.
"""

import json
import sys
from pathlib import Path


def convert(json_path: str) -> str:
    """Convert a batch output JSON to Excel. Returns the Excel path."""
    import openpyxl

    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {json_path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    headers = [
        "Label", "Source #", "Batch", "Entry Door", "Mode",
        "Post Text", "Word Count", "Voice Score",
        "Opener Mechanic", "Opener Rating", "Recommended Variant",
        "Original Opening", "Final Opening",
        "Buried Gold", "Weakness",
        "Argument",
        "Events Used", "Violations",
        "Gates Passed", "Convergence", "Saturation",
    ]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Posts"
    ws.append(headers)

    for pack in data.get("packs", []):
        src_num = pack.get("source_number", 0)
        conv = pack.get("convergence_test", {})
        conv_warning = pack.get("convergence_warning", False)
        conv_retried = pack.get("convergence_retry_attempted", False)
        if conv.get("passed", True):
            conv_str = "PASS (after regen)" if conv_retried else "PASS"
        elif conv_warning:
            conv_str = f"WARN — STILL FAIL after regen: {conv.get('recommendation', '')[:200]}"
        else:
            conv_str = f"FAIL: {conv.get('recommendation', '')[:200]}"

        for post in pack.get("posts", []):
            amp = post.get("amplifier", {})
            gates = amp.get("gates", {})
            gates_passed = all(gates.values()) if gates else ""
            if gates:
                gates_str = "PASS" if gates_passed else "FAIL: " + ", ".join(
                    k for k, v in gates.items() if not v
                )
            else:
                gates_str = ""

            events = post.get("events_used", [])
            events_str = "; ".join(events) if isinstance(events, list) else str(events)

            violations = post.get("violations", [])
            violations_str = "; ".join(violations) if violations else ""

            voice_score = post.get("voice_validation", {}).get("voice_score", "")

            sat = post.get("saturation_warning") or {}
            if sat.get("warning"):
                sat_str = f"WARN — {sat.get('count', 0)} shared 6-grams with {sat.get('worst_match_id', '?')}"
            elif sat.get("count", 0):
                sat_str = f"{sat.get('count')} shared"
            else:
                sat_str = ""

            row = [
                post.get("label", ""),
                src_num,
                post.get("batch", ""),
                post.get("entry_door", ""),
                post.get("mode", ""),
                post.get("text", ""),
                post.get("word_count", 0),
                voice_score,
                amp.get("mechanic", ""),
                amp.get("rating", ""),
                amp.get("recommended_variant", ""),
                amp.get("original_opening", ""),
                amp.get("final_opening", ""),
                amp.get("buried_gold", ""),
                amp.get("weakness", ""),
                post.get("argument_compressed", ""),
                events_str,
                violations_str,
                gates_str,
                conv_str,
                sat_str,
            ]
            ws.append([str(v) if v is not None else "" for v in row])

    # Formatting
    for cell in ws[1]:
        cell.font = openpyxl.styles.Font(bold=True)
    ws.freeze_panes = "A2"

    # Column widths for readability
    col_widths = {
        "A": 8, "B": 10, "C": 7, "D": 14, "E": 12,
        "F": 80, "G": 12, "H": 12,
        "I": 18, "J": 12, "K": 12,
        "L": 60, "M": 60,
        "N": 60, "O": 60,
        "P": 80,
        "Q": 40, "R": 30,
        "S": 20, "T": 40, "U": 35,
    }
    for col, width in col_widths.items():
        ws.column_dimensions[col].width = width

    # Cost sheet — surfaces this run's API spend so founders see where money went.
    cost = data.get("cost") or {}
    cs = wb.create_sheet("Run Cost")
    cs.append(["Metric", "Value"])
    cs.append(["Total USD", f"${cost.get('total_usd', 0):.4f}"])
    cs.append(["Input tokens", cost.get("total_input_tokens", 0)])
    cs.append(["Output tokens", cost.get("total_output_tokens", 0)])
    if cost.get("warning"):
        cs.append(["⚠ Warning", cost["warning"]])
    cs.append([])
    cs.append(["Cost by task (USD)", ""])
    for k, v in sorted((cost.get("by_task") or {}).items(), key=lambda x: -x[1]):
        cs.append([k, f"${v:.4f}"])
    cs.append([])
    cs.append(["Cost by model (USD)", ""])
    for k, v in sorted((cost.get("by_model") or {}).items(), key=lambda x: -x[1]):
        cs.append([k, f"${v:.4f}"])
    cs.append([])
    cs.append(["Cost by source pack (USD)", ""])
    for k, v in sorted((cost.get("by_pack") or {}).items()):
        cs.append([f"pack {k}", f"${v:.4f}"])
    cs.column_dimensions["A"].width = 36
    cs.column_dimensions["B"].width = 24

    xlsx_path = path.with_suffix(".xlsx")
    wb.save(xlsx_path)
    return str(xlsx_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.batch.json_to_excel <path_to_batch_json>", file=sys.stderr)
        sys.exit(1)

    result = convert(sys.argv[1])
    print(f"Excel saved: {result}")
