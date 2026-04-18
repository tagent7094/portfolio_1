"""Smoke test for the new PipelineConfig/StageConfig dataclasses."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.customizer.customizer_engine import (
    PipelineConfig, StageConfig, MAX_LLM_CALLS_PER_RUN, _estimate_llm_calls,
)

cfg = PipelineConfig()
print(f"Default: n_variants={cfg.variants.n}, top_k={cfg.refine.top_k}, openings={cfg.opening_massacre.n}")
print(f"Expected calls (5 agents, 5 opening agents): {_estimate_llm_calls(cfg, 5, 5)}")

legacy_skip = PipelineConfig.from_legacy(num_variants=3, skip_voting=True)
print(f"Legacy skip_voting: audience_vote.enabled={legacy_skip.audience_vote.enabled}, refine.enabled={legacy_skip.refine.enabled}")

huge = PipelineConfig(variants=StageConfig(n=10), opening_massacre=StageConfig(n=15))
print(f"Huge config: {_estimate_llm_calls(huge, 5, 5)} calls (cap={MAX_LLM_CALLS_PER_RUN})")

# Disable stages and check budget changes
no_vote = PipelineConfig()
no_vote.audience_vote.enabled = False
no_vote.refine.enabled = False
print(f"No-vote mode: {_estimate_llm_calls(no_vote, 5, 5)} calls")

print("OK")
