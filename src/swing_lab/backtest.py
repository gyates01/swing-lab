"""Walk-forward backtest for the momentum scanner.

Survivorship-bias-free: uses point-in-time S&P 500 membership for each
rebalance date (see ``universe.members_asof``). Prices are downloaded once
as a single batched panel and sliced locally per period.

Residual caveat: some delisted tickers have no data on Yahoo Finance at all
and drop out of scoring entirely. The membership filter removes the main
bias, but coverage of delisted names depends on the data source.
"""
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt
from datetime import datetime, date, timedelta
from pathlib import Path
from swing_lab.config import TOP_N_PICKS, REPORTS_DIR
from swing_lab.universe import fetch_sp500, fetch_sp500_historical, members_asof
from swing_lab.scanner import (
    ANCHOR_TOLERANCE_DAYS,
    fetch_close_panel,
    score_universe,
    top_n_picks,
)


def _price_asof(
    panel: pd.DataFrame,
    symbol: str,
    target_date,
    min_date=None,
    max_staleness_days: int | None = 5,
) -> float | None:
    """Last available close at or before target_date from the panel.

    Never looks ahead. ``max_staleness_days`` rejects prices that are too old
    (set to None to accept any — used for exits so a delisting's final print
    still counts as the exit price instead of silently dropping the loss).
    ``min_date`` ensures the price is from within the holding period.
    """
    if panel.empty or symbol not in panel.columns:
        return None
    s = panel[symbol].dropna()
    s = s[s.index <= pd.Timestamp(target_date)]
    if min_date is not None:
        s = s[s.index >= pd.Timestamp(min_date)]
    if s.empty:
        return None
    if max_staleness_days is not None:
        if (pd.Timestamp(target_date) - s.index[-1]).days > max_staleness_days:
            return None
    return float(s.iloc[-1])


