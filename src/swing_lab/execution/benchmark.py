"""Benchmark paper trades against SPY. Pure compute + a thin yfinance fetch."""
from __future__ import annotations

import datetime as _dt
from typing import Callable


def _to_date(value) -> _dt.date | None:
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    return _dt.date.fromisoformat(str(value)[:10])


def spy_price_lookup(closes) -> Callable:
    """Return spy_price_at(date) -> close on `date` or nearest prior trading day.

    `closes` is a pandas Series of SPY closes indexed by date. None/empty -> a
    lookup that always returns None.
    """
    if closes is None or len(closes) == 0:
        return lambda d: None
    import pandas as pd
    s = closes.copy()
    idx = pd.to_datetime(s.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    s.index = idx.normalize()
    s = s.sort_index()

    def _at(d):
        date = _to_date(d)
        if date is None:
            return None
        val = s.asof(pd.Timestamp(date))
        return None if pd.isna(val) else float(val)

    return _at


def per_position_benchmark(positions: list[dict], spy_price_at, today) -> list[dict]:
    spy_now = spy_price_at(today)
    out = []
    for p in positions:
        entry = p.get("entry_price")
        mark = p.get("quote") if p.get("quote") is not None else entry
        stock_return = (mark / entry - 1) if entry else None
        spy_then = spy_price_at(p.get("opened_at"))
        spy_return = (spy_now / spy_then - 1) if (spy_now and spy_then) else None
        alpha = (stock_return - spy_return) if (stock_return is not None and spy_return is not None) else None
        out.append({**p, "stock_return": stock_return, "spy_return": spy_return, "alpha": alpha})
    return out


def inception_benchmark(starting_cash, equity, inception_date, spy_price_at, today) -> dict | None:
    if inception_date is None or not starting_cash:
        return None
    portfolio_return = equity / starting_cash - 1
    spy_then = spy_price_at(inception_date)
    spy_now = spy_price_at(today)
    if spy_then and spy_now:
        spy_return = spy_now / spy_then - 1
        delta = portfolio_return - spy_return
    else:
        spy_return = delta = None
    return {"portfolio_return": portfolio_return, "spy_return": spy_return, "delta": delta}
