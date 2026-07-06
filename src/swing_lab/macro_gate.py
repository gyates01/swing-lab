"""6-signal macro gate: VIX level, VIX term structure, breadth, credit spread, put/call proxy, factor crowding."""
import yfinance as yf
import pandas as pd
import numpy as np
from swing_lab.config import GATE_FULL, GATE_PARTIAL


def vix_score() -> float:
    """VIX level score 0–100. Lower VIX → higher score (less fear)."""
    try:
        vix = yf.Ticker("^VIX").history(period="1y")["Close"]
        if len(vix) == 0:
            print("  [warn] vix_score: no VIX data")
            return 50.0
        raw = (1 - vix.iloc[-1] / vix.max()) * 100
        return float(np.clip(raw, 0.0, 100.0))
    except Exception as e:
        print(f"  [warn] vix_score: {e}")
        return 50.0


def vix_term_structure_score() -> float:
    """VIX term structure score 0–100.

    Compares 30-day (^VIX) vs 3-month (^VIX3M) implied vol.
    Contango (VIX3M > VIX) is healthy → score > 50.
    Backwardation (VIX > VIX3M) is stressed → score < 50.
    """
    try:
        vix_data = yf.Ticker("^VIX").history(period="5d")["Close"]
        vix3m_data = yf.Ticker("^VIX3M").history(period="5d")["Close"]
        vix_current = float(vix_data.iloc[-1])
        vix3m_current = float(vix3m_data.iloc[-1])
        spread = vix3m_current - vix_current
        raw = 50.0 + spread * 10.0
        return float(np.clip(raw, 0.0, 100.0))
    except Exception as e:
        print(f"  [warn] vix_term_structure_score: {e}")
        return 50.0


def breadth_score(universe_symbols: list[str] | None = None) -> float:
    """% of S&P 500 above 200-day MA, scored 0–100.

    Uses SPY/IWM/QQQ as a fast proxy until M3.5 adds full breadth calculation.
    """
    proxies = ["SPY", "IWM", "QQQ"]
    above_ma = 0
    total = 0
    for ticker in proxies:
        try:
            hist = yf.Ticker(ticker).history(period="1y")["Close"]
            if len(hist) >= 200:
                ma200 = hist.rolling(200).mean().iloc[-1]
                current = hist.iloc[-1]
                if current > ma200:
                    above_ma += 1
                total += 1
        except Exception as e:
            print(f"  [warn] breadth proxy {ticker}: {e}")

    if total == 0:
        return 50.0  # neutral fallback
    return float((above_ma / total) * 100)


def credit_spread_score() -> float:
    """Credit spread health score 0–100.

    Proxy: 30-day rolling return spread of HYG (high-yield) minus IEF (treasury).
    Positive spread (HYG outperforming) = credit healthy = risk-on → high score.
    Uses 1-year percentile rank of the spread as the score.
    """
    try:
        hyg = yf.Ticker("HYG").history(period="1y")["Close"]
        ief = yf.Ticker("IEF").history(period="1y")["Close"]

        # Align on common dates
        combined = pd.DataFrame({"HYG": hyg, "IEF": ief}).dropna()
        if len(combined) < 31:
            print("  [warn] credit_spread_score: insufficient data")
            return 50.0

        hyg_ret = combined["HYG"].pct_change(30)
        ief_ret = combined["IEF"].pct_change(30)
        spread = (hyg_ret - ief_ret).dropna()

        if len(spread) == 0:
            print("  [warn] credit_spread_score: spread series empty")
            return 50.0

        current_spread = float(spread.iloc[-1])
        percentile = float((spread < current_spread).mean() * 100)
        return float(np.clip(percentile, 0.0, 100.0))
    except Exception as e:
        print(f"  [warn] credit_spread_score: {e}")
        return 50.0


