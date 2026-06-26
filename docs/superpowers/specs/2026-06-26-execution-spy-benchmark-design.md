# Execution Page — "vs S&P 500" Benchmark

**Date:** 2026-06-26
**Status:** Approved design, ready for implementation plan
**Scope:** Execution page only (`7_Execution.py`), paper portfolio

## Goal

Let the user see whether their paper trades are actually beating "just holding the
index." Two additions to the existing **Paper portfolio** block on the Execution page:

- **A — Per-position alpha:** each open position shows its return since entry next to
  SPY's return over the *same* holding window, and the difference.
- **C — Inception headline:** a single compact line comparing total portfolio return
  vs SPY since the date of the first paper trade.

Closed-trade-by-trade benchmarking is explicitly **out of scope** (would belong on the
Trade Log page). Realized P&L from closed trades still flows into the inception headline
via current equity.

## Data available (no new tables)

- `paper_account_state(conn)` returns `{cash, equity, unrealized, open_positions, open_symbols}`.
  Each open position has `symbol, shares, entry_price, quote, market_value, unrealized`.
- The `trades` table records `opened_at`, `closed_at`, `entry_price`, `exit_price`, `mode`.
- `PAPER_STARTING_CASH` is the paper account's starting equity (`config.py`).
- `yfinance` is already a dependency (used by scanner/technicals) — SPY prices are free.

There is **no stored equity-over-time history**; equity is computed on the fly. This is why
a full equity-curve-vs-SPY chart was rejected in favor of A + C.

## Architecture

### New module: `src/swing_lab/execution/benchmark.py`

Pure, network-free compute functions plus one thin fetch helper. The compute functions take
an injected `spy_price_at(date) -> float | None` lookup so they are unit-testable with no
network — mirroring the existing `paper_account_state(quote_fn=...)` pattern.

```
def per_position_benchmark(positions, spy_price_at, today) -> list[dict]
    # For each open position dict (must include opened_at, entry_price, quote):
    #   stock_return = quote / entry_price - 1            (quote falls back to entry_price)
    #   spy_ret      = spy_price_at(today) / spy_price_at(opened_at) - 1
    #   alpha        = stock_return - spy_ret
    # Returns the position dict enriched with {stock_return, spy_return, alpha}.
    # If either SPY price is missing -> spy_return/alpha = None (render as "—").

def inception_benchmark(starting_cash, equity, inception_date, spy_price_at, today) -> dict | None
    # portfolio_return = equity / starting_cash - 1
    # spy_return       = spy_price_at(today) / spy_price_at(inception_date) - 1
    # delta            = portfolio_return - spy_return
    # Returns {portfolio_return, spy_return, delta}. Returns None if inception_date is None
    # (no paper trades) or SPY price missing.

def _fetch_spy_closes(start_date) -> "pd.Series | None"
    # One yfinance pull of SPY daily closes from start_date..today, indexed by date.
    # Returns None on any failure (offline / empty). Caller wraps in st.cache_data.

def spy_price_lookup(series) -> callable
    # Returns spy_price_at(date): nearest prior trading-day close (asof / ffill).
    # Weekends, holidays, and "today before close" resolve to the last available close.
```

### Edit: `src/swing_lab/execution/paper_account.py`

Add `opened_at` to each position dict in `paper_account_state` (the value is already present
in the underlying `_open_paper_trades` query). Needed so the benchmark knows each position's
entry date. One-line addition.

### Edit: `src/swing_lab/dashboard/pages/7_Execution.py`

In the **Paper portfolio** section:

1. Determine `inception_date = min(opened_at)` across **all** paper trades (open + closed) —
   small query, or reuse a helper. Determine the SPY fetch window start = inception_date.
2. Fetch SPY closes once via a page-level `@st.cache_data(ttl=3600)` wrapper around
   `_fetch_spy_closes`, then build `spy_price_at = spy_price_lookup(series)`.
3. Render the **inception headline** above the table using existing theme helpers
   (`metric_html` row or a single colored line): Portfolio %, SPY %, vs SPY (delta).
4. Add `since entry`, `SPY`, and `vs SPY` columns to the open-positions dataframe, formatted
   as signed percentages.
5. Caption noting the simplification (see below).

## The inception baseline (documented simplification)

SPY's inception number = "what if `PAPER_STARTING_CASH` was placed in SPY on the date of the
first paper trade and held." The paper portfolio deploys cash gradually, so SPY is fully
invested from day one while idle cash waited — this **slightly favors SPY**. A precise
time-weighted / cash-flow-matched comparison is intentionally deferred; a one-line caption on
the page discloses the simplification.

## Edge cases

- **No open positions:** show the inception headline only (realized P&L still counts).
- **No paper trades at all:** `inception_date is None` -> render nothing benchmark-related.
- **SPY fetch fails / offline:** `_fetch_spy_closes` returns None -> headline and columns show
  `—`; the page never crashes (consistent with existing quote-failure degradation).
- **Entry today / pre-close:** SPY window ≈ 0 -> ~0% return, valid.
- **Weekend/holiday entry date:** nearest prior trading-day close via `asof`/ffill.

## Testing — `tests/test_benchmark.py`

Unit tests with a fake `spy_price_at` (a dict-backed lookup), no network:

- `per_position_benchmark` computes stock return, SPY return, and alpha correctly.
- Position whose stock beat SPY -> positive alpha; one that lagged -> negative alpha.
- Missing SPY price -> `spy_return`/`alpha` are None.
- `inception_benchmark` computes portfolio vs SPY delta correctly.
- `inception_benchmark` returns None when `inception_date is None`.
- `spy_price_lookup` resolves a weekend date to the prior Friday close.

## Files

| File | Change |
|------|--------|
| `src/swing_lab/execution/benchmark.py` | **new** — pure compute + thin SPY fetch |
| `src/swing_lab/execution/paper_account.py` | add `opened_at` to position dicts |
| `src/swing_lab/dashboard/pages/7_Execution.py` | headline + table columns + cached SPY fetch |
| `tests/test_benchmark.py` | **new** — unit tests for pure functions |

## Out of scope

- Closed-trade-by-trade alpha (future, on Trade Log page).
- Stored equity-history table / full equity-curve chart.
- Time-weighted / cash-flow-matched benchmark math.
