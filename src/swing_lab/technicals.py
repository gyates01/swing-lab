"""Technical price level analysis from OHLC history."""
import pandas as pd
import yfinance as yf


def get_price_levels(symbol: str, pivot_window: int = 5) -> dict:
    """Compute chart-derived technical levels from 1-year OHLC history.

    Returns dict with:
        price_52w_high, price_52w_low,
        ma_20, ma_50, ma_200,
        atr_14,
        swing_lows   — list of (price, days_ago), most recent first, max 3
        swing_highs  — list of (price, days_ago), most recent first, max 3
    All numeric values are float | None; swing lists may be empty.
    """
    try:
        hist = yf.Ticker(symbol).history(period="1y")
        if hist.empty or len(hist) < 20:
            return {}

        close = hist["Close"]
        high_s = hist["High"]
        low_s = hist["Low"]

        # ── 52-week range ────────────────────────────────────────────────────
        price_52w_high = float(high_s.max())
        price_52w_low = float(low_s.min())

        # ── Moving averages ───────────────────────────────────────────────────
        ma_20  = float(close.tail(20).mean())  if len(close) >= 20  else None
        ma_50  = float(close.tail(50).mean())  if len(close) >= 50  else None
        ma_200 = float(close.tail(200).mean()) if len(close) >= 200 else None

        # ── ATR(14) ───────────────────────────────────────────────────────────
        atr_14 = None
        if len(hist) >= 15:
            prev_close = close.shift(1)
            tr = pd.concat([
                high_s - low_s,
                (high_s - prev_close).abs(),
                (low_s  - prev_close).abs(),
            ], axis=1).max(axis=1)
            atr_14 = float(tr.tail(14).mean())

        # ── Swing pivots over the last ~6 months ─────────────────────────────
        hist6 = hist.tail(130)
        low_arr  = hist6["Low"].values
        high_arr = hist6["High"].values
        dates    = hist6.index

        # Handle timezone-aware index from yfinance
        now = pd.Timestamp.now(tz=dates.tz) if dates.tz is not None else pd.Timestamp.now()

        n = pivot_window
        raw_lows: list[tuple[float, int]] = []
        raw_highs: list[tuple[float, int]] = []

        for i in range(n, len(hist6) - n):
            days_ago = (now - dates[i]).days
            if low_arr[i] <= min(low_arr[i - n: i + n + 1]):
                raw_lows.append((float(low_arr[i]), days_ago))
            if high_arr[i] >= max(high_arr[i - n: i + n + 1]):
                raw_highs.append((float(high_arr[i]), days_ago))

        swing_lows  = _dedup_pivots(raw_lows)
        swing_highs = _dedup_pivots(raw_highs)

        return {
            "price_52w_high": price_52w_high,
            "price_52w_low":  price_52w_low,
            "ma_20":  ma_20,
            "ma_50":  ma_50,
            "ma_200": ma_200,
            "atr_14": atr_14,
            "swing_lows":  swing_lows,
            "swing_highs": swing_highs,
        }

    except Exception as exc:
        print(f"  [warn] technicals {symbol}: {exc}")
        return {}


def _dedup_pivots(
    pivots: list[tuple[float, int]],
    max_results: int = 3,
    pct_gap: float = 0.01,
) -> list[tuple[float, int]]:
    """Sort by recency, then drop pivots within pct_gap % of an already-kept one."""
    if not pivots:
        return []
    pivots = sorted(pivots, key=lambda x: x[1])  # ascending days_ago → most recent first
    kept: list[tuple[float, int]] = [pivots[0]]
    for price, days in pivots[1:]:
        if all(abs(price - kp) / kp > pct_gap for kp, _ in kept):
            kept.append((price, days))
        if len(kept) >= max_results:
            break
    return kept


def format_levels_for_prompt(levels: dict, current_price: float | None) -> str:
    """Format technical levels as a prompt block for Claude."""
    if not levels:
        return ""

    lines = [
        "Technical chart levels (1-year OHLC — anchor your price levels to these):",
    ]

    h52 = levels.get("price_52w_high")
    l52 = levels.get("price_52w_low")
    if h52 and l52:
        pct = f"  ({(current_price / h52 - 1) * 100:+.1f}% vs 52w high)" if current_price else ""
        lines.append(f"52-week range: ${l52:.2f} – ${h52:.2f}{pct}")

    ma_parts = []
    for label, key in [("20d", "ma_20"), ("50d", "ma_50"), ("200d", "ma_200")]:
        v = levels.get(key)
        if v is not None:
            ma_parts.append(f"{label} ${v:.2f}")
    if ma_parts:
        lines.append("Moving averages: " + " | ".join(ma_parts))

    atr = levels.get("atr_14")
    if atr is not None:
        atr_pct = f" ({atr / current_price * 100:.1f}% of price)" if current_price else ""
        lines.append(f"ATR(14): ${atr:.2f}{atr_pct}")

    lows = levels.get("swing_lows") or []
    if lows:
        parts = [f"${p:.2f} ({d}d ago)" for p, d in lows]
        lines.append(f"Recent swing lows  (support candidates): {', '.join(parts)}")

    highs = levels.get("swing_highs") or []
    if highs:
        parts = [f"${p:.2f} ({d}d ago)" for p, d in highs]
        lines.append(f"Recent swing highs (resistance / target candidates): {', '.join(parts)}")

    lines.append(
        "Guidance: entry zone should bracket a nearby MA or the most recent swing low; "
        "support = next swing low below entry; stop = support minus 0.5–1× ATR; "
        "target = nearest swing high or 52w high."
    )

    return "\n".join(lines)