def walk_forward(
    start: str = "2015-01-01",
    end: str = "2024-12-31",
    rebalance_weeks: int = 2,
    with_gate: bool = False,
    rank_by: str = "sector",
    top_n: int = TOP_N_PICKS,
) -> pd.DataFrame:
    """Run a walk-forward momentum backtest over the given date range.

    Parameters
    ----------
    start:
        First rebalance date (inclusive), format YYYY-MM-DD.
    end:
        Last rebalance date (inclusive), format YYYY-MM-DD.
    rebalance_weeks:
        Number of weeks between rebalance periods (default 2).
    with_gate:
        Apply the macro gate historically: each period's exposure is scaled by
        the point-in-time gate sizing (1.0 / 0.6 / 0.0). Idle capital earns 0.

    Returns
    -------
    pd.DataFrame with columns: period_start, period_end, portfolio_return,
    spy_return, n_symbols (+ gate_score, gate_sizing when with_gate).
    """
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)

    # Build rebalance date grid
    rebalance_dates = pd.date_range(start_dt, end_dt, freq=f"{rebalance_weeks}W")

    # Point-in-time membership + sector map (sectors only known for current
    # members; departed names fall into an "Unknown" bucket and are ranked
    # against each other — imperfect, but unbiased).
    hist_members = fetch_sp500_historical()
    current = fetch_sp500()
    sector_map = dict(zip(current["symbol"], current["sector"]))

    all_symbols: set[str] = set()
    for d in rebalance_dates:
        all_symbols |= members_asof(d, hist_members)

    print(f"  Universe: {len(all_symbols)} point-in-time members across the window")
    print("  Downloading full price panel (one batched call — may take a minute)…", flush=True)
    panel = fetch_close_panel(
        sorted(all_symbols | {"SPY"}),  # SPY included for the benchmark line
        start=start_dt - pd.Timedelta(days=365 + ANCHOR_TOLERANCE_DAYS),
        end=end_dt + pd.Timedelta(days=7),
    )
    print(f"  Panel: {panel.shape[1]} symbols × {panel.shape[0]} trading days")

    gate_panel = None
    if with_gate:
        from swing_lab.macro_gate import fetch_gate_panel
        print("  Downloading gate instrument panel (VIX, credit, factor ETFs)…", flush=True)
        gate_panel = fetch_gate_panel(
            start=start_dt - pd.Timedelta(days=430),
            end=end_dt + pd.Timedelta(days=7),
        )

    records = []
    n_dates = len(rebalance_dates)

    for i in range(n_dates - 1):
        entry_date = rebalance_dates[i]
        exit_date = rebalance_dates[i + 1]

        print(f"  Period {i+1}/{n_dates-1}: {entry_date.date()} → {exit_date.date()}", flush=True)

        # SPY benchmark is recorded regardless of gate state
        spy_entry = _price_asof(panel, "SPY", entry_date, max_staleness_days=5)
        spy_exit = _price_asof(panel, "SPY", exit_date, min_date=entry_date, max_staleness_days=None)
        spy_return = (
            (spy_exit - spy_entry) / spy_entry
            if spy_entry is not None and spy_exit is not None and spy_entry > 0
            else 0.0
        )

        gate_score, gate_sizing = None, 1.0
        if with_gate:
            from swing_lab.macro_gate import compute_gate_asof
            gate = compute_gate_asof(gate_panel, entry_date)
            gate_score, gate_sizing = gate["score"], gate["sizing"]
            if gate_sizing == 0.0:
                # Stand down: skip scoring entirely, sit in cash this period
                records.append({
                    "period_start": entry_date,
                    "period_end": exit_date,
                    "portfolio_return": 0.0,
                    "spy_return": spy_return,
                    "n_symbols": 0,
                    "gate_score": gate_score,
                    "gate_sizing": 0.0,
                })
                continue

        # Membership as of the entry date — no look-ahead on index composition
        members = members_asof(entry_date, hist_members)
        uni = pd.DataFrame({"symbol": sorted(members)})
        uni["sector"] = uni["symbol"].map(sector_map).fillna("Unknown")

        # Score using only data up to entry_date (no look-ahead)
        picks = score_universe(uni, end_date=entry_date, panel=panel, rank_by=rank_by)
        top = top_n_picks(picks, gate_sizing=1.0, n=top_n)

        record = {
            "period_start": entry_date,
            "period_end": exit_date,
            "portfolio_return": 0.0,
            "spy_return": spy_return,
            "n_symbols": 0,
        }
        if with_gate:
            record["gate_score"] = gate_score
            record["gate_sizing"] = gate_sizing

        if top.empty:
            records.append(record)
            continue

        # Compute equal-weighted portfolio return for the period
        symbol_returns = []
        for symbol in top["symbol"]:
            entry_price = _price_asof(panel, symbol, entry_date, max_staleness_days=5)
            # Exits accept stale prices within the period so delistings count
            # as their last traded price rather than vanishing from the average.
            exit_price = _price_asof(
                panel, symbol, exit_date,
                min_date=entry_date, max_staleness_days=None,
            )
            if entry_price is not None and exit_price is not None and entry_price > 0:
                symbol_returns.append((exit_price - entry_price) / entry_price)

        raw_return = float(np.mean(symbol_returns)) if symbol_returns else 0.0

        # Gate scaling: invested fraction earns the portfolio return, rest sits in cash
        record["portfolio_return"] = raw_return * gate_sizing
        record["n_symbols"] = len(symbol_returns)
        records.append(record)

    return pd.DataFrame(records)


