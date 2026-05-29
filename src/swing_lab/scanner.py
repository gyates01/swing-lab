"""Momentum scanner: compute 12-1 month momentum, rank within sector."""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from swing_lab.config import MOMENTUM_LONG_MONTHS, MOMENTUM_SKIP_MONTHS, TOP_N_PICKS


def compute_momentum(symbol: str, end_date: datetime | None = None) -> float | None:
    """12-1 month momentum: return from 12mo ago to 1mo ago."""
    try:
        if end_date is None:
            end_date = datetime.today()
        t12 = end_date - timedelta(days=365)
        t1  = end_date - timedelta(days=30)
        hist = yf.Ticker(symbol).history(start=t12 - timedelta(days=5), end=t1 + timedelta(days=5))
        if hist.empty or len(hist) < 10:
            return None
        price_12 = hist.iloc[0]["Close"]
        price_1  = hist.iloc[-1]["Close"]
        return (price_1 - price_12) / price_12
    except Exception as e:
        print(f"  [warn] {symbol}: {e}")
        return None


def score_universe(
    universe_df: pd.DataFrame,
    end_date: datetime | None = None,
    progress=None,
) -> pd.DataFrame:
    """Score all symbols on momentum, rank percentile within sector (0–100).

    progress: optional callable(current, total, symbol) for UI progress bars.
    """
    records = []
    total = len(universe_df)
    for i, (_, row) in enumerate(universe_df.iterrows(), start=1):
        symbol = row["symbol"]
        sector = row["sector"]
        if progress:
            progress(i, total, symbol)
        momentum = compute_momentum(symbol, end_date)
        records.append({"symbol": symbol, "sector": sector, "momentum": momentum})

    df = pd.DataFrame(records)

    # Compute percentile rank within sector (only for non-NaN momentum values)
    df["score"] = np.nan
    valid_mask = df["momentum"].notna()
    if valid_mask.any():
        df.loc[valid_mask, "score"] = (
            df[valid_mask].groupby("sector")["momentum"].rank(pct=True) * 100
        )

    return df.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)


def top_n_picks(scored_df: pd.DataFrame, gate_sizing: float, n: int = TOP_N_PICKS) -> pd.DataFrame:
    """Apply gate sizing filter and return top N by score."""
    if gate_sizing == 0.0:
        return pd.DataFrame(columns=scored_df.columns.tolist() + ["gate_sizing"])

    filtered = scored_df[scored_df["score"].notna()].copy()
    top = filtered.head(n).copy()
    top["gate_sizing"] = gate_sizing
    return top.reset_index(drop=True)
