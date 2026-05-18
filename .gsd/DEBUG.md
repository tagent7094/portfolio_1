# Debug Session: Batch Pipeline Prompt Migration

## Symptom
Batch generation pipeline crashes with `FileNotFoundError` on `02_dissect.txt` and produces 0 posts.

**When:** Every batch run (server restart triggers it)
**Expected:** Pipeline loads prompts, generates posts, saves pack
**Actual:** 
1. First: `FileNotFoundError` on `02_dissect.txt` (fixed in prior session)
2. After fix: prompts load but `A1 parse failed or empty text` → 0 posts generated

## Root Cause Analysis

### Issue 1: Wrong prompt filenames (FIXED)
Code referenced numbered files (`02_dissect.txt`, `03_generate.txt`, etc.) that were renamed.

### Issue 2: JSON output schema mismatch (FIXED)
`transpose.txt` wraps output in `{"posts": [...]}` but `_generate_one_post()` expected `{"text": "..."}` at the top level. Added unwrap logic after `parse_llm_json()`.

### Issue 3: Missing fill_prompt kwargs (FIXED)
`transpose.txt` expects placeholders like `{mode_rules}`, `{internalization}`, `{voice_markers}`, `{personality_card}`, `{formatting_habits}`, `{web_search_facts}`, `{prior_arguments}`, `{events_used}`, `{stories_used}` that the code wasn't providing. Added all missing kwargs from `BatchState` fields.

## Fixes Applied

| File | Fix |
|------|-----|
| `pack_generator.py:68` | `02_dissect.txt` → `source_dissect_hook.txt` |
| `pack_generator.py:496` | `03_generate.txt` → `transpose.txt` |
| `pack_generator.py:591-604` | Unwrap `{"posts": [...]}` array from transpose response |
| `pack_generator.py:559-604` | Added transpose.txt placeholder kwargs to fill_prompt |
| `amplifier.py:222` | `04_amplify.txt` → `amplify.txt` |
| `voice_validator.py:176` | `05_validate.txt` → `validate.txt` |
| `corpus_reader.py:178` | `01_voice_load.txt` → `corpus_internalize_v2.txt` |
| `anchor_inventory.py:99` | `00_anchor_inventory.txt` → `anchor_inventory.txt` |
| `compile_step.py:42` | `06_compile.txt` → `compile.txt` |

## Created Files
- `src/batch/prompts/anchor_inventory.txt` — new prompt for anchor inventory step
- `src/batch/prompts/compile.txt` — new prompt for compile/ship-gate step

## Status: PENDING VERIFICATION
Server restart needed to test.