def put_call_score() -> float:
    """Put/call sentiment score 0–100.

    Proxy: 1-year percentile of VVIX (volatility-of-volatility).
    High VVIX = heavy put buying / tail hedging = bearish → low score.
    Score = (1 - percentile) * 100, so low VVIX percentile → high score.
    """
    try:
        vvix = yf.Ticker("^VVIX").history(period="1y")["Close"]
        if len(vvix) == 0:
            print("  [warn] put_call_score: no VVIX data")
            return 50.0

        current = float(vvix.iloc[-1])
        percentile = float((vvix < current).mean())
        score = (1.0 - percentile) * 100.0
        return float(np.clip(score, 0.0, 100.0))
    except Exception as e:
        print(f"  [warn] put_call_score: {e}")
        return 50.0


def factor_crowding_score() -> float:
    """Factor crowding score 0–100.

    Rolling 60-day correlation between MTUM (momentum) and VLUE (value) daily
    MARKET-EXCESS returns (each minus SPY). Raw returns are dominated by shared
    market beta (~0.75 correlation in every regime), which measured the market
    rather than factor crowding; subtracting SPY isolates the factor tilts.
    High positive excess-return correlation = factors crowded → low score.
    corr = 1.0  → score = 0   (fully crowded)
    corr = 0.0  → score = 50  (neutral)
    corr = -1.0 → score = 100 (diversified)
    Formula: score = (1 - corr) * 50
    """
    try:
        mtum = yf.Ticker("MTUM").history(period="1y")["Close"]
        vlue = yf.Ticker("VLUE").history(period="1y")["Close"]
        spy = yf.Ticker("SPY").history(period="1y")["Close"]

        combined = pd.DataFrame({"MTUM": mtum, "VLUE": vlue, "SPY": spy}).dropna()
        if len(combined) < 61:
            print("  [warn] factor_crowding_score: insufficient data for 60-day window")
            return 50.0

        rets = combined.pct_change().dropna()
        excess = pd.DataFrame({
            "MTUM": rets["MTUM"] - rets["SPY"],
            "VLUE": rets["VLUE"] - rets["SPY"],
        }).dropna()
        if len(excess) < 61:
            print("  [warn] factor_crowding_score: insufficient return data")
            return 50.0

        rolling_corr = excess["MTUM"].rolling(60).corr(excess["VLUE"])
        last_corr = float(rolling_corr.dropna().iloc[-1])
        score = (1.0 - last_corr) * 50.0
        return float(np.clip(score, 0.0, 100.0))
    except Exception as e:
        print(f"  [warn] factor_crowding_score: {e}")
        return 50.0


# ── Point-in-time gate (for backtesting) ─────────────────────────────────────
# Mirrors the six live signals, but computed from a pre-fetched price panel
# using only data at or before the as-of date. Signals with insufficient
# history degrade to neutral 50.0, same as the live fallbacks.

GATE_TICKERS = ["^VIX", "^VIX3M", "^VVIX", "HYG", "IEF", "MTUM", "VLUE", "SPY", "IWM", "QQQ"]


def fetch_gate_panel(start, end) -> pd.DataFrame:
    """Batched close-price panel for all gate instruments."""
    from swing_lab.scanner import fetch_close_panel
    return fetch_close_panel(GATE_TICKERS, start, end)


def _window(panel: pd.DataFrame, ticker: str, as_of, days: int = 365) -> pd.Series:
    """Series for ticker covering the `days` ending at as_of (inclusive, no look-ahead)."""
    if panel.empty or ticker not in panel.columns:
        return pd.Series(dtype=float)
    s = panel[ticker].dropna()
    as_of = pd.Timestamp(as_of)
    return s[(s.index > as_of - pd.Timedelta(days=days)) & (s.index <= as_of)]


