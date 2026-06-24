from swing_lab.technicals import format_levels_for_prompt


def _levels():
    return {
        "price_52w_high": 110.0,
        "price_52w_low": 70.0,
        "ma_20": 98.0, "ma_50": 95.0, "ma_200": 88.0,
        "atr_14": 2.0,
        "swing_highs": [(108.0, 10)],
        "swing_lows": [(95.0, 20)],
    }


def test_projected_target_line_present():
    out = format_levels_for_prompt(_levels(), current_price=100.0)
    assert "Projected swing target" in out


def test_guidance_no_longer_caps_at_52w_high():
    out = format_levels_for_prompt(_levels(), current_price=100.0)
    assert "nearest swing high or 52w high" not in out
    assert "do NOT cap the target at the prior high" in out


def test_no_projected_line_without_atr():
    levels = _levels()
    levels["atr_14"] = None
    out = format_levels_for_prompt(levels, current_price=100.0)
    assert "Projected swing target" not in out
