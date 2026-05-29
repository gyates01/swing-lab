"""
Phase 1: Factor Exposure Analysis of Current Holdings
------------------------------------------------------
Answers: "What factor exposures do my current picks have?"

Data sources:
  - Wealthfront Stock Investing Account: hardcoded from Dec 2025 PDF statement
    (not yet imported into Finance Tracker DB)
  - Robinhood: queried from Finance Tracker DB (latest snapshot)

Enrichment via yfinance: sector, marketCap, trailingPE, priceToBook, beta, 12-1m momentum
Output: printed report + written back into the Obsidian strategy note
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

import yfinance as yf
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from swing_lab.config import OBSIDIAN_STRATEGY_NOTE

FINANCE_TRACKER_DB = Path("H:/Other/Claude Projects/Finance Tracker/backend/finance.db")

# --- Wealthfront Stock Investing Account (Dec 31, 2025 statement) ---
# Supply Chain / Logistics + Biotech / Pharma
WEALTHFRONT_STOCKS = {
    # Supply Chain / Logistics
    "BMY":  {"shares": 0.20146, "price": 53.94,   "value": 10.87, "account": "Wealthfront Stocks"},
    "CHRW": {"shares": 0.03036, "price": 160.76,  "value": 4.88,  "account": "Wealthfront Stocks"},
    "CSX":  {"shares": 0.12916, "price": 36.25,   "value": 4.68,  "account": "Wealthfront Stocks"},
    "EXPD": {"shares": 0.03155, "price": 149.01,  "value": 4.70,  "account": "Wealthfront Stocks"},
    "FDX":  {"shares": 0.01697, "price": 288.86,  "value": 4.90,  "account": "Wealthfront Stocks"},
    "INCY": {"shares": 0.09012, "price": 98.77,   "value": 8.90,  "account": "Wealthfront Stocks"},
    "JBHT": {"shares": 0.02484, "price": 194.34,  "value": 4.83,  "account": "Wealthfront Stocks"},
    "LLY":  {"shares": 0.00929, "price": 1074.68, "value": 9.98,  "account": "Wealthfront Stocks"},
    "MRK":  {"shares": 0.10202, "price": 105.26,  "value": 10.74, "account": "Wealthfront Stocks"},
    "NSC":  {"shares": 0.01602, "price": 288.72,  "value": 4.63,  "account": "Wealthfront Stocks"},
    "ODFL": {"shares": 0.03078, "price": 156.80,  "value": 4.83,  "account": "Wealthfront Stocks"},
    "UNP":  {"shares": 0.02001, "price": 231.32,  "value": 4.63,  "account": "Wealthfront Stocks"},
    "UPS":  {"shares": 0.04966, "price": 99.19,   "value": 4.93,  "account": "Wealthfront Stocks"},
    "VRTX": {"shares": 0.02186, "price": 453.36,  "value": 9.91,  "account": "Wealthfront Stocks"},
    "XPO":  {"shares": 0.03354, "price": 135.91,  "value": 4.56,  "account": "Wealthfront Stocks"},
}


def load_robinhood_holdings():
    """Pull latest Robinhood holdings from Finance Tracker DB."""
    if not FINANCE_TRACKER_DB.exists():
        print(f"[warn] Finance Tracker DB not found at {FINANCE_TRACKER_DB}")
        return {}
    db = sqlite3.connect(str(FINANCE_TRACKER_DB))
    cur = db.cursor()
    cur.execute("""
        SELECT h.symbol, h.shares, h.price, h.market_value, h.date
        FROM holdings h
        WHERE h.account = 'assets:investments:robinhood'
          AND h.date = (
            SELECT MAX(h2.date) FROM holdings h2
            WHERE h2.account = h.account AND h2.symbol = h.symbol
          )
        ORDER BY h.market_value DESC
    """)
    rows = cur.fetchall()
    db.close()
    return {
        r[0]: {"shares": r[1], "price": r[2], "value": r[3],
                "date": r[4], "account": "Robinhood"}
        for r in rows
    }


def fetch_yf_info(symbol: str) -> dict:
    """Fetch fundamentals and sector info for one symbol."""
    try:
        t = yf.Ticker(symbol)
        info = t.info
        return {
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap"),
            "pe": info.get("trailingPE"),
            "pb": info.get("priceToBook"),
            "beta": info.get("beta"),
            "div_yield": info.get("dividendYield"),
        }
    except Exception as e:
        print(f"  [warn] {symbol}: {e}")
        return {"sector": "Unknown", "industry": "Unknown",
                "market_cap": None, "pe": None, "pb": None,
                "beta": None, "div_yield": None}


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
    except Exception:
        return None


def size_bucket(market_cap) -> str:
    if market_cap is None:
        return "Unknown"
    if market_cap >= 10e9:
        return "Large-cap"
    if market_cap >= 2e9:
        return "Mid-cap"
    return "Small-cap"


def format_pct(v, decimals=1):
    if v is None:
        return "N/A"
    return f"{v * 100:.{decimals}f}%"


def format_float(v, decimals=1):
    if v is None:
        return "N/A"
    return f"{v:.{decimals}f}x"


def main():
    print("=" * 65)
    print("SWING LAB — PHASE 1: FACTOR EXPOSURE ANALYSIS")
    print(f"As of: {datetime.today().strftime('%Y-%m-%d')}")
    print("=" * 65)

    # Build unified holdings dict
    holdings = dict(WEALTHFRONT_STOCKS)
    rb_holdings = load_robinhood_holdings()
    for sym, data in rb_holdings.items():
        if sym in holdings:
            holdings[sym]["value"] = holdings[sym].get("value", 0) + data["value"]
        else:
            holdings[sym] = data

    total_value = sum(h["value"] for h in holdings.values() if h["value"])
    symbols = list(holdings.keys())

    print(f"\nPortfolio: {len(symbols)} positions, total tracked value ${total_value:,.2f}")
    print("\nFetching yfinance data (this may take ~30s)...\n")

    # Enrich
    rows = []
    for sym in symbols:
        h = holdings[sym]
        val = h.get("value", 0) or 0
        pct = val / total_value if total_value else 0
        info = fetch_yf_info(sym)
        mom = compute_momentum(sym)
        rows.append({
            "symbol": sym,
            "account": h.get("account", "?"),
            "value": val,
            "pct": pct,
            "sector": info["sector"],
            "industry": info["industry"],
            "market_cap": info["market_cap"],
            "size": size_bucket(info["market_cap"]),
            "pe": info["pe"],
            "pb": info["pb"],
            "beta": info["beta"],
            "div_yield": info["div_yield"],
            "momentum_12_1": mom,
        })
        print(f"  {sym:5s} | {info['sector'][:28]:28s} | beta={format_float(info['beta'])} | "
              f"mom12-1={format_pct(mom)} | {pct*100:.1f}% of portfolio")

    df = pd.DataFrame(rows)

    # ── 1. Sector concentration ────────────────────────────────────────
    print("\n\n1. SECTOR CONCENTRATION")
    print("-" * 45)
    sector_pct = df.groupby("sector")["pct"].sum().sort_values(ascending=False)
    for sector, pct in sector_pct.items():
        bar = "█" * int(pct * 40)
        print(f"  {sector:<35} {pct*100:5.1f}%  {bar}")

    # ── 2. Size tilt ───────────────────────────────────────────────────
    print("\n\n2. SIZE TILT")
    print("-" * 45)
    size_pct = df.groupby("size")["pct"].sum().sort_values(ascending=False)
    for size, pct in size_pct.items():
        print(f"  {size:<15} {pct*100:5.1f}%")
    print("  (S&P 500 benchmark: ~87% large-cap, ~11% mid, ~2% small)")

    # ── 3. Value vs. growth ────────────────────────────────────────────
    print("\n\n3. VALUE vs. GROWTH TILT")
    print("-" * 45)
    pe_vals = df["pe"].dropna()
    pb_vals = df["pb"].dropna()
    wt_pe = np.average(df["pe"].fillna(0), weights=df["pct"]) if pe_vals.any() else None
    wt_pb = np.average(df["pb"].fillna(0), weights=df["pct"]) if pb_vals.any() else None
    print(f"  Weighted avg P/E: {wt_pe:.1f}x  (S&P 500 ~22x)")
    print(f"  Weighted avg P/B: {wt_pb:.1f}x  (S&P 500 ~4.5x)")
    if wt_pe and wt_pe < 18:
        print("  Tilt: VALUE (below-market P/E)")
    elif wt_pe and wt_pe > 28:
        print("  Tilt: GROWTH (above-market P/E)")
    else:
        print("  Tilt: BLEND")

    # ── 4. Momentum ────────────────────────────────────────────────────
    print("\n\n4. MOMENTUM TILT (12-1 month returns)")
    print("-" * 45)
    mom_df = df[df["momentum_12_1"].notna()].copy()
    mom_df = mom_df.sort_values("momentum_12_1", ascending=False)
    for _, r in mom_df.iterrows():
        bar = ("▲" if r["momentum_12_1"] >= 0 else "▼") * min(20, int(abs(r["momentum_12_1"]) * 20))
        print(f"  {r['symbol']:5s} {format_pct(r['momentum_12_1'], 1):>8s}  {bar}")
    valid_moms = mom_df["momentum_12_1"]
    wt_mom = np.average(valid_moms, weights=mom_df["pct"]) if not valid_moms.empty else None
    print(f"\n  Portfolio weighted avg momentum: {format_pct(wt_mom, 1)}")
    print("  (SPY 12-1m benchmark for comparison)")

    # ── 5. Beta ────────────────────────────────────────────────────────
    print("\n\n5. BETA (MARKET SENSITIVITY)")
    print("-" * 45)
    beta_df = df[df["beta"].notna()]
    wt_beta = np.average(beta_df["beta"], weights=beta_df["pct"]) if not beta_df.empty else None
    print(f"  Portfolio weighted beta: {wt_beta:.2f}x")
    print("  (Beta 1.0 = moves with market, <1.0 = lower volatility)")
    for _, r in df[df["beta"].notna()].sort_values("beta", ascending=False).iterrows():
        print(f"  {r['symbol']:5s}  beta={r['beta']:.2f}")

    # ── 6. Concentration risk ──────────────────────────────────────────
    print("\n\n6. CONCENTRATION RISK")
    print("-" * 45)
    top5 = df.nlargest(5, "pct")
    print(f"  Top 5 positions: {top5['pct'].sum()*100:.1f}% of portfolio")
    for _, r in top5.iterrows():
        print(f"    {r['symbol']:5s}  {r['pct']*100:.1f}%  [{r['sector']}]")
    print(f"\n  Distinct sectors: {df['sector'].nunique()}")
    print(f"  Herfindahl concentration: {(df['pct']**2).sum()*10000:.0f}/10000")
    print("  (HHI <1000=diversified, 1000-2500=moderate, >2500=concentrated)")

    # ── Summary paragraph ──────────────────────────────────────────────
    top_sector = sector_pct.index[0]
    top_sector_pct = sector_pct.iloc[0]
    second_sector = sector_pct.index[1] if len(sector_pct) > 1 else "N/A"
    second_sector_pct = sector_pct.iloc[1] if len(sector_pct) > 1 else 0

    summary = f"""
