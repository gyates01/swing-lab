import datetime as dt
import pandas as pd
import pytest

from swing_lab.execution.benchmark import (
    _to_date, spy_price_lookup, per_position_benchmark, inception_benchmark,
)


def _lookup(mapping):
    """Fake spy_price_at backed by a {date_str: price} dict."""
    def _at(d):
        key = _to_date(d)
        return mapping.get(key.isoformat()) if key else None
    return _at


def test_to_date_parses_iso_timestamp():
    assert _to_date("2026-06-12T13:45:00+00:00") == dt.date(2026, 6, 12)
    assert _to_date("2026-06-12") == dt.date(2026, 6, 12)
    assert _to_date(None) is None


def test_spy_price_lookup_resolves_weekend_to_prior_close():
    # 2026-06-12 is a Friday; 2026-06-13/14 are the weekend.
    closes = pd.Series(
        [100.0, 101.0],
        index=pd.to_datetime(["2026-06-11", "2026-06-12"]),
    )
    at = spy_price_lookup(closes)
    assert at("2026-06-12") == 101.0
    assert at("2026-06-14") == 101.0          # Sunday -> Friday close
    assert at("2026-06-10") is None           # before first close


def test_spy_price_lookup_none_series_yields_none():
    at = spy_price_lookup(None)
    assert at("2026-06-12") is None


def test_per_position_alpha_beats_and_lags():
    positions = [
        {"symbol": "WIN", "entry_price": 100.0, "quote": 110.0, "opened_at": "2026-06-01"},
        {"symbol": "LAG", "entry_price": 100.0, "quote": 102.0, "opened_at": "2026-06-01"},
    ]
    at = _lookup({"2026-06-01": 100.0, "2026-06-26": 105.0})  # SPY +5%
    rows = per_position_benchmark(positions, at, "2026-06-26")
    win = next(r for r in rows if r["symbol"] == "WIN")
    lag = next(r for r in rows if r["symbol"] == "LAG")
    assert win["stock_return"] == pytest.approx(0.10)
    assert win["spy_return"] == pytest.approx(0.05)
    assert win["alpha"] == pytest.approx(0.05)
    assert lag["alpha"] == pytest.approx(-0.03)


def test_per_position_quote_none_uses_entry_price():
    positions = [{"symbol": "X", "entry_price": 100.0, "quote": None, "opened_at": "2026-06-01"}]
    at = _lookup({"2026-06-01": 100.0, "2026-06-26": 105.0})
    rows = per_position_benchmark(positions, at, "2026-06-26")
    assert rows[0]["stock_return"] == pytest.approx(0.0)
    assert rows[0]["alpha"] == pytest.approx(-0.05)


def test_per_position_missing_spy_is_none():
    positions = [{"symbol": "X", "entry_price": 100.0, "quote": 110.0, "opened_at": "2026-06-01"}]
    at = _lookup({})  # no SPY data
    rows = per_position_benchmark(positions, at, "2026-06-26")
    assert rows[0]["stock_return"] == pytest.approx(0.10)
    assert rows[0]["spy_return"] is None
    assert rows[0]["alpha"] is None


def test_inception_benchmark_delta():
    at = _lookup({"2026-06-01": 100.0, "2026-06-26": 104.0})  # SPY +4%
    result = inception_benchmark(10000.0, 11000.0, "2026-06-01", at, "2026-06-26")
    assert result["portfolio_return"] == pytest.approx(0.10)
    assert result["spy_return"] == pytest.approx(0.04)
    assert result["delta"] == pytest.approx(0.06)


def test_inception_benchmark_none_when_no_trades():
    at = _lookup({"2026-06-26": 104.0})
    assert inception_benchmark(10000.0, 10000.0, None, at, "2026-06-26") is None


def test_inception_benchmark_missing_spy_keeps_portfolio_return():
    at = _lookup({})
    result = inception_benchmark(10000.0, 11000.0, "2026-06-01", at, "2026-06-26")
    assert result["portfolio_return"] == pytest.approx(0.10)
    assert result["spy_return"] is None
    assert result["delta"] is None
