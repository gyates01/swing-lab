from swing_lab.recommendation import (
    reward_risk,
    validate_target,
    risks_with_target_flags,
)
from swing_lab.config import TARGET_ATR_MULTIPLE


def test_degenerate_target_recomputed_to_atr_projection():
    # model target sits ~1% above entry → recompute to entry_high + k*ATR
    target, flags = validate_target(entry_high=100.0, stop=94.0, atr=2.0, model_target=101.0)
    assert target == 100.0 + TARGET_ATR_MULTIPLE * 2.0
    assert "target_recomputed" in flags


def test_low_upside_target_recomputed():
    # 3% above entry < 5% floor → degenerate
    _, flags = validate_target(entry_high=100.0, stop=94.0, atr=2.0, model_target=103.0)
    assert "target_recomputed" in flags


def test_good_model_target_kept():
    # 12% above entry, a real level → kept unchanged
    target, flags = validate_target(entry_high=100.0, stop=94.0, atr=2.0, model_target=112.0)
    assert target == 112.0
    assert "target_recomputed" not in flags


def test_weak_reward_risk_flagged():
    # reward 7 / risk 6 = 1.17 < 2.0
    _, flags = validate_target(entry_high=100.0, stop=94.0, atr=0.5, model_target=107.0)
    assert "weak_rr" in flags


def test_healthy_reward_risk_not_flagged():
    # reward 15 / risk 6 = 2.5 >= 2.0
    _, flags = validate_target(entry_high=100.0, stop=94.0, atr=2.0, model_target=115.0)
    assert "weak_rr" not in flags


def test_atr_none_degenerate_uses_ten_pct_fallback():
    target, flags = validate_target(entry_high=100.0, stop=94.0, atr=None, model_target=100.5)
    assert target == 100.0 * 1.10
    assert "target_recomputed" in flags


def test_reward_risk_zero_when_no_risk():
    assert reward_risk(entry_high=100.0, stop=100.0, target=120.0) == 0.0


def test_weak_rr_note_appended_without_mutating_input():
    risks = ["Sector rotation risk"]
    out = risks_with_target_flags(risks, ["weak_rr"], rr=1.6)
    assert len(out) == 2
    assert "1.6:1" in out[1]
    assert risks == ["Sector rotation risk"]  # original list untouched


def test_no_note_without_weak_rr_flag():
    assert risks_with_target_flags(["X"], ["target_recomputed"], rr=3.0) == ["X"]
