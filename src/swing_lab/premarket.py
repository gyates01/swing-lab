"""Pre-market gap scanner: find gappers across a watchlist or via screener.

Two data-source strategies:

1. **Finviz screener (preferred)** — scrapes finviz.com's pre-market tab for
   stocks with gap %, price, volume. Fast and purpose-built for this task.
2. **yfinance watchlist** — fetches pre-market prices per-ticker for a given
   universe (e.g. S&P 500). Slower but no external scraping dependency.

News catalysts are sourced from Finviz news blurb per ticker.
"""
import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

import pandas as pd
import yfinance as yf

from swing_lab.config import DATA_DIR

# ── Constants ────────────────────────────────────────────────────────────────

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_DEFAULT_MIN_GAP_PCT = 5.0       # gap up at least 5%
_DEFAULT_MIN_PRICE = 3.0         # price above $3
_DEFAULT_MIN_VOLUME = 50_000     # pre-market volume > 50K
_DEFAULT_TOP_N = 10              # return top N gappers

# Trading hours (ET)
_PREMARKET_START_HOUR = 4    # 4:00 AM ET pre-market opens
_PREMARKET_END_HOUR = 9      # 9:30 AM ET regular open

# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class GapCandidate:
    """One pre-market gap candidate."""
    ticker: str
    gap_pct: float           # e.g. 5.2 means +5.2%
    price: float             # latest pre-market price
    volume: int              # pre-market volume
    prev_close: float        # previous day's close
    catalyst: str = ""       # news catalyst blurb (one line)
    sector: str = ""         # GICS sector

@dataclass
class PremarketScanResult:
    """Full scan result."""
    candidates: list[GapCandidate] = field(default_factory=list)
    scanned_at: str = ""     # ISO timestamp
    source: str = ""         # "finviz" or "yfinance"
    total_scanned: int = 0
    errors: list[str] = field(default_factory=list)


# ── Finviz screener ──────────────────────────────────────────────────────────

_FINVIZ_SCREENER_URL = (
    "https://finviz.com/screener.ashx?v=111"
    "&f=sh_price_above{min_price},sh_vol_{min_vol},ta_gap_{min_gap}"
    "&ft=4"  # ft=4 = pre-market
)

_FINVIZ_PATTERN_TABLE = re.compile(
    r'<table[^>]*class="[^"]*screener_data[^"]*"[^>]*>.*?</table>',
    re.DOTALL | re.IGNORECASE,
)
_FINVIZ_PATTERN_ROWS = re.compile(
    r'<tr[^>]*>.*?</tr>',
    re.DOTALL,
)
_FINVIZ_PATTERN_CELL = re.compile(
    r'<td[^>]*>(.*?)</td>',
    re.DOTALL,
)


