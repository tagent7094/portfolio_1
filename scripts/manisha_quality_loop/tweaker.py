"""Prompt-edit functions per audit parameter.

Each tweak is a surgical insertion into transpose.txt — adds a focused
section with explicit examples right before the OUTPUT FORMAT block. One
tweak per iteration to keep the cause→effect signal clean.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPT_FILE = (
    Path(__file__).parent.parent.parent
    / "src" / "batch" / "prompts" / "transpose.txt"
)
BACKUP_FILE = PROMPT_FILE.with_suffix(".txt.preloop_backup")

# Anchor sentinel — we insert tweak blocks AFTER this marker. The closing
# ## OUTPUT FORMAT section in transpose.txt is always preceded by a "---".
INSERTION_MARKER = "## OUTPUT FORMAT"


def save_preloop_backup() -> None:
    """One-time backup of the production prompt before any loop tweaks."""
    if not BACKUP_FILE.exists():
        shutil.copy2(PROMPT_FILE, BACKUP_FILE)
        logger.info("[tweaker] Saved pre-loop backup to %s", BACKUP_FILE)


def restore_preloop_backup() -> None:
    """Restore the production prompt to its pre-loop state."""
    if BACKUP_FILE.exists():
        shutil.copy2(BACKUP_FILE, PROMPT_FILE)
        logger.info("[tweaker] Restored prompt from pre-loop backup")


def _read_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def _write_prompt(new_content: str) -> None:
    PROMPT_FILE.write_text(new_content, encoding="utf-8")


def _insert_block(block_title: str, block_body: str) -> tuple[str, str]:
    """Insert block before INSERTION_MARKER if not already present. Returns
    (status, diff_summary). Status is 'inserted' or 'already_present'.
    """
    current = _read_prompt()
    if block_title in current:
        return "already_present", f"Block '{block_title}' already in prompt — no change"

    block = f"\n\n{block_title}\n{block_body.rstrip()}\n\n---\n"
    idx = current.find(INSERTION_MARKER)
    if idx == -1:
        # Fallback: append at end
        new_content = current.rstrip() + block
    else:
        # Find the "---" line just before INSERTION_MARKER and insert before that
        before_marker = current[:idx]
        last_sep = before_marker.rfind("\n---\n")
        if last_sep == -1:
            new_content = before_marker + block + current[idx:]
        else:
            new_content = (
                before_marker[:last_sep]
                + block
                + before_marker[last_sep:]
                + current[idx:]
            )

    _write_prompt(new_content)
    return "inserted", f"Inserted block '{block_title}' before {INSERTION_MARKER}"


# ---------------------------------------------------------------------------
# Tweak templates (verbatim from user's prompt)
# ---------------------------------------------------------------------------

_T_P1 = """The source uses this opener mechanic: refer to dissection.hook_mechanic_primary.
Your opener MUST use the same mechanic family.

If source uses "audience-address + scale credential + count promise":
  Sentence 1: [Audience]: + [scale credential from founder, NOT source].
  Sentence 2: [Threat or insight] in founder's voice.

Source example (DO NOT COPY):
"From zero to $4 billion ARR (!!) - one CRO, one epic run. He figured out..."

Manisha example (DO USE):
"From zero to a board seat at Paytm — one founder, one decade-long arc. She figured out..."

The structural beats match. The phrasing differs. The voice is founder's."""

_T_P2 = """These anchors are FROM THE SOURCE and must NOT appear in your output:
- "$4 billion ARR"
- "Chris Degnan"
- "Snowflake"
- "GTMnow podcast"
- "decade before AI existed"
- "you're already behind"

You MUST substitute with one of Manisha's verified anchors:
- "$80M ARR enterprise customer" (anonymized SiftHub reference)
- "board seat at Paytm" (verified — Independent Director)
- "Vijay/Paytm 2015 investment" (verified — first startup)
- "Dreamforce notebook scene" (verified — pre-product market validation)
- "presales leaders dinner" (verified — context observation)
- "vertical AI for B2B GTM" (SiftHub mission)
- "14 case studies, 3 people knew where to find them" (SiftHub internal scene)

Pick the anchor that best maps to the post's argument. Different anchor per A1/A2/A3."""

_T_P3 = """Before writing the post:
1. State the opener's promise in one sentence: "This post will argue ___"
2. State the body's actual argument in one sentence: "The body delivers ___"
3. If these don't match exactly, EITHER rewrite the opener to match the body, OR rewrite the body to match the opener.

Common failure: opener teases a named person's story ("She figured out something..."), body delivers founder's own thesis instead. This is bait-and-switch — coherence FAIL.

If you can't honor the opener's promise with available founder anchors, change the opener."""