As of {datetime.today().strftime('%Y-%m-%d')}, the portfolio ({len(symbols)} positions, \
~${total_value:,.0f} tracked) is dominated by {top_sector} ({top_sector_pct*100:.0f}%) \
and {second_sector} ({second_sector_pct*100:.0f}%), \
with virtually no exposure to Technology, Financials, or Communication Services. \
Size tilt is {dict(size_pct).get('Large-cap',0)*100:.0f}% large-cap. \
Valuation is {'value-tilted' if wt_pe and wt_pe < 20 else 'growth-tilted' if wt_pe and wt_pe > 28 else 'blend'} \
(P/E {wt_pe:.1f}x vs S&P 500 ~22x). \
Portfolio beta is {wt_beta:.2f}x — {'below' if wt_beta and wt_beta < 1 else 'above'} market. \
The primary risk is sector concentration: \
two themes (Supply Chain & Pharma/Biotech) account for essentially all equity exposure. \
The Swing Lab system should target diversification across at least 4-5 sectors \
to complement this existing tilt."""

    print("\n\n" + "=" * 65)
    print("SUMMARY (will be written to Obsidian note):")
    print("=" * 65)
    print(summary)

    # ── Write back to Obsidian ─────────────────────────────────────────
    write_to_obsidian(summary, sector_pct, size_pct, wt_pe, wt_pb, wt_beta, wt_mom, df)

    print("\nDone. Obsidian note updated.")
    return df, summary


def write_to_obsidian(summary, sector_pct, size_pct, wt_pe, wt_pb, wt_beta, wt_mom, df):
    note_path = OBSIDIAN_STRATEGY_NOTE
    if not note_path.exists():
        print(f"[warn] Obsidian note not found: {note_path}")
        return

    content = note_path.read_text(encoding="utf-8")

    filled_block = f"""
