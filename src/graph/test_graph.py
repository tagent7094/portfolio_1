"""Test all 29 fixes against the real Sharath graph data."""

import json
import sys
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

# Add module to path
sys.path.insert(0, "/home/claude")

from graph_module.schema import (
    VALID_REGISTERS, VALID_RULE_TYPES, CATEGORY_HUBS,
)
from graph_module.builder import (
    build_graph, normalize_topic, _is_placeholder_id, _slugify,
    _normalize_register, _normalize_rule_type, _sanitize_personality_card,
    _split_compound_contrast, _validate_opposes, _validate_evidence_quotes,
    _validate_phrases_used, _validate_pronoun_rules, _maybe_split_belief,
)
from graph_module.dedup import deduplicate_graph, _text_similarity
from graph_module.store import load_graph, save_graph
from graph_module.query import (
    get_beliefs_for_topic, get_stories_for_beliefs, get_contrast_pairs,
    get_full_context, get_thinking_models, get_stories_for_topic,
)

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \033[32m✓\033[0m {name}")
    else:
        FAIL += 1
        print(f"  \033[31m✗\033[0m {name}" + (f" — {detail}" if detail else ""))


# ── Load existing graph for testing ──
print("\n\033[1m═══ LOADING EXISTING GRAPH ═══\033[0m")
old_graph = load_graph("/mnt/user-data/uploads/graph.json")
print(f"  Old graph: {old_graph.number_of_nodes()} nodes, {old_graph.number_of_edges()} edges")

# ── Unit tests: Helper functions ──
print("\n\033[1m═══ UNIT TESTS: HELPERS ═══\033[0m")

# Issue #1: Placeholder ID detection
check("#1a placeholder ID detection",
      _is_placeholder_id("snake_case_identifier"))
check("#1b placeholder ID detection",
      _is_placeholder_id("snake_case_identifier_4"))
check("#1c valid ID passes",
      not _is_placeholder_id("ai_augmentation_vs_automation"))
check("#1d short ID caught",
      _is_placeholder_id("ab"))
check("#1e unknown caught",
      _is_placeholder_id("unknown"))

# Issue #23: Topic normalization
check("#23a single topic",
      "ai_technology" in normalize_topic("AI"))
check("#23b pipe-separated",
      len(normalize_topic("Leadership | market timing | AI augmentation")) >= 2)
check("#23c pipe gives multiple buckets",
      "leadership" in normalize_topic("Leadership | AI") and "ai_technology" in normalize_topic("Leadership | AI"))
check("#23d slash-separated",
      len(normalize_topic("Hiring/talent")) >= 1)

# Issue #21: Register normalization
check("#21a valid register passes",
      _normalize_register("quiet_authority") == "quiet_authority")
check("#21b misspelling fixed",
      _normalize_register("generated_vulnerability") == "earned_vulnerability")
check("#21c pipe-separated takes first valid",
      _normalize_register("earned_vulnerability | quiet_authority") == "earned_vulnerability")
check("#21d empty defaults",
      _normalize_register("") == "quiet_authority")

# Issue #14: Rule type normalization
check("#14a valid type passes",
      _normalize_rule_type("opening") == "opening")
check("#14b pipe-separated takes first valid",
      _normalize_rule_type("opening | closing | rhythm") == "opening")
check("#14c compound normalizes",
      _normalize_rule_type("vocabulary | punctuation | pronoun | formatting") == "vocabulary")
check("#14d unknown defaults to rhetorical_move",
      _normalize_rule_type("earned cynicism") == "rhetorical_move")

# Issue #11: Personality card sanitization
check("#11a strips prompt instructions",
      "Write the personality card" not in _sanitize_personality_card(
          "You are a founder. Write the personality card now. Return ONLY the card text."))
check("#11b preserves content",
      "You are a founder" in _sanitize_personality_card(
          "You are a founder. Write the personality card now."))

# Issue #17: Compound contrast pair splitting
check("#17a simple split",
      _split_compound_contrast("X vs Y") == [("X", "Y", "X vs Y")])
check("#17b compound split",
      len(_split_compound_contrast("Outside critics vs actual users | Noise vs signal")) == 2)
check("#17c N/A rejected",
      _split_compound_contrast("N/A") == [])
check("#17d N/A (gratitude) rejected",
      _split_compound_contrast("N/A (gratitude story)") == [])

# Issue #16: Opposes validation
check("#16a generic opposes rejected",
      _validate_opposes("Metrics over narrative", "some stance") is None)
check("#16b specific opposes kept",
      _validate_opposes("Hiring based on credentials alone", "Pattern recognition beats credentials") is not None)
check("#16c empty opposes returns None",
      _validate_opposes("", "stance") is None)

# Issue #12: Evidence validation
check("#12a empty quotes stripped",
      _validate_evidence_quotes(["good quote", "", "  "], "stance") == ["good quote"])
check("#12b stance-identical stripped",
      _validate_evidence_quotes(["same as stance", "different"], "same as stance") == ["different"])
check("#12c duplicates stripped",
      len(_validate_evidence_quotes(["quote", "quote", "other"], "stance")) == 2)

# Issue #24: Phrases used validation
check("#24a anti-pattern removed",
      "Here's what people miss" not in _validate_phrases_used(
          ["Here's what people miss", "Stop X. Start Y."]))
check("#24b good phrase kept",
      "Stop X. Start Y." in _validate_phrases_used(
          ["Here's what people miss", "Stop X. Start Y."]))

# Issue #15: Pronoun rules validation
check("#15a placeholder rejected",
      _validate_pronoun_rules({"I": "when and how they use first person"}) == {})
check("#15b real rule kept",
      _validate_pronoun_rules({"I": "Used for personal origin stories and authority claims"}) != {})

# Issue #3: Junk drawer splitting
junk = {
    "topic": "ai | hiring | fundraising | sales | leadership",
    "stance": "AI augmentation beats pure automation",
    "id": "junk",
    "evidence_quotes": ["quote about ai", "quote about hiring", "quote about sales",
                         "quote about leadership", "quote about fundraising", "extra quote"],
}
check("#3 junk drawer splits into multiple beliefs",
      len(_maybe_split_belief(junk)) > 1)


# ── Integration test: Rebuild graph from old data ──
print("\n\033[1m═══ INTEGRATION: REBUILD OLD GRAPH THROUGH NEW CODE ═══\033[0m")

# Extract data from old graph to simulate re-build
beliefs_raw = []
stories_raw = []
styles_raw = []
models_raw = []
vocab_raw = {}

for nid, data in old_graph.nodes(data=True):
    ntype = data.get("node_type", "")
    if ntype == "belief":
        beliefs_raw.append({
            "id": nid.replace("belief_", ""),
            "topic": data.get("topic", ""),
            "stance": data.get("stance", ""),
            "confidence": data.get("confidence", 0.5),
            "evidence_quotes": data.get("evidence_quotes", []),
            "opposes": data.get("opposes"),
        })
    elif ntype == "story":
        stories_raw.append({
            "id": nid.replace("story_", ""),
            "title": data.get("title", ""),
            "summary": data.get("summary", ""),
            "emotional_register": data.get("emotional_register", ""),
            "contrast_pair": data.get("contrast_pair"),
            "best_used_for": data.get("best_used_for", []),
            "key_quotes": data.get("key_quotes", []),
            "engagement": data.get("engagement", 0),
            "times_used": data.get("times_used", 0),
            "virality_potential": data.get("virality_potential", "medium"),
        })
    elif ntype == "style_rule":
        styles_raw.append({
            "id": nid.replace("style_", ""),
            "rule_type": data.get("rule_type", ""),
            "description": data.get("description", ""),
            "examples": data.get("examples", []),
            "anti_pattern": data.get("anti_pattern"),
            "platform": data.get("platform", "universal"),
        })
    elif ntype == "thinking_model":
        models_raw.append({
            "id": nid.replace("model_", ""),
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "priority": data.get("priority", 0),
        })
    elif ntype == "vocabulary":
        vocab_raw = {
            "phrases_used": data.get("phrases_used", []),
            "phrases_never": data.get("phrases_never", []),
            "pronoun_rules": data.get("pronoun_rules", {}),
        }

pc = old_graph.graph.get("personality_card", "")

extracted = {
    "beliefs": beliefs_raw,
    "stories": stories_raw,
    "style_rules": styles_raw,
    "thinking_models": models_raw,
    "vocabulary": vocab_raw,
    "personality_card": pc,
}

# Build with new code (no embedder for dedup, uses difflib fallback)
new_graph = build_graph(extracted, run_post_dedup=True, embedder=None)

print(f"\n  Old: {old_graph.number_of_nodes()} nodes, {old_graph.number_of_edges()} edges")
print(f"  New: {new_graph.number_of_nodes()} nodes, {new_graph.number_of_edges()} edges")

# ── Validate all 29 issues on new graph ──
print("\n\033[1m═══ VALIDATION: ALL 29 ISSUES ON NEW GRAPH ═══\033[0m")

# Issue #1: No snake_case_identifier IDs
snake_ids = [n for n in new_graph.nodes if "snake_case_identifier" in n]
check("#1 No snake_case_identifier IDs",
      len(snake_ids) == 0,
      f"Found: {snake_ids[:5]}")

# Issue #3: No mega-node junk drawers (>2KB)
mega = [(n, len(json.dumps(dict(new_graph.nodes[n])))) for n in new_graph.nodes
        if len(json.dumps(dict(new_graph.nodes[n]))) > 2500]
check("#3 No mega-node junk drawers",
      len(mega) == 0,
      f"Found: {[(m[0], m[1]) for m in mega[:3]]}")

# Issue #4/#19: USES_STYLE edge count dramatically reduced
uses_style = [e for e in new_graph.edges(data=True) if e[2].get("edge_type") == "USES_STYLE"]
check("#4 USES_STYLE edges < 300 (was 968)",
      len(uses_style) < 300,
      f"Count: {len(uses_style)}")

# Check max USES_STYLE per story
style_per_story = Counter(e[0] for e in uses_style)
max_styles = max(style_per_story.values()) if style_per_story else 0
check("#19 Max USES_STYLE per story <= 8",
      max_styles <= 8,
      f"Max: {max_styles}")

# Issue #5/#20: BEST_FOR edges exist
best_for = [e for e in new_graph.edges(data=True) if e[2].get("edge_type") == "BEST_FOR"]
check("#5 BEST_FOR edges created",
      len(best_for) > 0,
      f"Count: {len(best_for)}")

# Issue #7: All style rules have label
styles_no_label = [n for n in new_graph.nodes
                   if new_graph.nodes[n].get("node_type") == "style_rule"
                   and not new_graph.nodes[n].get("label")]
check("#7 All style rules have label",
      len(styles_no_label) == 0,
      f"{len(styles_no_label)} missing labels")

# Issue #10: Contrast pairs under cat_contrasts
cp_under_stories = [e for e in new_graph.edges(data=True)
                    if e[0] == "cat_stories"
                    and new_graph.nodes.get(e[1], {}).get("node_type") == "contrast_pair"]
cp_under_contrasts = [e for e in new_graph.edges(data=True)
                      if e[0] == "cat_contrasts"
                      and new_graph.nodes.get(e[1], {}).get("node_type") == "contrast_pair"]
check("#10 Contrast pairs under cat_contrasts (not cat_stories)",
      len(cp_under_stories) == 0 and len(cp_under_contrasts) > 0,
      f"Under stories: {len(cp_under_stories)}, under contrasts: {len(cp_under_contrasts)}")

# Issue #11: Personality card clean
pc_new = new_graph.graph.get("personality_card", "")
check("#11 Personality card has no prompt instructions",
      "Write the personality card" not in pc_new and "Return ONLY" not in pc_new,
      f"Last 80 chars: ...{pc_new[-80:]}")

# Issue #13: Fewer style rules (duplicates removed by dedup)
style_count = sum(1 for n in new_graph.nodes if new_graph.nodes[n].get("node_type") == "style_rule")
check("#13 Style rules reduced (was 150)",
      style_count < 150,
      f"Count: {style_count}")

# Issue #14: No pipe-separated rule_types
pipe_rules = [n for n in new_graph.nodes
              if new_graph.nodes[n].get("node_type") == "style_rule"
              and "|" in new_graph.nodes[n].get("rule_type", "")]
check("#14 No pipe-separated rule_types",
      len(pipe_rules) == 0,
      f"Found: {len(pipe_rules)}")

# Issue #14b: All rule_types are valid
invalid_types = [n for n in new_graph.nodes
                 if new_graph.nodes[n].get("node_type") == "style_rule"
                 and new_graph.nodes[n].get("rule_type", "") not in VALID_RULE_TYPES]
check("#14b All rule_types are valid enum values",
      len(invalid_types) == 0,
      f"Invalid: {[new_graph.nodes[n].get('rule_type') for n in invalid_types[:5]]}")

# Issue #15: Pronoun rules validated
vocab_node = new_graph.nodes.get("vocabulary", {})
pronoun = vocab_node.get("pronoun_rules", {})
placeholder_pronouns = [k for k, v in pronoun.items() if "when and how" in str(v).lower()]
check("#15 No placeholder pronoun rules",
      len(placeholder_pronouns) == 0,
      f"Placeholders: {placeholder_pronouns}")

# Issue #16: No generic opposes
beliefs_data = [(n, new_graph.nodes[n]) for n in new_graph.nodes
                if new_graph.nodes[n].get("node_type") == "belief"]
generic_opp = [n for n, d in beliefs_data
               if (d.get("opposes") or "").lower().strip() in ("metrics over narrative", "metrics over narrative fit")]
check("#16 No generic 'Metrics over narrative' opposes",
      len(generic_opp) == 0,
      f"Found: {len(generic_opp)}")

# Issue #17: No corrupted contrast pair right fields
cp_nodes = [(n, new_graph.nodes[n]) for n in new_graph.nodes
            if new_graph.nodes[n].get("node_type") == "contrast_pair"]
bad_right = [n for n, d in cp_nodes if "|" in d.get("right", "")]
check("#17 No contrast pairs with | in right field",
      len(bad_right) == 0,
      f"Found: {len(bad_right)}")

# Issue #18: No N/A contrast pairs
na_cp = [n for n, d in cp_nodes if "n/a" in d.get("left", "").lower() or "n/a" in d.get("right", "").lower()]
check("#18 No N/A contrast pairs",
      len(na_cp) == 0,
      f"Found: {[n for n in na_cp]}")

# Issue #21: All registers valid
stories_data = [(n, new_graph.nodes[n]) for n in new_graph.nodes
                if new_graph.nodes[n].get("node_type") == "story"]
invalid_regs = [(n, d.get("emotional_register", "")) for n, d in stories_data
                if d.get("emotional_register", "") not in VALID_REGISTERS]
check("#21 All emotional registers are valid",
      len(invalid_regs) == 0,
      f"Invalid: {invalid_regs[:5]}")

# Issue #24: No anti-patterns in phrases_used
phrases_used = vocab_node.get("phrases_used", [])
anti_in_used = [p for p in phrases_used if p.lower().strip() in {
    "here's what people miss", "let me be honest", "unpopular opinion"}]
check("#24 No anti-patterns in phrases_used",
      len(anti_in_used) == 0,
      f"Found: {anti_in_used}")

# Issue #25: No zero-strength SUPPORTS edges
supports = [e for e in new_graph.edges(data=True) if e[2].get("edge_type") == "SUPPORTS"]
zero_strength = [e for e in supports if e[2].get("strength", 0) < 2]
check("#25 No SUPPORTS edges with strength < 2",
      len(zero_strength) == 0,
      f"Found: {len(zero_strength)}")

# Issue #29: Contrast pairs queryable
cp_results = get_contrast_pairs(new_graph, "AI")
check("#29 Contrast pairs are queryable",
      len(cp_results) > 0,
      f"Results for 'AI': {len(cp_results)}")

# ── Query tests ──
print("\n\033[1m═══ QUERY TESTS ═══\033[0m")

beliefs_ai = get_beliefs_for_topic(new_graph, "AI Leadership")
check("Query: AI Leadership returns beliefs",
      len(beliefs_ai) > 0,
      f"Count: {len(beliefs_ai)}")

beliefs_hiring = get_beliefs_for_topic(new_graph, "Hiring & Talent")
check("Query: Hiring returns beliefs",
      len(beliefs_hiring) > 0,
      f"Count: {len(beliefs_hiring)}")

stories_for_b = get_stories_for_beliefs(new_graph, [b.get("node_id") for b in beliefs_ai[:5]])
check("Query: Stories for AI beliefs found",
      len(stories_for_b) > 0,
      f"Count: {len(stories_for_b)}")

models = get_thinking_models(new_graph, "AI")
check("Query: Thinking models for AI found",
      len(models) > 0,
      f"Count: {len(models)}")

full_ctx = get_full_context(new_graph, "AI Leadership", "linkedin")
check("Query: Full context includes contrast_pairs",
      "contrast_pairs" in full_ctx,
      f"Keys: {list(full_ctx.keys())}")
check("Query: Full context includes thinking_models",
      "thinking_models" in full_ctx,
      f"Keys: {list(full_ctx.keys())}")

# ── Save and reload test ──
print("\n\033[1m═══ SAVE/RELOAD TEST ═══\033[0m")
save_path = "/home/claude/graph_module/test_output.json"
save_graph(new_graph, save_path)
reloaded = load_graph(save_path)
check("Save/reload preserves node count",
      reloaded.number_of_nodes() == new_graph.number_of_nodes(),
      f"Saved {new_graph.number_of_nodes()}, loaded {reloaded.number_of_nodes()}")
check("Save/reload preserves edge count",
      reloaded.number_of_edges() == new_graph.number_of_edges(),
      f"Saved {new_graph.number_of_edges()}, loaded {reloaded.number_of_edges()}")
check("Save/reload preserves personality card",
      reloaded.graph.get("personality_card", "") == new_graph.graph.get("personality_card", ""))

# ── Summary ──
print(f"\n\033[1m═══ RESULTS: {PASS} passed, {FAIL} failed ═══\033[0m")

# Print graph stats comparison
print(f"\n\033[1m═══ GRAPH COMPARISON ═══\033[0m")
def count_type(g, t):
    return sum(1 for n in g.nodes if g.nodes[n].get("node_type") == t)

def count_edge_type(g, t):
    return sum(1 for _, _, d in g.edges(data=True) if d.get("edge_type") == t)

for ntype in ["belief", "story", "style_rule", "thinking_model", "contrast_pair", "vocabulary"]:
    old_c = count_type(old_graph, ntype)
    new_c = count_type(new_graph, ntype)
    delta = new_c - old_c
    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "="
    print(f"  {ntype:20s}: {old_c:3d} → {new_c:3d} ({arrow}{abs(delta)})")

print()
for etype in ["SUPPORTS", "BEST_FOR", "USES_STYLE", "CONTRADICTS", "RELATED", "INFORMS",
              "DEMONSTRATES", "ILLUMINATES", "CONTAINS", "HAS_CATEGORY", "CONSTRAINS"]:
    old_c = count_edge_type(old_graph, etype)
    new_c = count_edge_type(new_graph, etype)
    delta = new_c - old_c
    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "="
    print(f"  {etype:20s}: {old_c:4d} → {new_c:4d} ({arrow}{abs(delta)})")

if FAIL > 0:
    sys.exit(1)