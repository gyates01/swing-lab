# Execution Page S&P 500 Benchmark — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show on the Execution page whether paper trades are beating "just holding the S&P 500" — per-position alpha plus a since-inception headline.

**Architecture:** A new pure-compute module `execution/benchmark.py` (network-free functions that take an injected `spy_price_at(date)` lookup, mirroring `paper_account_state(quote_fn=...)`), a thin `yfinance` SPY fetch helper, a one-field addition to `paper_account_state`, and rendering on `7_Execution.py` using the `st.metric` / `st.dataframe` widgets the page already uses.

**Tech Stack:** Python 3.11, pandas, yfinance, Streamlit, pytest, SQLite.

## Global Constraints

- `PAPER_STARTING_CASH = 10000.0` — import from `swing_lab.config`, never hardcode.
- SPY prices via `yfinance` only; established call style is `yf.Ticker("SPY").history(...)["Close"]`.
- yfinance `.history()` index can be timezone-aware — normalize to tz-naive dates before lookups.
- All percentages are decimal fractions internally (`0.042` = 4.2%); format at the view layer.
- Pure compute functions must take an injected `spy_price_at` lookup — no network in tested code.
- Scope is the Execution page only. Closed-trade-by-trade alpha is out of scope.

---

### Task 1: Pure benchmark compute + date/SPY lookup helpers

**Files:**
- Create: `src/swing_lab/execution/benchmark.py`
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Produces:
  - `_to_date(value) -> datetime.date | None`
  - `spy_price_lookup(closes) -> Callable[[date|str|None], float|None]`
  - `per_position_benchmark(positions: list[dict], spy_price_at, today) -> list[dict]`
  - `inception_benchmark(starting_cash, equity, inception_date, spy_price_at, today) -> dict | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_benchmark.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_benchmark.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'swing_lab.execution.benchmark'`

- [ ] **Step 3: Write the minimal implementation**

```python
# src/swing_lab/execution/benchmark.py
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_benchmark.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/execution/benchmark.py tests/test_benchmark.py
git commit -m "feat: pure SPY benchmark compute for paper positions"
```

---

### Task 2: SPY fetch helper + paper inception-date query

**Files:**
- Modify: `src/swing_lab/execution/benchmark.py`
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: `_to_date` (Task 1).
- Produces:
  - `_fetch_spy_closes(start_date) -> "pd.Series | None"`
  - `paper_inception_date(conn) -> str | None`

- [ ] **Step 1: Write the failing test (append to tests/test_benchmark.py)**

```python
def test_fetch_spy_closes_returns_none_on_error(monkeypatch):
    import swing_lab.execution.benchmark as bm

    class _Boom:
        def __init__(self, *a, **k): raise RuntimeError("offline")

    monkeypatch.setattr("yfinance.Ticker", _Boom)
    assert bm._fetch_spy_closes("2026-06-01") is None


def test_fetch_spy_closes_returns_none_for_bad_start():
    import swing_lab.execution.benchmark as bm
    assert bm._fetch_spy_closes(None) is None


def test_paper_inception_date(db_conn):
    from swing_lab.tradelog import open_trade
    from swing_lab.execution.benchmark import paper_inception_date
    assert paper_inception_date(db_conn) is None
    open_trade(db_conn, "AAPL", 10.0, 100.0, mode="paper")
    assert paper_inception_date(db_conn) is not None


def test_paper_inception_date_ignores_live(db_conn):
    from swing_lab.tradelog import open_trade
    from swing_lab.execution.benchmark import paper_inception_date
    open_trade(db_conn, "LIVE", 10.0, 100.0)  # mode defaults to 'live'
    assert paper_inception_date(db_conn) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_benchmark.py -k "fetch_spy or inception_date" -q`
Expected: FAIL — `AttributeError: module ... has no attribute '_fetch_spy_closes'`

- [ ] **Step 3: Add the implementation (append to benchmark.py)**

```python
def _fetch_spy_closes(start_date):
    """One yfinance pull of SPY daily closes from start_date..today. None on failure."""
    try:
        import yfinance as yf
        start = _to_date(start_date)
        if start is None:
            return None
        closes = yf.Ticker("SPY").history(start=start.isoformat())["Close"]
        return closes if len(closes) else None
    except Exception:
        return None


def paper_inception_date(conn) -> str | None:
    row = conn.execute(
        "SELECT MIN(opened_at) FROM trades WHERE mode = 'paper'"
    ).fetchone()
    return row[0] if row and row[0] else None
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_benchmark.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/execution/benchmark.py tests/test_benchmark.py
git commit -m "feat: SPY fetch helper + paper inception-date query"
```

---

### Task 3: Expose `opened_at` on paper positions

**Files:**
- Modify: `src/swing_lab/execution/paper_account.py` (the position dict built in `paper_account_state`)
- Test: `tests/test_paper_account.py`

**Interfaces:**
- Produces: each dict in `paper_account_state(...)["open_positions"]` now includes key `opened_at`.

- [ ] **Step 1: Write the failing test (append to tests/test_paper_account.py)**

```python
def test_position_includes_opened_at(db_conn):
    from swing_lab.execution.paper_account import paper_account_state
    _open_paper(db_conn, "AAPL", 10.0, 100.0)
    state = paper_account_state(db_conn, quote_fn=lambda s: 120.0)
    assert state["open_positions"][0]["opened_at"] is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_paper_account.py::test_position_includes_opened_at -q`
Expected: FAIL — `KeyError: 'opened_at'`

- [ ] **Step 3: Add `opened_at` to the position dict**

In `paper_account.py`, in the `positions.append({...})` block inside `paper_account_state`, add the `opened_at` field:

