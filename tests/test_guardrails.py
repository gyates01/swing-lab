from datetime import datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_RTH = datetime(2026, 6, 17, 12, 0, tzinfo=_ET)       # Wednesday noon ET
_WEEKEND = datetime(2026, 6, 20, 12, 0, tzinfo=_ET)   # Saturday noon ET


def _state(**kw):
    base = {"cash": 9000.0, "equity": 10000.0, "open_symbols": set(),
            "todays_order_count": 0, "todays_notional": 0.0}
    base.update(kw)
    return base


def _prop(**kw):
    base = {"mode": "paper", "side": "buy", "symbol": "AAPL", "shares": 5.0,
            "est_price": 100.0, "est_notional": 500.0, "reason": "open_rec"}
    base.update(kw)
    return base


def test_clean_buy_passes():
    from swing_lab.execution import guardrails
    assert guardrails.check(_prop(), _state(), now_et=_RTH) == []


def test_kill_switch_blocks_everything(monkeypatch):
    from swing_lab.execution import guardrails
    monkeypatch.setattr(guardrails.config, "EXECUTION_KILL_SWITCH", True)
    assert guardrails.check(_prop(), _state(), now_et=_RTH) == ["kill switch engaged"]


def test_outside_rth_blocks():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(), _state(), now_et=_WEEKEND)
    assert "outside regular trading hours" in v


def test_per_position_cap():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(est_notional=900.0), _state(), now_et=_RTH)  # >8% of 10000
    assert "position exceeds max position size" in v


def test_cash_reserve():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(est_notional=500.0), _state(cash=1000.0), now_et=_RTH)
    assert "insufficient cash reserve" in v  # 1000-500=500 < 0.10*10000=1000


def test_max_open_positions():
    from swing_lab.execution import guardrails
    state = _state(open_symbols={f"S{i}" for i in range(8)})
    v = guardrails.check(_prop(symbol="ZZZZ"), state, now_et=_RTH)
    assert "max open positions reached" in v


def test_adding_to_existing_position_ignores_max_open():
    from swing_lab.execution import guardrails
    state = _state(open_symbols={f"S{i}" for i in range(8)})
    v = guardrails.check(_prop(symbol="S0"), state, now_et=_RTH)  # already held
    assert "max open positions reached" not in v


def test_daily_order_count():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(), _state(todays_order_count=12), now_et=_RTH)
    assert any("daily order count" in x for x in v)


def test_daily_notional():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(est_notional=500.0), _state(todays_notional=2800.0), now_et=_RTH)
    assert "daily notional cap exceeded" in v  # 2800+500=3300 > 0.30*10000=3000


def test_sells_exempt_from_buy_only_checks():
    from swing_lab.execution import guardrails
    state = _state(cash=0.0, open_symbols={f"S{i}" for i in range(8)})
    v = guardrails.check(_prop(side="sell", symbol="ZZZZ", est_notional=500.0),
                         state, now_et=_RTH)
    assert v == []  # no cash-reserve / max-positions / per-position for sells


def test_price_above_entry_zone_blocks():
    from swing_lab.execution import guardrails
    # entry_high=100, 2% tolerance -> ceiling 102; price 105 is above -> flag
    v = guardrails.check(_prop(est_price=105.0, entry_high=100.0), _state(), now_et=_RTH)
    assert any("entry zone" in x for x in v)


def test_price_within_tolerance_passes():
    from swing_lab.execution import guardrails
    # price 101 <= 102 ceiling -> no flag (a little chasing is allowed)
    v = guardrails.check(_prop(est_price=101.0, entry_high=100.0), _state(), now_et=_RTH)
    assert not any("entry zone" in x for x in v)


def test_price_below_entry_zone_passes():
    from swing_lab.execution import guardrails
    # buying cheaper than the zone is never a problem
    v = guardrails.check(_prop(est_price=80.0, entry_high=100.0), _state(), now_et=_RTH)
    assert not any("entry zone" in x for x in v)


def test_no_entry_high_skips_zone_check():
    from swing_lab.execution import guardrails
    # recs without levels carry no entry_high -> zone check is a no-op
    v = guardrails.check(_prop(est_price=9999.0), _state(), now_et=_RTH)
    assert not any("entry zone" in x for x in v)


def test_sell_exempt_from_entry_zone():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(side="sell", est_price=105.0, entry_high=100.0),
                         _state(), now_et=_RTH)
    assert not any("entry zone" in x for x in v)
