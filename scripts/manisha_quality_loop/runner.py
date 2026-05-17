"""Batch-A-only pipeline wrapper for the iterative quality loop.

Reuses production pipeline functions but skips Batch B, multi-source
orchestration, and convergence regen. Carry-forward semantics let passing
posts skip regeneration between iterations.
"""

from __future__ import annotations

import logging
from typing import Iterable

from src.batch.state import AmplifiedPost, BatchState
from src.batch.pack_generator import (
    transpose,
    _enforce_word_count,
    _extract_forbidden_tokens,
    _scan_batch_a_for_token_leaks,
)
from src.batch.amplifier import amplify_batch_v2

logger = logging.getLogger(__name__)


def generate_batch_a(
    state: BatchState,
    source_post: str,
    dissection: dict,
    llm_gen,
    posts_to_keep: list[tuple[str, AmplifiedPost]] | None = None,
    pack_number: int = 0,
) -> list[AmplifiedPost]:
    """Produce 3 Batch A posts. Carry forward passing posts unchanged; generate
    fresh posts for missing slots. Run forbidden-token leak check on new posts
    only. Amplify all 3 (carried + new) so the amplifier judgment is consistent
    across the pack.
    """
    posts_to_keep = posts_to_keep or []
    kept = [p for _, p in posts_to_keep]
    n_needed = 3 - len(kept)

    new_posts: list[AmplifiedPost] = []
    if n_needed > 0:
        prior_args = [p.argument_compressed for p in kept if p.argument_compressed]
        new_posts = transpose(
            llm_gen, source_post, dissection, mode="A", state=state,
            prior_arguments=prior_args, post_count=n_needed,
            pack_number=pack_number,
        )

        forbidden = _extract_forbidden_tokens(dissection, source_post)
        for p in new_posts:
            leaks = _scan_batch_a_for_token_leaks(p, forbidden)
            if leaks:
                p.quality_flags["batch_a_source_token_leak"] = leaks
                logger.info("[loop_runner] %s: token leak detected: %s", p.label, leaks)

        new_posts = [_enforce_word_count(p, state, llm=llm_gen) for p in new_posts]

    combined = kept + new_posts
    combined = combined[:3]

    # Amplify the full set (carried posts get re-diagnosed against current peers;
    # the amplifier's _should_apply_batch_a_variant decides whether to keep or
    # replace each opener based on gates).
    if combined:
        combined = amplify_batch_v2(
            llm_gen, combined, state,
            source_dissection=dissection, never_replace=True,
        )

    # Relabel sequentially: A1, A2, A3.
    for i, p in enumerate(combined[:3], 1):
        p.label = f"A{i}"
        p.batch = "A"

    return combined[:3]
