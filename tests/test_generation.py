"""Tests for the generation engine."""

import pytest


def test_aggregate_narrative_scores():
    from src.generation.voting import aggregate_narrative_scores

    scores = [
        {"safety": 8, "traction": 7, "alignment": 9, "freshness": 6},
        {"safety": 7, "traction": 8, "alignment": 8, "freshness": 7},
    ]
    result = aggregate_narrative_scores(scores)
    assert result["safety"] == 7.5
    assert result["traction"] == 7.5
    assert result["total"] > 0


def test_aggregate_empty_scores():
    from src.generation.voting import aggregate_narrative_scores

    result = aggregate_narrative_scores([])
    assert result["total"] == 0


def test_pick_winner():
    from src.generation.voting import pick_winner

    scores = {
        "narr_1": {"total": 25},
        "narr_2": {"total": 30},
        "narr_3": {"total": 22},
    }
    assert pick_winner(scores) == "narr_2"


def test_pick_winner_empty():
    from src.generation.voting import pick_winner

    assert pick_winner({}) == ""
