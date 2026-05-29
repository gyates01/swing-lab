"""Walk-forward backtest for the momentum scanner."""
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt
from datetime import datetime, date, timedelta
from pathlib import Path
from swing_lab.config import TOP_N_PICKS, REPORTS_DIR
from swing_lab.universe import fetch_sp500
from swing_lab.scanner import score_universe, top_n_picks


def _get_price(symbol: str, target_date) -> float | None:
    """Fetch the last available closing price at or before target_date (±3-day window)."""
    start = target_date - timedelta(days=3)
    end = target_date + timedelta(days=4)
    hist = yf.Ticker(symbol).history(start=start, end=end)["Close"]
    if hist.empty:
        return None
    # Use last available price at or before target_date
    if hasattr(target_date, "date"):
        mask = hist.index.date <= target_date.date()
    else:
        mask = hist.index.date <= target_date
    available = hist[mask]
    return float(available.iloc[-1]) if not available.empty else float(hist.iloc[0])


def walk_forward(
    start: str = "2015-01-01",
    end: str = "2024-12-31",
    rebalance_weeks: int = 2,
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

    Returns
    -------
    pd.DataFrame with columns: period_start, period_end, portfolio_return, n_symbols
    """
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)

    # Build rebalance date grid
    rebalance_dates = pd.date_range(start_dt, end_dt, freq=f"{rebalance_weeks}W")

    # Fetch the universe once
    universe = fetch_sp500()

    records = []
    n_dates = len(rebalance_dates)

    for i in range(n_dates - 1):
        entry_date = rebalance_dates[i]
        exit_date = rebalance_dates[i + 1]

        print(f"  Period {i+1}/{n_dates-1}: {entry_date.date()} → {exit_date.date()}", flush=True)

        # Score universe using only data up to entry_date (no look-ahead)
        picks = score_universe(universe, end_date=entry_date)
        top = top_n_picks(picks, gate_sizing=1.0, n=TOP_N_PICKS)

        if top.empty:
            records.append({
                "period_start": entry_date,
                "period_end": exit_date,
                "portfolio_return": 0.0,
                "n_symbols": 0,
            })
            continue

        # Compute equal-weighted portfolio return for the period
        symbol_returns = []
        for symbol in top["symbol"]:
            entry_price = _get_price(symbol, entry_date)
            exit_price = _get_price(symbol, exit_date)
            if entry_price is not None and exit_price is not None and entry_price > 0:
                symbol_returns.append((exit_price - entry_price) / entry_price)

        portfolio_return = float(np.mean(symbol_returns)) if symbol_returns else 0.0

        records.append({
            "period_start": entry_date,
            "period_end": exit_date,
            "portfolio_return": portfolio_return,
            "n_symbols": len(symbol_returns),
        })

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

    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "hit_rate": hit_rate,
        "n_periods": n_periods,
    }


def plot_equity_curve(
    returns_df: pd.DataFrame,
    out_path: Path | None = None,
) -> Path:
    """Plot and save the portfolio equity curve.

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
        out_path = REPORTS_DIR / f"backtest_{date.today().isoformat()}.png"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    wealth = (1 + returns_df["portfolio_return"]).cumprod()
    dates = returns_df["period_start"]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(dates, wealth, linewidth=1.8, label="Momentum Portfolio", color="steelblue")
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
