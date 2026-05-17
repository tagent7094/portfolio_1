# Blog Prompts v2 — SEO-Optimized Pipeline

These prompts rewrite the original blog generation pipeline to produce SEO-rankable content while preserving founder voice. Every prompt has been changed; two new prompts have been added.

## Honest expectations first

**These prompts will NOT make every blog rank #1 for every search.** That's impossible. SEO ranking depends on:

- **Domain authority** (~30% of ranking) — built over months/years
- **Backlinks** (~25% of ranking) — built through distribution
- **Topical authority** (~15%) — requires 20+ blogs on related topics
- **On-page SEO** (~15%) — *this is what these prompts fix*
- **User signals** (~10%) — engagement, CTR, time on page
- **Technical SEO** (~5%) — site speed, schema, mobile

These prompts fix the **on-page SEO** portion. That's the 15% you control with prompts. The other 85% requires a content strategy, distribution, time, and consistency.

**Realistic outcome with these prompts:**
- Month 1-3: Blog ranks page 3-5 for primary keyword, page 1-2 for very long-tail variants
- Month 4-6: With 8-12 related blogs, main blog rises to page 2
- Month 6-12: With backlinks + engagement, blog can reach page 1 for primary keyword
- Year 2+: Some posts consistently rank top 3

Anyone who tells you a prompt gets you to #1 immediately is selling fantasy.

## New pipeline architecture

```
1. topic_discovery       (SEO-aware topic scoring)
2. keyword_research      [NEW] — primary keyword + long-tails + PAA targets
3. serp_analysis         [NEW] — competition analysis + structural reqs
4. transcript_structure  (cleans YouTube captions)
5. transcript_analysis   (SEO-aware theme extraction)
6. narrative_mining      (SEO-aware angle selection)
7. outline_generation    (MANDATORY H2 structure + SEO inputs)
8. section_draft         (per-section SEO obligations)
9. narrative_draft       (full-blog generator with SEO-aware formats)
10. seo_optimize         (final auditor with PASS/FAIL gates)
11. voice_validation_blog (voice + SEO-awareness)

If seo_optimize FAILS → loop back to narrative_draft with specific fixes
```

## What changed in each file

### NEW FILES

**`keyword_research.txt`** — Runs FIRST in the SEO branch. Identifies the primary keyword, 5-8 long-tail variations, 8-15 related entities the blog must cover, search intent classification, and 5-8 People Also Ask question targets. Without this step, downstream prompts are SEO-blind.

**`serp_analysis.txt`** — Runs AFTER keyword research. Analyzes likely top 10 competitors, identifies table-stakes coverage, content gaps to exploit, and structural elements needed to beat current rankers. Determines realistic word count target.

### REWRITTEN FILES

**`topic_discovery.txt`** — Added 5-dimension scoring (founder relevance, timeliness, search opportunity, differentiation, audience value) with search_opportunity weighted 1.5x. Topics now scored for SEO viability, not just founder fit.

**`transcript_structure.txt`** — Minor improvement. Added segment_id, has_quotable_moment flag, timestamp ranges. Mostly preserves the working prompt.

**`transcript_analysis.txt`** — Added SEO-relevant fields: seo_potential rating on themes, could_anchor_blog flag on quotes, seo_opportunity rating on contrarian positions, searchable_questions extraction, named_entities for topical authority.

**`narrative_mining.txt`** — Added SEO inputs (from keyword_research) AND SERP competition inputs (from serp_analysis). Angles now scored on both ranking_confidence AND voice_authenticity_confidence with composite scoring.

**`outline_generation.txt`** — Major rewrite. Mandatory H2 structure (minimum 5), mandatory FAQ section for informational intent, mandatory structured elements (min 3 of 5), keyword density targets, related entity distribution requirements, internal link placeholder marking. Outline now includes seo_validation block that must pass before returning.

**`section_draft.txt`** — Added per-section SEO requirements: primary keyword usage (0-2x), required related entities, structured element type, PAA question handling (direct 40-60 word answer first), internal link anchors. Sections now flag SEO integration failures for outline revision.

**`narrative_draft.txt`** — Full SEO-aware format-specific structures for all 5 formats (thought_leadership, behind_the_scenes, listicle, how_to, comparison). Mandatory output rules (minimum 5 H2s, 2 PAA H2s, 4-8 primary keyword uses, all related entities present, 3+ structured elements). Built-in self-audit with regeneration trigger if below threshold.

**`seo_optimize.txt`** — Complete redesign. Was a metadata-only optimizer; now a strict 23-point publication gate with critical / topical / structural / semantic categories. Outputs publication_decision with regeneration_target if blog fails. Includes schema_recommendations for technical SEO.

**`voice_validation_blog.txt`** — Added posture_score dimension (operator-inside vs commentator-outside). Added AI slop detection list. Added section-level analysis identifying strongest/weakest sections for targeted regeneration. Failure thresholds tightened.

## Critical SEO failures these prompts now prevent