### Phase 1 — Factor Exposure (Filled {datetime.today().strftime('%Y-%m-%d')})

**Portfolio:** {len(df)} equity positions tracked across Robinhood + Wealthfront Stock Investing Account.

| Factor | Portfolio | S&P 500 Benchmark |
|---|---|---|
| Top sector | {sector_pct.index[0]} ({sector_pct.iloc[0]*100:.0f}%) | Diversified |
| 2nd sector | {sector_pct.index[1] if len(sector_pct)>1 else 'N/A'} ({sector_pct.iloc[1]*100:.0f}% if len(sector_pct)>1 else 0) | |
| Size tilt | {dict(size_pct).get('Large-cap',0)*100:.0f}% large-cap | ~87% large-cap |
| Weighted P/E | {wt_pe:.1f}x | ~22x |
| Weighted P/B | {wt_pb:.1f}x | ~4.5x |
| Portfolio beta | {wt_beta:.2f}x | 1.00x |
| Avg 12-1m momentum | {wt_mom*100:.1f}% if wt_mom is not None else 'N/A' | varies |

**Sector breakdown:**
{chr(10).join(f'- {s}: {p*100:.1f}%' for s, p in sector_pct.items())}

**Key finding:** {summary.strip()}

> [!info] What this means for Swing Lab
> The scanner should weight sectors currently UNDERREPRESENTED in this portfolio
> (Technology, Financials, Consumer) more heavily when picking candidates,
> to avoid doubling down on existing Industrials/Healthcare concentration.

"""

    # Insert after the Phase 1 section header
    insert_marker = "### Phase 1: Understand What You Own"
    if insert_marker in content and "Phase 1 — Factor Exposure (Filled" not in content:
        # Find the end of the Phase 1 section (next ### or ---)
        idx = content.index(insert_marker)
        next_section = content.find("\n### Phase 2:", idx)
        if next_section == -1:
            next_section = content.find("\n---", idx)
        insert_at = next_section if next_section != -1 else idx + len(insert_marker) + 200
        content = content[:insert_at] + "\n" + filled_block + content[insert_at:]
        # Check off the first Resources item
        content = content.replace(
            "- [ ] Map factor exposures of current holdings",
            "- [x] Map factor exposures of current holdings"
        )
        note_path.write_text(content, encoding="utf-8")
        print(f"  Written to: {note_path}")
    elif "Phase 1 — Factor Exposure (Filled" in content:
        print("  [info] Phase 1 already filled in Obsidian note — skipping overwrite")
    else:
        print(f"  [warn] Could not find insert marker '{insert_marker}' in note")


if __name__ == "__main__":
    df, summary = main()
