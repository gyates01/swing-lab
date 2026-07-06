"""Fetch and cache the S&P 500 universe."""
import io
import urllib.request
import pandas as pd
from pathlib import Path
from datetime import datetime
from swing_lab.config import SP500_URL, DATA_DIR

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Use CSV as the cache format — no extra deps (parquet requires pyarrow/fastparquet)
_CACHE_FILE = DATA_DIR / "universe.csv"

# Point-in-time S&P 500 membership (for survivorship-bias-free backtests).
# Source: github.com/fja05680/sp500 — daily membership snapshots 1996→present.
_HISTORICAL_FILE = DATA_DIR / "sp500_historical.csv"
_HISTORICAL_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv"
)


def fetch_sp500() -> pd.DataFrame:
    """Return DataFrame with columns [symbol, sector]. Caches daily to data/universe.csv."""
    cache = _CACHE_FILE

    # Return cached version if it was written today
    if cache.exists():
        mtime_date = datetime.fromtimestamp(cache.stat().st_mtime).date()
        if mtime_date == datetime.today().date():
            return pd.read_csv(cache)

    # Fetch from Wikipedia with a browser-like User-Agent to avoid 403
    req = urllib.request.Request(SP500_URL, headers=_HEADERS)
    with urllib.request.urlopen(req) as resp:
        html_bytes = resp.read()
    tables = pd.read_html(io.BytesIO(html_bytes))
    df = tables[0]

    # Rename columns
    df = df.rename(columns={"Symbol": "symbol", "GICS Sector": "sector"})

    # Fix tickers like BRK.B → BRK-B
    df["symbol"] = df["symbol"].str.replace(".", "-", regex=False)

    # Ensure data dir exists and save
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df[["symbol", "sector"]].to_csv(cache, index=False)

    return df[["symbol", "sector"]]


def fetch_sp500_historical() -> pd.DataFrame:
    """Return point-in-time membership snapshots: columns [date, tickers].

    Downloads once and caches to data/sp500_historical.csv (~5 MB).
    """
    if not _HISTORICAL_FILE.exists():
        print("  Downloading historical S&P 500 membership (one-time, ~5 MB)…")
        req = urllib.request.Request(_HISTORICAL_URL, headers=_HEADERS)
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _HISTORICAL_FILE.write_bytes(data)
    df = pd.read_csv(_HISTORICAL_FILE, parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def members_asof(as_of, hist_df: pd.DataFrame | None = None) -> set[str]:
    """Return the S&P 500 member set as of a date (latest snapshot ≤ as_of).

    Tickers are normalized to yfinance style (BRK.B → BRK-B).
    Falls back to the earliest snapshot if as_of predates the dataset.
    """
    if hist_df is None:
        hist_df = fetch_sp500_historical()
    as_of = pd.Timestamp(as_of)
    eligible = hist_df[hist_df["date"] <= as_of]
    row = eligible.iloc[-1] if not eligible.empty else hist_df.iloc[0]
    return {
        t.strip().replace(".", "-")
        for t in str(row["tickers"]).split(",")
        if t.strip()
    }