_T_P4 = """Every Batch A post MUST contain at least ONE of these anchor types:

TIER 1 (preferred): Specific operating rule
Pattern: [Specific actor] + [specific action] + [specific number/threshold] + [emphasis/repetition]
Example: "The product team doesn't ship a feature until the CRO has heard the request from three buyers. Not one. Not two. Three."

TIER 2 (acceptable): Named scene with quoted dialogue
Pattern: [Specific time] + [specific setting] + [specific question] + [direct quote]
Example: "I had coffee with this founder last week and asked her why she hired her CRO at month two with no product to sell. Her answer: 'Because I needed to know if there was a market before I built a product for it.'"

NOT ACCEPTABLE: Generic third-degree pattern
Example: "I've watched founders at $500M companies struggle with..."

Without a Tier 1 or Tier 2 anchor, the post fails. Do not return."""

_T_P5 = """The closing 1-2 sentences must include AT LEAST 2 of:
1. Specific time measurement ("six weeks", "thirty minutes", "two quarters")
2. Concrete physical/temporal image (not abstract systems metaphor)
3. Parallel structure with twist on second clause
4. ≤30 words total

Good examples:
- "Demos can be matched in six weeks. The thirty minutes after a demo cannot."
- "Six weeks of code can be rewritten. Six months of wrong-ICP pipeline compounds in the other direction."
- "Feature parity arrives on a calendar. Distribution depth doesn't."

Bad example (abstract restatement):
- "The ones that win treat it as the upstream sensor that tells engineering what to ship."

Do not return a post with a weak closer."""

_T_P6 = """Each Batch A post MUST contain AT LEAST 3 of these documented Manisha markers:

1. "I've watched" / "I've sat through" / "I keep hearing" — witness framing
2. "Not because X. Because Y." — negation-then-truth pattern
3. "And" sentence-start for rhythmic emphasis
4. Capitalized emphasis on single word (e.g., "the person explaining it IS building it")
5. "The real [X] is [Y]" — reframe construction
6. Short declarative provocation (≤8 words) as standalone paragraph
7. Hyphenated bullet lists (-, not •)
8. Direct audience address by role ("CROs:", "SEs:", "Founders:")

Count markers before returning. If fewer than 3, rewrite."""

_T_P7 = """Compare your output to the source on these dimensions:
- Opener sentence count: source has N sentences, mine has ___
- Body format: source uses {numbered_list|paragraphs|three_examples}, mine uses ___
- Closer mechanic: source uses {cta|reframe_question|terminal_verdict}, mine uses ___

If any of these don't match, revise before returning. The voice differs. The structural beats stay."""

_T_P9 = """Target: 220-260 words (Manisha's median is 225).
Hard band: 180-280 words.

Before returning, count words. If outside hard band, trim or expand:
- Over 280: cut second-to-last paragraph
- Under 180: expand the body anchor with one more specific detail"""

_T_P10 = """Banned phrases that must NEVER appear in output:
- "you're already behind" (source's exact phrase)
- "let that sink in"
- "here's the thing"
- "hot take"
- "in today's [X] landscape"
- Any double exclamation marks (!!)
- Source's exact urgency closers

ACROSS the 3 Batch A posts you generate:
- Each post must use a DIFFERENT urgency closer
- Each post must reference a DIFFERENT verified anchor
- Posts must argue DIFFERENT compressed arguments

If you cannot generate 3 distinct openers using different anchors, flag for source review."""


TWEAK_TEMPLATES: dict[str, tuple[str, str]] = {
    "P1": ("## P1 — OPENER MECHANIC MIRROR (loop tweak)", _T_P1),
    "P2": ("## P2 — SOURCE ANCHOR SUBSTITUTION (loop tweak)", _T_P2),
    "P3": ("## P3 — COHERENCE PRE-COMMIT (loop tweak)", _T_P3),
    "P4": ("## P4 — BODY ANCHOR REQUIREMENT (loop tweak)", _T_P4),
    "P5": ("## P5 — CLOSER REQUIREMENTS (loop tweak)", _T_P5),
    "P6": ("## P6 — VOICE MARKER REQUIREMENTS (loop tweak)", _T_P6),
    "P7": ("## P7 — STRUCTURAL VERIFICATION (loop tweak)", _T_P7),
    "P9": ("## P9 — WORD COUNT (loop tweak)", _T_P9),
    "P10": ("## P10 — ANTI-CONTAMINATION (loop tweak)", _T_P10),
}


def apply_tweak(param_id: str) -> dict:
    """Apply the tweak for the given parameter. Returns:
    {"param": "P1", "status": "inserted|already_present", "summary": "..."}
    """
    if param_id == "P8":
        return {
            "param": "P8",
            "status": "skipped",
            "summary": "P8 is amplifier logic — already fixed in Stage 0",
        }
    if param_id not in TWEAK_TEMPLATES:
        return {
            "param": param_id,
            "status": "unknown",
            "summary": f"No tweak template for {param_id}",
        }

    title, body = TWEAK_TEMPLATES[param_id]
    status, summary = _insert_block(title, body)
    return {"param": param_id, "status": status, "summary": summary}
