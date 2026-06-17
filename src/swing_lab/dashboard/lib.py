"""Shared DB helpers, descriptions, and formatters for the Swing Lab dashboard."""
import sqlite3
import pandas as pd
from swing_lab.config import DB_PATH, GATE_FULL, GATE_PARTIAL

# Educational descriptions for the six gate signals
GATE_DESCRIPTIONS = {
    "vix_level": """
**What it measures:** The absolute level of the VIX (CBOE Volatility Index) — the options market's
30-day implied volatility forecast for the S&P 500. Think of it as the market's "fear gauge."

**How it's scored:** Current VIX is ranked against its 1-year range.
VIX near annual low → score near 100 (calm). VIX near annual high → score near 0 (fearful).

**Why it matters:** Momentum strategies work best in low-volatility, trending environments.
High VIX signals choppy, mean-reverting conditions where trend-following breaks down.
""",
    "vix_term_structure": """
**What it measures:** The *shape* of the VIX futures curve — compares the 30-day VIX (^VIX)
against the 3-month VIX (^VIX3M).

**How it's scored:** Contango (VIX3M > VIX) = score above 50 — near-term fear is subsiding.
Backwardation (VIX > VIX3M) = score below 50 — acute near-term stress exceeds the medium-term
forecast.

**Why it matters:** Even when the VIX level is elevated, a recovering term structure (moving toward
contango) is a leading indicator that the volatility regime is normalizing.
""",
    "breadth": """
**What it measures:** Market participation — what percentage of large-cap names are in uptrends
(above their 200-day moving average). This proxy uses SPY (large-cap), IWM (small-cap), and
QQQ (tech/growth).

**How it's scored:** 0 of 3 proxies above their 200-day MA = 0; 3 of 3 = 100.

**Why it matters:** A narrow rally driven by a few mega-caps is fragile. Broad participation means
the trend has structural support. If SPY is up but IWM and QQQ are lagging, internals are weak.
""",
    "credit_spread": """
**What it measures:** High-yield bond health vs. treasuries. Specifically: the 30-day rolling
return of HYG (high-yield ETF) minus IEF (7-10yr treasury ETF), ranked as a 1-year percentile.

**How it's scored:** HYG outperforming IEF → high score (credit healthy, risk-on).
IEF outperforming → low score (flight-to-safety, corporate distress signal).

**Why it matters:** The bond market is often earlier and smarter than equity markets. Widening
credit spreads signal companies can't borrow cheaply — a leading indicator for equity drawdowns.
""",
    "put_call": """
**What it measures:** Tail-risk hedging demand in the options market, proxied by VVIX (the
"VIX of VIX" — how volatile VIX options themselves are). High VVIX = aggressive put-buying.

**How it's scored:** 1-year VVIX percentile, inverted. Low VVIX (calm options market) = high
score. High VVIX (frantic hedging) = low score.

**Why it matters:** VVIX spikes before volatility events materialize in the VIX itself. When
institutions are frantically buying downside protection, it signals elevated uncertainty even
if spot prices look stable.
""",
    "factor_crowding": """
**What it measures:** How crowded momentum trades are — measured as the 60-day rolling
correlation between MTUM (momentum factor ETF) and VLUE (value factor ETF) daily returns.

**How it's scored:** High correlation (crowded) = low score. Low/negative correlation
(diversified positioning) = high score. Formula: (1 − correlation) × 50.

**Why it matters:** When momentum and value are highly correlated, most systematic strategies
are piled into the same names. Crowding creates violent unwind risk — if one manager de-risks,
others are forced to follow. A score near zero means near-maximum crowding.
""",
}

FLAG_NOTES = {
    "vix_level": "Markets are near peak fear — momentum signals are unreliable in high-vol regimes.",
    "vix_term_structure": "Near-term VIX exceeds the 3-month outlook — acute stress detected.",
    "breadth": "Only a narrow subset of stocks are in uptrends — concentration risk is elevated.",
    "credit_spread": "High-yield bonds are underperforming treasuries — a corporate distress signal.",
    "put_call": "Unusual options hedging activity suggests institutional tail-risk protection.",
    "factor_crowding": "Momentum factors are near maximum crowding — unwind risk is severe.",
}

COMPONENT_DISPLAY_NAMES = {
    "vix_level": "VIX Level",
    "vix_term_structure": "VIX Term Structure",
    "breadth": "Market Breadth",
    "credit_spread": "Credit Spreads",
    "put_call": "Put / Call Sentiment",
    "factor_crowding": "Factor Crowding",
}


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _safe_read(query: str, params=None) -> pd.DataFrame:
    try:
        with get_conn() as conn:
            return pd.read_sql_query(query, conn, params=params or [])
    except Exception:
        return pd.DataFrame()


def load_gate_runs(limit: int = 100) -> pd.DataFrame:
    df = _safe_read(f"SELECT * FROM gate_runs ORDER BY gate_id DESC LIMIT {limit}")
    if not df.empty and "run_at" in df.columns:
        df["run_at"] = pd.to_datetime(df["run_at"], utc=True, errors="coerce")
    return df


