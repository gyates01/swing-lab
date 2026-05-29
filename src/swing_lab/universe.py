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