def compute_gate_asof(panel: pd.DataFrame, as_of) -> dict:
    """Historical gate score at a given date. Same structure as compute_gate()."""
    # 1. VIX level (1y relative)
    vix = _window(panel, "^VIX", as_of)
    vix_s = (
        float(np.clip((1 - vix.iloc[-1] / vix.max()) * 100, 0.0, 100.0))
        if len(vix) >= 60 else 50.0
    )

    # 2. VIX term structure
    vix3m_w = _window(panel, "^VIX3M", as_of, days=30)
    vix_w = _window(panel, "^VIX", as_of, days=30)
    if len(vix3m_w) > 0 and len(vix_w) > 0:
        spread = float(vix3m_w.iloc[-1]) - float(vix_w.iloc[-1])
        term_s = float(np.clip(50.0 + spread * 10.0, 0.0, 100.0))
    else:
        term_s = 50.0

    # 3. Breadth proxies above 200dma
    above, total = 0, 0
    for t in ("SPY", "IWM", "QQQ"):
        s = _window(panel, t, as_of, days=400)
        if len(s) >= 200:
            total += 1
            if float(s.iloc[-1]) > float(s.rolling(200).mean().iloc[-1]):
                above += 1
    breadth_s = float(above / total * 100) if total else 50.0

    # 4. Credit spread (HYG vs IEF 30d return spread, 1y percentile)
    combined = pd.DataFrame({
        "HYG": _window(panel, "HYG", as_of),
        "IEF": _window(panel, "IEF", as_of),
    }).dropna()
    if len(combined) >= 31:
        spread = (combined["HYG"].pct_change(30) - combined["IEF"].pct_change(30)).dropna()
        credit_s = (
            float(np.clip((spread < spread.iloc[-1]).mean() * 100, 0.0, 100.0))
            if len(spread) else 50.0
        )
    else:
        credit_s = 50.0

    # 5. Put/call proxy (VVIX 1y percentile, inverted)
    vvix = _window(panel, "^VVIX", as_of)
    if len(vvix) >= 60:
        pct = float((vvix < vvix.iloc[-1]).mean())
        pc_s = float(np.clip((1.0 - pct) * 100.0, 0.0, 100.0))
    else:
        pc_s = 50.0

    # 6. Factor crowding (60d MTUM/VLUE market-excess return correlation —
    # raw returns are dominated by shared SPY beta, see factor_crowding_score)
    rets = pd.DataFrame({
        "MTUM": _window(panel, "MTUM", as_of).pct_change(),
        "VLUE": _window(panel, "VLUE", as_of).pct_change(),
        "SPY": _window(panel, "SPY", as_of).pct_change(),
    }).dropna()
    if len(rets) >= 61:
        excess_m = rets["MTUM"] - rets["SPY"]
        excess_v = rets["VLUE"] - rets["SPY"]
        corr_series = excess_m.rolling(60).corr(excess_v).dropna()
        crowd_s = (
            float(np.clip((1.0 - float(corr_series.iloc[-1])) * 50.0, 0.0, 100.0))
            if len(corr_series) else 50.0
        )
    else:
        crowd_s = 50.0

    composite = (vix_s + term_s + breadth_s + credit_s + pc_s + crowd_s) / 6.0
    if composite >= GATE_FULL:
        sizing, label = 1.0, "FULL"
    elif composite >= GATE_PARTIAL:
        sizing, label = 0.6, "PARTIAL"
    else:
        sizing, label = 0.0, "STAND DOWN"

    return {
        "score": composite,
        "sizing": sizing,
        "label": label,
        "components": {
            "vix_level": vix_s,
            "vix_term_structure": term_s,
            "breadth": breadth_s,
            "credit_spread": credit_s,
            "put_call": pc_s,
            "factor_crowding": crowd_s,
        },
    }


def compute_gate() -> dict:
    """Compute composite gate score and deployment sizing from 6 signals."""
    vix = vix_score()
    term = vix_term_structure_score()
    breadth = breadth_score()
    credit = credit_spread_score()
    put_call = put_call_score()
    crowding = factor_crowding_score()

    composite = (vix + term + breadth + credit + put_call + crowding) / 6.0

    if composite >= GATE_FULL:
        sizing, label = 1.0, "FULL"
    elif composite >= GATE_PARTIAL:
        sizing, label = 0.6, "PARTIAL"
    else:
        sizing, label = 0.0, "STAND DOWN"

    return {
        "score": composite,
        "sizing": sizing,
        "label": label,
        "components": {
            "vix_level": vix,
            "vix_term_structure": term,
            "breadth": breadth,
            "credit_spread": credit,
            "put_call": put_call,
            "factor_crowding": crowding,
        },
    }