```python
        positions.append({
            "trade_id": t["trade_id"], "symbol": t["symbol"], "shares": t["shares"],
            "entry_price": t["entry_price"], "quote": quote,
            "market_value": value, "unrealized": value - basis,
            "opened_at": t["opened_at"],
        })
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_paper_account.py -q`
Expected: PASS (all paper_account tests)

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/execution/paper_account.py tests/test_paper_account.py
git commit -m "feat: include opened_at on paper position dicts"
```

---

### Task 4: Render benchmark on the Execution page

**Files:**
- Modify: `src/swing_lab/dashboard/pages/7_Execution.py` (the "Paper portfolio" section, lines ~96-109)

**Interfaces:**
- Consumes: `per_position_benchmark`, `inception_benchmark`, `spy_price_lookup`, `_fetch_spy_closes`, `paper_inception_date` (Tasks 1-2); `paper_account_state` positions now carry `opened_at` (Task 3).

This task changes Streamlit view code, which isn't unit-tested; verification is an import-smoke check plus a manual browser pass.

- [ ] **Step 1: Add a cached SPY fetch + imports near the top of the file**

Add to the imports block:

```python
from datetime import date
from swing_lab.config import PAPER_STARTING_CASH
from swing_lab.execution.benchmark import (
    per_position_benchmark, inception_benchmark, spy_price_lookup,
    _fetch_spy_closes, paper_inception_date,
)


@st.cache_data(ttl=3600)
def _spy_closes_cached(start_iso: str):
    return _fetch_spy_closes(start_iso)
```

- [ ] **Step 2: Replace the "Paper portfolio" section body**

Replace the current block (from `st.subheader("Paper portfolio")` through the open-positions `else: st.caption(...)`) with:

```python
st.subheader("Paper portfolio")
state = paper_account_state(conn)
m1, m2, m3 = st.columns(3)
m1.metric("Equity", f"${state['equity']:,.2f}")
m2.metric("Cash", f"${state['cash']:,.2f}")
m3.metric("Unrealized P&L", f"${state['unrealized']:,.2f}")

# --- vs S&P 500 ---
today = date.today()
inception = paper_inception_date(conn)
spy_at = spy_price_lookup(_spy_closes_cached(inception) if inception else None)

headline = inception_benchmark(PAPER_STARTING_CASH, state["equity"], inception, spy_at, today)
if headline:
    b1, b2 = st.columns(2)
    port = headline["portfolio_return"]
    spy_ret = headline["spy_return"]
    delta = headline["delta"]
    if delta is not None:
        b1.metric("Portfolio return", f"{port:+.1%}", delta=f"{delta:+.1%} vs S&P 500")
        b2.metric("S&P 500 return", f"{spy_ret:+.1%}")
    else:
        b1.metric("Portfolio return", f"{port:+.1%}")
        b2.metric("S&P 500 return", "—")
    st.caption(
        "S&P 500 baseline = the same starting cash placed in SPY on your first "
        "paper trade date and held. Your cash deploys gradually, so this slightly "
        "favors SPY (fully invested from day one)."
    )

if state["open_positions"]:
    rows = per_position_benchmark(state["open_positions"], spy_at, today)

    def _pct(v):
        return f"{v:+.1%}" if v is not None else "—"

    st.dataframe([{"symbol": p["symbol"], "shares": p["shares"],
                   "entry": p["entry_price"], "quote": p["quote"],
                   "market_value": p["market_value"], "unrealized": p["unrealized"],
                   "since entry": _pct(p["stock_return"]),
                   "SPY": _pct(p["spy_return"]),
                   "vs SPY": _pct(p["alpha"])}
                  for p in rows], use_container_width=True)
else:
    st.caption("No open paper positions.")
```

- [ ] **Step 3: Import-smoke check (catches syntax/import errors without a browser)**

Run: `uv run python -c "import ast; ast.parse(open('src/swing_lab/dashboard/pages/7_Execution.py').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Run the full test suite (no regressions)**

Run: `uv run pytest -q`
Expected: PASS (all tests green)

- [ ] **Step 5: Manual browser verification**

Run: `uv run streamlit run src/swing_lab/dashboard/Home.py` (or the project's dashboard entrypoint), open the **Execution** page, and confirm:
- The "Portfolio return / S&P 500 return" metric pair renders, delta arrow green when ahead.
- The open-positions table shows `since entry`, `SPY`, `vs SPY` columns with signed percentages.
- With no open positions, only the headline (or nothing, if no paper trades) shows — no crash.

- [ ] **Step 6: Commit**

```bash
git add src/swing_lab/dashboard/pages/7_Execution.py
git commit -m "feat: show vs-S&P 500 benchmark on Execution page"
```

---

## Self-Review

**Spec coverage:**
- A (per-position alpha) → Task 1 (`per_position_benchmark`) + Task 4 table columns. ✓
- C (inception headline) → Task 1 (`inception_benchmark`) + Task 4 metric pair. ✓
- `opened_at` needed by A → Task 3. ✓
- One SPY fetch, cached, nearest-prior-day lookup → Task 2 (`_fetch_spy_closes`) + Task 1 (`spy_price_lookup`). ✓
- Documented simplification caption → Task 4 Step 2. ✓
- Edge cases (no positions / no trades / SPY offline / weekend entry / entry today) → Task 1 & 2 tests + Task 4 conditionals. ✓
- Testing module → Tasks 1-2 (`tests/test_benchmark.py`). ✓

**Placeholder scan:** No TBD/TODO; all code shown in full. ✓

**Type consistency:** `spy_price_at` lookup name, `per_position_benchmark(positions, spy_price_at, today)`, `inception_benchmark(starting_cash, equity, inception_date, spy_price_at, today)`, and dict keys (`stock_return`, `spy_return`, `alpha`, `portfolio_return`, `delta`, `opened_at`) are used identically across tasks. ✓