def report(returns_df: pd.DataFrame, spy_prices: pd.Series | None = None) -> dict:
    """Compute backtest summary statistics from a walk-forward returns DataFrame.

    Parameters
    ----------
    returns_df:
        Output of ``walk_forward()``.
    spy_prices:
        Optional SPY price series (unused currently, reserved for future benchmark comparison).

    Returns
    -------
    dict with keys: total_return, annualized_return, sharpe, max_drawdown, hit_rate, n_periods
    """
    rets = returns_df["portfolio_return"]

    total_return = float((1 + rets).prod() - 1)

    # CAGR
    years = (
        returns_df["period_end"].iloc[-1] - returns_df["period_start"].iloc[0]
    ).days / 365.25
    annualized_return = float((1 + total_return) ** (1 / years) - 1) if years > 0 else 0.0

    # Annualised Sharpe — 26 bi-weekly periods per year
    mean_ret = float(rets.mean())
    std_ret = float(rets.std())
    sharpe = float(mean_ret / std_ret * np.sqrt(26)) if std_ret > 0 else 0.0

    # Max drawdown via cumulative wealth series
    wealth = (1 + rets).cumprod()
    max_drawdown = float((wealth / wealth.cummax() - 1).min())

    hit_rate = float((rets > 0).mean())
    n_periods = len(returns_df)

    stats = {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "hit_rate": hit_rate,
        "n_periods": n_periods,
    }

    # SPY benchmark comparison (when walk_forward provided spy_return)
    if "spy_return" in returns_df.columns:
        spy = returns_df["spy_return"]
        spy_total = float((1 + spy).prod() - 1)
        spy_annualized = float((1 + spy_total) ** (1 / years) - 1) if years > 0 else 0.0
        spy_std = float(spy.std())
        spy_wealth = (1 + spy).cumprod()
        stats.update({
            "spy_total_return": spy_total,
            "spy_annualized_return": spy_annualized,
            "spy_sharpe": float(spy.mean() / spy_std * np.sqrt(26)) if spy_std > 0 else 0.0,
            "spy_max_drawdown": float((spy_wealth / spy_wealth.cummax() - 1).min()),
            "excess_annualized": annualized_return - spy_annualized,
            "beat_spy_rate": float((rets > spy).mean()),
        })

    # Gate exposure stats (when walk_forward ran with with_gate=True)
    if "gate_sizing" in returns_df.columns:
        sizing = returns_df["gate_sizing"]
        stats.update({
            "avg_gate_sizing": float(sizing.mean()),
            "pct_full": float((sizing == 1.0).mean()),
            "pct_partial": float((sizing == 0.6).mean()),
            "pct_stand_down": float((sizing == 0.0).mean()),
        })

    return stats


def plot_equity_curve(
    returns_df: pd.DataFrame,
    out_path: Path | None = None,
    tag: str = "",
) -> Path:
    """Plot and save the portfolio equity curve.

    tag: optional filename suffix (e.g. "raw_top5") so experiment runs
    on the same day don't overwrite each other.

    Parameters
    ----------
    returns_df:
        Output of ``walk_forward()``.
    out_path:
        Destination PNG path.  Defaults to REPORTS_DIR/backtest_<today>.png.

    Returns
    -------
    Path where the PNG was saved.
    """
    if out_path is None:
        suffix = "_gated" if "gate_sizing" in returns_df.columns else ""
        if tag:
            suffix += f"_{tag}"
        out_path = REPORTS_DIR / f"backtest_{date.today().isoformat()}{suffix}.png"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    wealth = (1 + returns_df["portfolio_return"]).cumprod()
    dates = returns_df["period_start"]

    gated = "gate_sizing" in returns_df.columns
    label = "Momentum + Macro Gate" if gated else "Momentum Portfolio"

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(dates, wealth, linewidth=1.8, label=label, color="steelblue")
    if "spy_return" in returns_df.columns:
        spy_wealth = (1 + returns_df["spy_return"]).cumprod()
        ax.plot(dates, spy_wealth, linewidth=1.4, label="SPY (benchmark)",
                color="darkorange", alpha=0.85)
    if gated:
        # Shade stand-down (red) and partial (amber) periods
        for _, r in returns_df.iterrows():
            if r["gate_sizing"] == 0.0:
                ax.axvspan(r["period_start"], r["period_end"], color="red", alpha=0.10, lw=0)
            elif r["gate_sizing"] < 1.0:
                ax.axvspan(r["period_start"], r["period_end"], color="orange", alpha=0.06, lw=0)
    ax.axhline(y=1.0, color="grey", linestyle="--", linewidth=0.8)

    ax.set_title("Swing Lab — Walk-Forward Equity Curve", fontsize=14)
    ax.set_ylabel("Portfolio Value (starts at 1.0)")
    ax.set_xlabel("Date")
    ax.legend()
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    plt.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close(fig)

    return out_path
