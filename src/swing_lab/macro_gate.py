"""6-signal macro gate: VIX level, VIX term structure, breadth, credit spread, put/call proxy, factor crowding."""
import yfinance as yf
import pandas as pd
import numpy as np
from swing_lab.config import GATE_FULL, GATE_PARTIAL


def vix_score() -> float:
    """VIX level score 0–100. Lower VIX → higher score (less fear)."""
    vix = yf.Ticker("^VIX").history(period="1y")["Close"]
    raw = (1 - vix.iloc[-1] / vix.max()) * 100
    return float(np.clip(raw, 0.0, 100.0))


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

    Rolling 60-day correlation between MTUM (momentum) and VLUE (value) daily returns.
    High positive correlation = factors crowded = dangerous → low score.
    corr = 1.0  → score = 0   (fully crowded)
    corr = 0.0  → score = 50  (neutral)
    corr = -1.0 → score = 100 (diversified)
    Formula: score = (1 - corr) * 50
    """
    try:
        mtum = yf.Ticker("MTUM").history(period="1y")["Close"]
        vlue = yf.Ticker("VLUE").history(period="1y")["Close"]

        combined = pd.DataFrame({"MTUM": mtum, "VLUE": vlue}).dropna()
        if len(combined) < 61:
            print("  [warn] factor_crowding_score: insufficient data for 60-day window")
            return 50.0

        mtum_ret = combined["MTUM"].pct_change().dropna()
        vlue_ret = combined["VLUE"].pct_change().dropna()

        ret_df = pd.DataFrame({"MTUM": mtum_ret, "VLUE": vlue_ret}).dropna()
        if len(ret_df) < 61:
            print("  [warn] factor_crowding_score: insufficient return data")
            return 50.0

        rolling_corr = ret_df["MTUM"].rolling(60).corr(ret_df["VLUE"])
        last_corr = float(rolling_corr.dropna().iloc[-1])
        score = (1.0 - last_corr) * 50.0
        return float(np.clip(score, 0.0, 100.0))
    except Exception as e:
        print(f"  [warn] factor_crowding_score: {e}")
        return 50.0


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