### Failures in the OLD pipeline:
1. **Zero H2 subheadings** in 1,500-word blogs — Google can't parse structure
2. **Missing related entities** (e.g., blog about JEE never mentioned "IIT")
3. **Primary keyword used 3 times in 1,500 words** — under-optimized
4. **No FAQ section** — kills "People Also Ask" panel eligibility
5. **No lists or comparison tables** — kills featured snippet eligibility
6. **Meta description over 155 chars** — gets truncated in Google
7. **Zero internal link opportunities** marked
8. **Post-hoc SEO optimization** — too late, content structure already locked
9. **No competition awareness** — competing blindly against established sites
10. **No PAA question targeting** — missed massive visibility opportunity

### Fixed in v2:
- H2 structure is MANDATORY (minimum 5) — `outline_generation.txt`, `narrative_draft.txt`
- Related entities tracked from `keyword_research.txt` through to `seo_optimize.txt` audit
- Primary keyword density target (4-8 occurrences) enforced in narrative_draft
- FAQ section mandatory for informational intent — `outline_generation.txt`
- Minimum 3 structured elements required — `outline_generation.txt`, `seo_optimize.txt` audit
- Meta description 140-155 char range enforced
- Internal link placeholders required in every section
- Keyword research runs FIRST, SEO inputs flow through every downstream prompt
- Competition analyzed in `serp_analysis.txt` before outline creation
- PAA targets become H2 questions (mandatory minimum 2) — `outline_generation.txt`

## How to integrate into your Python pipeline

In your `corpus_reader.py` and blog session orchestrator, the loading order needs to update:

```python
# OLD pipeline order
TOPIC_DISCOVERY -> TRANSCRIPT_ANALYSIS -> NARRATIVE_MINING -> 
OUTLINE_GENERATION -> SECTION_DRAFT (or NARRATIVE_DRAFT) -> 
SEO_OPTIMIZE -> VOICE_VALIDATION_BLOG

# NEW pipeline order
TOPIC_DISCOVERY -> 
KEYWORD_RESEARCH -> 
SERP_ANALYSIS -> 
TRANSCRIPT_STRUCTURE (if from YouTube) -> 
TRANSCRIPT_ANALYSIS -> 
NARRATIVE_MINING -> 
OUTLINE_GENERATION -> 
SECTION_DRAFT (or NARRATIVE_DRAFT) -> 
SEO_OPTIMIZE -> 
  if FAIL -> loop back to NARRATIVE_DRAFT with specific fixes
  if PASS -> VOICE_VALIDATION_BLOG -> publish
```

Two new variables flow through the pipeline now:
- `seo_inputs` (from keyword_research)
- `serp_competition` (from serp_analysis)

Make sure these are passed into `outline_generation`, `section_draft`, `narrative_draft`, and `seo_optimize`.

## Cost/latency impact

Adding 2 new LLM calls (keyword_research + serp_analysis) adds:
- ~$0.05-0.10 per blog in additional LLM cost
- ~30-60 seconds in additional generation time

The seo_optimize prompt now does more work (23 checks vs 5), adding:
- ~$0.05 per blog
- ~15-30 seconds

Total: ~$0.15 and ~60-90 seconds added per blog. The ROI is the difference between a blog that ranks (and earns organic traffic for years) and a blog that doesn't (and earns nothing).

## What the prompts do NOT do

Be clear about what's outside scope:

- **Backlink building** — needs distribution strategy
- **Domain authority** — needs time and consistent publishing
- **Internal link wiring** — prompts mark placeholders but actual linking is implementation-side
- **Schema markup injection** — prompts recommend, implementation must inject
- **Image SEO** — alt text, file naming not covered
- **Site speed / Core Web Vitals** — site infrastructure
- **Indexing requests** — submit sitemap via Google Search Console

These are the other 85% mentioned at the top. The prompts handle the 15% of on-page SEO. The rest is strategic content/distribution work.

## Recommended next steps

1. Drop these files into `src/blog/prompts/` (replace existing)
2. Add the 2 new prompts to the pipeline orchestrator
3. Update `corpus_reader.py` to load `keyword_research.txt` and `serp_analysis.txt`
4. Add the new variables (`seo_inputs`, `serp_competition`) to the prompt context
5. Wire the regeneration loop: if `seo_optimize.publication_decision.should_publish == false`, regenerate via `narrative_draft` with `specific_regeneration_instructions` passed in
6. Test on a low-stakes topic first to validate the pipeline
7. Iterate based on actual ranking outcomes over 4-8 weeks

## Voice + SEO are NOT in conflict

The most important architectural commitment in these prompts: **a blog can be SEO-perfect AND voice-perfect simultaneously**. They are not tradeoffs. The prompts demand both.

If a section feels forced because an SEO requirement is fighting voice authenticity, that's a sign the outline is wrong — not that SEO must lose. Re-outline to find natural placement for keywords and entities.

If the founder voice gets stripped to fit SEO templates, the blog reads as generic — and ironically loses on the user signals (time on page, scroll depth) that Google increasingly weights.

The system optimizes for both. Validation gates check both. Regeneration loops protect both.