def load_scans(limit: int = 30) -> pd.DataFrame:
    df = _safe_read(f"SELECT * FROM scans ORDER BY scan_id DESC LIMIT {limit}")
    if not df.empty and "run_at" in df.columns:
        df["run_at"] = pd.to_datetime(df["run_at"], utc=True, errors="coerce")
    return df


def load_scan_picks(scan_id: int) -> pd.DataFrame:
    return _safe_read(
        "SELECT * FROM scan_picks WHERE scan_id = ? ORDER BY rank_score DESC",
        params=(scan_id,),
    )


def load_reviews(scan_id: int) -> pd.DataFrame:
    return _safe_read(
        "SELECT * FROM reviews WHERE scan_id = ? ORDER BY blended_score DESC",
        params=(scan_id,),
    )


def load_scans_with_reviews() -> list[int]:
    df = _safe_read("SELECT DISTINCT scan_id FROM reviews ORDER BY scan_id DESC")
    if df.empty or "scan_id" not in df.columns:
        return []
    return df["scan_id"].tolist()


def load_trades() -> pd.DataFrame:
    return _safe_read("SELECT * FROM trades ORDER BY trade_id DESC")


def load_open_trades() -> pd.DataFrame:
    return _safe_read(
        """SELECT t.*, r.entry_zone as rec_entry_zone
           FROM trades t
           LEFT JOIN recommendations r ON t.rec_id = r.rec_id
           WHERE t.exit_price IS NULL
           ORDER BY t.trade_id DESC"""
    )


def load_latest_recommendations() -> list[dict]:
    """Return today's recommendations ordered by rank, or empty list."""
    try:
        with get_conn() as conn:
            from swing_lab.db import load_latest_recommendations as _load
            return _load(conn)
    except Exception:
        return []


def load_latest_postmortem() -> dict | None:
    try:
        with get_conn() as conn:
            from swing_lab.db import load_latest_postmortem as _load
            return _load(conn)
    except Exception:
        return None


def load_trade_outcomes(limit: int = 20) -> pd.DataFrame:
    return _safe_read(
        """SELECT t.trade_id, t.symbol, t.pnl, t.pnl_pct, t.closed_at,
                  o.thesis_validated, o.exit_driver,
                  o.red_flags_materialized_json, o.exit_triggers_fired_json,
                  o.macro_aligned, o.notes
           FROM trades t
           LEFT JOIN trade_outcomes o ON t.trade_id = o.trade_id
           WHERE t.exit_price IS NOT NULL
             AND (t.rec_id IS NOT NULL OR t.mode = 'paper')
           ORDER BY t.trade_id DESC
           LIMIT ?""",
        params=(limit,),
    )


def load_trade_outcome_context(trade_id: int) -> dict:
    """Return rec risks and exit triggers for a trade's linked recommendation."""
    import json
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.rec_id, r.risks_json, r.exit_triggers_json
                   FROM trades t
                   LEFT JOIN recommendations r ON t.rec_id = r.rec_id
                   WHERE t.trade_id = ?""",
                (trade_id,),
            )
            row = cursor.fetchone()
    except Exception:
        return {}
    if row is None or row[0] is None:
        return {}
    rec_id, risks_json, exit_triggers_json = row
    risks = []
    triggers = []
    try:
        risks = json.loads(risks_json or "[]")
    except Exception:
        pass
    try:
        triggers = json.loads(exit_triggers_json or "[]")
    except Exception:
        pass
    return {"rec_id": rec_id, "risks": risks, "exit_triggers": triggers}


def score_color(score: float) -> str:
    if score >= GATE_FULL:
        return "green"
    elif score >= GATE_PARTIAL:
        return "orange"
    return "red"


def score_label(score: float) -> str:
    if score >= GATE_FULL:
        return "Healthy"
    elif score >= GATE_PARTIAL:
        return "Caution"
    return "Warning"


def fmt_pct(val) -> str:
    try:
        if pd.isna(val):
            return "—"
        return f"{float(val) * 100:.1f}%"
    except Exception:
        return "—"


def fmt_local_time(ts) -> str:
    """Convert a UTC ISO timestamp string to local-time display (no UTC suffix)."""
    from datetime import datetime as _dt, timezone as _tz
    if ts is None:
        return "—"
    try:
        s = str(ts)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        utc_dt = _dt.fromisoformat(s)
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=_tz.utc)
        local_dt = utc_dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)[:16]


def load_analyst_session_list() -> list[dict]:
    """Return all saved analyst chat sessions ordered newest-first."""
    try:
        with get_conn() as conn:
            from swing_lab.db import load_analyst_sessions as _load
            return _load(conn)
    except Exception:
        return []


def load_analyst_session_messages(session_id: str) -> list[dict]:
    """Return the messages list for a saved analyst session, or empty list."""
    try:
        with get_conn() as conn:
            from swing_lab.db import load_analyst_session as _load
            row = _load(conn, session_id)
            return row["messages"] if row else []
    except Exception:
        return []
