"""Momentum scanner: compute 12-1 month momentum, rank within sector.

Price fetching is batched via ``yf.download`` (one HTTP call for the whole
universe) instead of ~500 sequential per-ticker requests.
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from swing_lab.config import MOMENTUM_LONG_MONTHS, MOMENTUM_SKIP_MONTHS, TOP_N_PICKS

# Max calendar-day gap allowed between the t-12mo / t-1mo anchors and the
# nearest actual trading bar. Prevents short histories (recent IPOs/spinoffs)
# from masquerading as 12-1 momentum.
ANCHOR_TOLERANCE_DAYS = 14


def fetch_close_panel(symbols, start, end) -> pd.DataFrame:
    """Batched download of (auto-adjusted) close prices.

    Returns DataFrame with index = trading dates (tz-naive), columns = symbols.
    Symbols with no data are simply absent / all-NaN.
    """
    symbols = list(symbols)
    if not symbols:
        return pd.DataFrame()
    data = yf.download(
        symbols,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"].copy()
    else:
        # Single symbol: flat columns
        close = data[["Close"]].copy()
        close.columns = [symbols[0]]
    if close.index.tz is not None:
        close.index = close.index.tz_localize(None)
    return close


def compute_momentum_from_series(close: pd.Series, end_date) -> float | None:
    """12-1 momentum from a close-price series: return from ~12mo ago to ~1mo ago.

    Returns None when the series does not actually cover the 12-month window
    (within ANCHOR_TOLERANCE_DAYS at both ends).
    """
    close = close.dropna()
    if close.empty:
        return None

    end_ts = pd.Timestamp(end_date)
    t12 = end_ts - pd.Timedelta(days=365)
    t1 = end_ts - pd.Timedelta(days=30)

    window = close[(close.index >= t12 - pd.Timedelta(days=ANCHOR_TOLERANCE_DAYS))
                   & (close.index <= t1)]
    if len(window) < 2:
        return None

    # Both anchors must be matched by a real trading bar nearby.
    if abs((window.index[0] - t12).days) > ANCHOR_TOLERANCE_DAYS:
        return None
    if abs((window.index[-1] - t1).days) > ANCHOR_TOLERANCE_DAYS:
        return None

    price_12 = float(window.iloc[0])
    price_1 = float(window.iloc[-1])
    if price_12 <= 0:
        return None
    return (price_1 - price_12) / price_12


def compute_momentum(symbol: str, end_date: datetime | None = None) -> float | None:
    """12-1 month momentum for a single symbol (one network call).

    Canonical single-ticker entry point (used by the analyst agent).
    Bulk scoring should go through ``score_universe`` which batches downloads.
    """
    try:
        if end_date is None:
            end_date = datetime.today()
        start = end_date - timedelta(days=365 + ANCHOR_TOLERANCE_DAYS)
        hist = yf.Ticker(symbol).history(start=start, end=end_date)
        if hist.empty:
            return None
        close = hist["Close"]
        if close.index.tz is not None:
            close = close.copy()
            close.index = close.index.tz_localize(None)
        return compute_momentum_from_series(close, end_date)
    except Exception as e:
        print(f"  [warn] {symbol}: {e}")
        return None


def score_universe(
    universe_df: pd.DataFrame,
    end_date: datetime | None = None,
    progress=None,
    panel: pd.DataFrame | None = None,
    rank_by: str = "sector",
) -> pd.DataFrame:
    """Score all symbols on momentum, percentile-ranked 0–100.

    rank_by: "sector" ranks momentum within each GICS sector (sector-neutral,
             the live default); "raw" ranks across the whole universe, letting
             the portfolio concentrate in the strongest sectors.
    progress: optional callable(current, total, symbol) for UI progress bars.
    panel: optional pre-fetched close-price panel (from ``fetch_close_panel``).
           When omitted, one batched download covers the whole universe.
    """
    if end_date is None:
        end_date = datetime.today()
    end_ts = pd.Timestamp(end_date)

    symbols = universe_df["symbol"].tolist()
    total = len(universe_df)

    if panel is None:
        if progress:
            progress(0, total, "downloading price history (batched)…")
        panel = fetch_close_panel(
            symbols,
            start=end_ts - pd.Timedelta(days=365 + ANCHOR_TOLERANCE_DAYS),
            end=end_ts,
        )

    records = []
    for i, (_, row) in enumerate(universe_df.iterrows(), start=1):
        symbol = row["symbol"]
        sector = row["sector"]
        if progress:
            progress(i, total, symbol)
        momentum = None
        if not panel.empty and symbol in panel.columns:
            momentum = compute_momentum_from_series(panel[symbol], end_date)
        records.append({"symbol": symbol, "sector": sector, "momentum": momentum})

    df = pd.DataFrame(records)

    # Percentile rank (only for non-NaN momentum values)
    df["score"] = np.nan
    valid_mask = df["momentum"].notna()
    if valid_mask.any():
        if rank_by == "raw":
            df.loc[valid_mask, "score"] = (
                df.loc[valid_mask, "momentum"].rank(pct=True) * 100
            )
        else:
            df.loc[valid_mask, "score"] = (
                df[valid_mask].groupby("sector")["momentum"].rank(pct=True) * 100
            )

    return df.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)


def top_n_picks(scored_df: pd.DataFrame, gate_sizing: float, n: int = TOP_N_PICKS) -> pd.DataFrame:
    """Apply gate sizing filter and return top N by score."""
    if gate_sizing == 0.0:
        return pd.DataFrame(columns=scored_df.columns.tolist() + ["gate_sizing"])

    filtered = scored_df[scored_df["score"].notna()].copy()
    filtered = filtered.sort_values("score", ascending=False)
    top = filtered.head(n).copy()
    top["gate_sizing"] = gate_sizing
    return top.reset_index(drop=True)
