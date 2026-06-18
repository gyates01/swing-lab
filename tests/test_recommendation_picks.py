import pandas as pd

from swing_lab.recommendation import n_picks_to_synthesize


def _df(scores):
    return pd.DataFrame({
        "symbol": [f"S{i}" for i in range(len(scores))],
        "blended_score": scores,
    })


def test_empty_returns_zero():
    assert n_picks_to_synthesize(_df([])) == 0


def test_single_candidate_returns_one():
    assert n_picks_to_synthesize(_df([85.0])) == 1


def test_second_below_threshold_returns_one():
    assert n_picks_to_synthesize(_df([85.0, 60.0]), second_min_score=70.0) == 1


def test_second_clears_threshold_returns_two():
    assert n_picks_to_synthesize(_df([85.0, 75.0]), second_min_score=70.0) == 2


def test_second_exactly_at_threshold_returns_two():
    assert n_picks_to_synthesize(_df([85.0, 70.0]), second_min_score=70.0) == 2


def test_never_exceeds_cap():
    assert n_picks_to_synthesize(_df([90.0, 88.0, 85.0]), second_min_score=70.0, cap=2) == 2


def test_missing_second_score_treated_as_zero():
    assert n_picks_to_synthesize(_df([85.0, None]), second_min_score=70.0) == 1