def _fetch_finviz_screener(min_gap: float, min_price: float,
                           min_volume: int) -> str | None:
    """Fetch the Finviz pre-market screener HTML. Returns raw HTML or None."""
    vol_str = f"{min_volume // 1000}k" if min_volume >= 1000 else str(min_volume)
    # Finviz uses 'k' suffix for volume (e.g. 50k)
    gap_str = f"gap_{min_gap}" if min_gap == int(min_gap) else f"gap_{min_gap:.1f}"
    url = (
        f"https://finviz.com/screener.ashx?v=111"
        f"&f=sh_price_above{min_price},sh_vol_{vol_str},ta_{gap_str}"
        f"&ft=4"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None


def _parse_finviz_table(html: str) -> list[dict]:
    """Parse Finviz screener HTML table into row dicts.

    Returns list of {col_name: value} where col_name is from Finviz's
    column headers (Ticker, Price, Change, Volume, etc.).
    """
    # Find the screener data table
    table_match = _FINVIZ_PATTERN_TABLE.search(html)
    if not table_match:
        # Try alternate structure: screener_body
        alt = re.search(
            r'<div[^>]*id="screener_cont"[^>]*>.*?</div>\s*</div>',
            html, re.DOTALL,
        )
        if not alt:
            return []
        # Re-search inside the container
        table_match = _FINVIZ_PATTERN_TABLE.search(alt.group())
        if not table_match:
            return []

    table_html = table_match.group()

    # Extract rows
    rows = _FINVIZ_PATTERN_ROWS.findall(table_html)

    # First row is headers
    if not rows:
        return []
    header_cells = _FINVIZ_PATTERN_CELL.findall(rows[0])
    headers = [re.sub(r'<[^>]+>', '', c).strip() for c in header_cells]

    parsed = []
    for row_html in rows[1:]:
        cells = _FINVIZ_PATTERN_CELL.findall(row_html)
        if len(cells) < len(headers):
            continue
        row = {}
        for i, h in enumerate(headers):
            row[h] = re.sub(r'<[^>]+>', '', cells[i]).strip()
        parsed.append(row)

    return parsed


def _parse_gap_value(text: str) -> float:
    """Parse a Finviz gap/change value like '+5.32%' or '-1.23%' to float."""
    cleaned = text.strip().replace("%", "").replace("+", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_volume_value(text: str) -> int:
    """Parse a Finviz volume value like '1.2M', '500K', '123,456' to int."""
    text = text.strip().replace(",", "")
    if not text or text == "-":
        return 0
    multipliers = {"B": 1_000_000_000, "M": 1_000_000, "K": 1_000}
    suffix = text[-1].upper()
    if suffix in multipliers:
        try:
            return int(float(text[:-1]) * multipliers[suffix])
        except ValueError:
            return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _fetch_catalyst(ticker: str) -> str:
    """Fetch a one-line news catalyst for a ticker from Finviz."""
    url = f"https://finviz.com/quote.ashx?t={ticker.lower()}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        # News table
        news_match = re.search(
            r'<table[^>]*class="fullview-news-outer"[^>]*>.*?<tr[^>]*>(.*?)</tr>',
            html, re.DOTALL,
        )
        if news_match:
            first_row = news_match.group(1)
            # Extract the link text
            link_match = re.search(r'<a[^>]*>(.*?)</a>', first_row)
            if link_match:
                return link_match.group(1).strip()
        return ""
    except Exception:
        return ""


def scan_finviz(
    min_gap_pct: float = _DEFAULT_MIN_GAP_PCT,
    min_price: float = _DEFAULT_MIN_PRICE,
    min_volume: int = _DEFAULT_MIN_VOLUME,
    top_n: int = _DEFAULT_TOP_N,
    include_catalysts: bool = True,
) -> PremarketScanResult:
    """Scan pre-market gappers via Finviz screener.

    Returns the top N gappers sorted by gap % descending.
    """
    result = PremarketScanResult(
        scanned_at=datetime.now(timezone.utc).isoformat(),
        source="finviz",
    )

    html = _fetch_finviz_screener(min_gap_pct, min_price, min_volume)
    if not html:
        result.errors.append("Failed to fetch Finviz screener page")
        return result

    rows = _parse_finviz_table(html)
    if not rows:
        result.errors.append("No pre-market gapper data found on Finviz")
        return result

    result.total_scanned = len(rows)

    # Map Finviz columns to our schema
    candidates = []
    for row in rows:
        try:
            gap_str = row.get("Change", "0%")
            gap = _parse_gap_value(gap_str)
            # Keep only gap-ups
            if gap < min_gap_pct:
                continue

            price_str = row.get("Price", "0")
            try:
                price = float(price_str.replace(",", ""))
            except ValueError:
                price = 0.0

            vol_str = row.get("Volume", "0")
            volume = _parse_volume_value(vol_str)

            ticker = row.get("Ticker", "").strip()

            candidates.append(GapCandidate(
                ticker=ticker,
                gap_pct=gap,
                price=price,
                volume=volume,
                prev_close=round(price / (1 + gap / 100), 2) if price > 0 else 0.0,
            ))
        except Exception:
            continue

    # Sort by gap % descending, take top N
    candidates.sort(key=lambda c: c.gap_pct, reverse=True)
    candidates = candidates[:top_n]

    # Fetch catalysts if requested
    if include_catalysts and candidates:
        for i, c in enumerate(candidates):
            if i < top_n:
                c.catalyst = _fetch_catalyst(c.ticker)

    result.candidates = candidates
    return result


# ── yfinance watchlist scanner ───────────────────────────────────────────────

def _get_daily_data(ticker: str) -> dict | None:
    """Fetch daily price data for a ticker via yfinance.

    Returns dict with keys: prev_close, prev_date
    or None on failure.
    """
    try:
        daily = yf.Ticker(ticker).history(period="5d", interval="1d")
        if daily.empty or len(daily) < 2:
            return None
        return {
            "prev_close": float(daily["Close"].iloc[-2]),
            "prev_date": str(daily.index[-2].date()),
        }
    except Exception:
        return None


def scan_yfinance_watchlist(
    symbols: list[str],
    min_gap_pct: float = _DEFAULT_MIN_GAP_PCT,
    min_price: float = _DEFAULT_MIN_PRICE,
    min_volume: int = _DEFAULT_MIN_VOLUME,
    top_n: int = _DEFAULT_TOP_N,
) -> PremarketScanResult:
    """Scan pre-market gappers via per-ticker yfinance calls.

    Slower than Finviz but doesn't require scraping.
    Best used with a focused watchlist (20-50 tickers).
    """
    result = PremarketScanResult(
        scanned_at=datetime.now(timezone.utc).isoformat(),
        source="yfinance",
        total_scanned=len(symbols),
    )

    candidates = []
    for i, sym in enumerate(symbols):
        print(f"  Scanning {i+1}/{len(symbols)}: {sym}", end="\r", flush=True)
        daily = _get_daily_data(sym)
        if not daily:
            continue

        prev_close = daily["prev_close"]
        if prev_close <= 0:
            continue

        # Get the latest available price (regular market close is the
        # most reliable proxy when actual pre-market data isn't available
        # through the batch API)
        try:
            hist = yf.Ticker(sym).history(period="1d", interval="5m", prepost=True)
            if hist.empty:
                continue
            pre_price = float(hist["Close"].iloc[-1])
            pre_volume = int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0
        except Exception:
            continue

        gap = (pre_price - prev_close) / prev_close * 100
        if gap < min_gap_pct:
            continue
        if pre_price < min_price:
            continue
        if pre_volume < min_volume:
            continue

        candidates.append(GapCandidate(
            ticker=sym,
            gap_pct=round(gap, 2),
            price=pre_price,
            volume=pre_volume,
            prev_close=prev_close,
        ))

    print(" " * 60, end="\r", flush=True)

    candidates.sort(key=lambda c: c.gap_pct, reverse=True)
    result.candidates = candidates[:top_n]
    return result


# ── Combined scanner ─────────────────────────────────────────────────────────

def scan_premarket(
    min_gap_pct: float = _DEFAULT_MIN_GAP_PCT,
    min_price: float = _DEFAULT_MIN_PRICE,
    min_volume: int = _DEFAULT_MIN_VOLUME,
    top_n: int = _DEFAULT_TOP_N,
    symbols: list[str] | None = None,
    include_catalysts: bool = True,
) -> PremarketScanResult:
    """Run pre-market gap scan with fallback: Finviz first, then yfinance.

    Args:
        symbols: Optional watchlist for yfinance fallback. If None and Finviz
                 fails, returns empty result.
    """
    result = scan_finviz(
        min_gap_pct=min_gap_pct,
        min_price=min_price,
        min_volume=min_volume,
        top_n=top_n,
        include_catalysts=include_catalysts,
    )

    # If Finviz returned data, use it
    if result.candidates:
        return result

    # Fallback to yfinance if we have a watchlist
    if symbols:
        return scan_yfinance_watchlist(
            symbols=symbols,
            min_gap_pct=min_gap_pct,
            min_price=min_price,
            min_volume=min_volume,
            top_n=top_n,
        )

    return result


# ── Output helpers ───────────────────────────────────────────────────────────

def format_scan_result(result: PremarketScanResult, verbose: bool = False) -> str:
    """Format a pre-market scan result for terminal output."""
    lines = []
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    lines.append(f"PREMARKET GAP SCANNER — {date_str}")
    lines.append(f"Source: {result.source} | Candidates: {len(result.candidates)}/{result.total_scanned}")
    lines.append("")

    if not result.candidates:
        lines.append("No gappers found matching the criteria.")
        if result.errors:
            lines.append(f"Errors: {'; '.join(result.errors)}")
        return "\n".join(lines)

    # Header
    lines.append(f"{'#':>3}  {'Ticker':>6}  {'Gap%':>7}  {'Price':>8}  {'Volume':>10}  {'Prev Close':>10}  Catalyst")
    lines.append(f"{'─'*3}  {'─'*6}  {'─'*7}  {'─'*8}  {'─'*10}  {'─'*10}  {'─'*40}")

    for i, c in enumerate(result.candidates, start=1):
        gap_str = f"+{c.gap_pct:.1f}%" if c.gap_pct >= 0 else f"{c.gap_pct:.1f}%"
        vol_str = _format_volume(c.volume)
        catalyst = c.catalyst[:40] if c.catalyst else "—"
        lines.append(
            f"{i:>3}  {c.ticker:>6}  {gap_str:>7}  ${c.price:<6.2f}  {vol_str:>10}  ${c.prev_close:<8.2f}  {catalyst}"
        )

    return "\n".join(lines)


def format_scan_json(result: PremarketScanResult) -> str:
    """Format scan result as JSON for machine consumption (Telegram, etc.)."""
    return json.dumps({
        "scanned_at": result.scanned_at,
        "source": result.source,
        "total_scanned": result.total_scanned,
        "candidates": [
            {
                "ticker": c.ticker,
                "gap_pct": round(c.gap_pct, 2),
                "price": round(c.price, 2),
                "volume": c.volume,
                "prev_close": round(c.prev_close, 2),
                "catalyst": c.catalyst,
            }
            for c in result.candidates
        ],
        "errors": result.errors,
    }, indent=2)


def _format_volume(vol: int) -> str:
    """Format volume as human-readable string."""
    if vol >= 1_000_000_000:
        return f"{vol/1_000_000_000:.1f}B"
    if vol >= 1_000_000:
        return f"{vol/1_000_000:.1f}M"
    if vol >= 1_000:
        return f"{vol/1_000:.0f}K"
    return str(vol)


# ── JSON persistence ─────────────────────────────────────────────────────────

def save_scan_result(result: PremarketScanResult) -> str:
    """Save scan result to a date-stamped JSON file in results/.

    Returns the file path.
    """
    from pathlib import Path
    results_dir = Path(__file__).resolve().parent.parent.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = results_dir / f"premarket_{today}.json"
    path.write_text(format_scan_json(result), encoding="utf-8")
    return str(path)
