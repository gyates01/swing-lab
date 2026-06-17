"""Trade Log — read-only view of synced positions and trade history."""
import streamlit as st
import pandas as pd
from swing_lab.dashboard.lib import load_trades, load_open_trades, fmt_local_time
from swing_lab.dashboard.theme import (
    inject, render_topbar, section_header_html,
    GREEN, RED, AMBER, BORDER, CARD, TEXT, TEXT_DIM,
)
from swing_lab.dashboard import sidebar_chat
from swing_lab.dashboard.charts import fetch_history as _fetch_history, candle_chart as _candle_chart


def _position_data(symbol: str) -> dict:
    """Current price + daily change from last 2 trading-day closes (cached 5d daily)."""
    from datetime import date
    try:
        hist = _fetch_history(symbol, "5d", "1d")
        if hist is None or len(hist) < 2:
            return {}
        current = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        market_open_today = hist.index[-1].date() >= date.today()
        daily_chg = (current - prev) if market_open_today else 0.0
        daily_pct = (daily_chg / prev * 100) if market_open_today else 0.0
        return {
            "current": current,
            "prev_close": prev,
            "daily_chg": daily_chg,
            "daily_pct": daily_pct,
        }
    except Exception:
        return {}


_METRIC_OPTIONS = [
    "Last price",
    "Percent change",
    "Today's return",
    "Total return",
    "Total % change",
]


def _market_status() -> tuple[str, str, str]:
    """Return (key, label, color) based on US Eastern market hours.
    key: 'live' | 'pre' | 'post' | 'closed'
    """
    from datetime import datetime, time as dtime
    try:
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
    except ImportError:
        import pytz
        et = pytz.timezone("America/New_York")
    now = datetime.now(et)
    if now.weekday() >= 5:
        return "closed", "Closed", TEXT_DIM
    t = now.time()
    if t < dtime(4, 0):
        return "closed", "Closed", TEXT_DIM
    elif t < dtime(9, 30):
        return "pre", "Pre-market", AMBER
    elif t <= dtime(16, 0):
        return "live", "Live", GREEN
    elif t <= dtime(20, 0):
        return "post", "After-hours", AMBER
    return "closed", "Closed", TEXT_DIM


def _status_badge_html(label: str, color: str) -> str:
    return (
        f'<span style="background:{color}22;color:{color};font-size:0.6rem;font-weight:600;'
        f'padding:1px 7px;border-radius:10px;text-transform:uppercase;'
        f'letter-spacing:0.06em;vertical-align:middle;">{label}</span>'
    )


def _fmt_metric(key: str, pdata: dict, shares: float, entry_price: float | None) -> tuple[str, str]:
    """Return (formatted_value, color). Color follows the sign of the value itself."""
    current = pdata.get("current")
    prev = pdata.get("prev_close")
    if current is None:
        return "—", TEXT_DIM

    def _color(val: float) -> str:
        return GREEN if val > 0 else (RED if val < 0 else TEXT_DIM)

    if key == "Last price":
        entry_delta = (current - entry_price) if entry_price else 0
        return f"${current:,.2f}", _color(entry_delta)

    if key == "Percent change":
        pct = pdata.get("daily_pct", 0)
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.2f}%", _color(pct)

    if key == "Today's return":
        if prev is None:
            return "—", TEXT_DIM
        val = shares * pdata.get("daily_chg", 0)
        sign = "+" if val >= 0 else ""
        return f"{sign}${val:,.2f}", _color(val)

    if key == "Total return":
        if not entry_price or entry_price == 0:
            return "—", TEXT_DIM
        val = shares * (current - entry_price)
        sign = "+" if val >= 0 else ""
        return f"{sign}${val:,.2f}", _color(val)

    if key == "Total % change":
        if not entry_price or entry_price == 0:
            return "—", TEXT_DIM
        pct = (current - entry_price) / entry_price * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.2f}%", _color(pct)

    return "—", TEXT_DIM


st.set_page_config(page_title="Trade Log — Swing Lab", layout="wide")
inject()
st.markdown(
    "<style>"
    "[data-testid='stPopover'] button svg { display: none !important; }"
    "[data-testid='stPopover'] button { padding: 2px 8px !important; }"
    "@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.35} }"
    "</style>",
    unsafe_allow_html=True,
)
st.session_state["current_page"] = "trade_log"
sidebar_chat.render()
render_topbar()

_ms_key, _ms_label, _ms_color = _market_status()
st.markdown(f"""
<div style="margin-bottom:6px;display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;">
    <div>
        <span style="color:{AMBER};font-size:0.72rem;text-transform:uppercase;
                     letter-spacing:0.1em;">Trade Log</span>
        <h1 style="margin:2px 0 0;">Positions</h1>
    </div>
    <span style="background:{_ms_color}1a;color:{_ms_color};font-size:0.72rem;font-weight:600;
                 padding:3px 12px;border-radius:20px;text-transform:uppercase;
                 letter-spacing:0.07em;border:1px solid {_ms_color}44;
                 align-self:flex-end;margin-bottom:6px;">
        {'&#9679;' if _ms_key == 'live' else '&#9675;'} {_ms_label}
    </span>
</div>
<p style="color:{TEXT_DIM};font-size:0.85rem;margin-top:0;">
    Open positions are tracked live against your entry price. Synced read-only from your broker account.
</p>
""", unsafe_allow_html=True)

# ── Positions tables ───────────────────────────────────────────────────────────
st.divider()

open_df = load_open_trades()

# ── Portfolio summary bar ──────────────────────────────────────────────────────
if not open_df.empty:
    _n_pos = len(open_df)
    _total_cost = open_df.apply(
        lambda r: float(r.shares or 0) * float(r.entry_price or 0), axis=1
    ).sum()
    _ms_key2, _ms_label2, _ms_color2 = _market_status()
    _stale_count = 0
    try:
        _now_ts = pd.Timestamp.now(tz="UTC")
        _opened_dt = pd.to_datetime(open_df["opened_at"], utc=True, errors="coerce")
        _stale_count = int(((_now_ts - _opened_dt).dt.days > 30).sum())
    except Exception:
        pass

    _stale_note = (
        f' &nbsp;<span style="color:{AMBER};font-size:0.72rem;">'
        f'{_stale_count} stale (&gt;30d)</span>'
    ) if _stale_count else ""

    st.markdown(f"""
<div style="background:{CARD};border:1px solid {BORDER};border-radius:10px;
            padding:14px 20px;margin-bottom:18px;display:flex;gap:32px;
            align-items:center;flex-wrap:wrap;">
    <div>
        <div style="color:{TEXT_DIM};font-size:0.65rem;text-transform:uppercase;
                    letter-spacing:0.09em;margin-bottom:3px;">Positions</div>
        <div style="color:{TEXT};font-family:'DM Mono',monospace;
                    font-size:1.4rem;font-weight:600;">{_n_pos}{_stale_note}</div>
    </div>
    <div>
        <div style="color:{TEXT_DIM};font-size:0.65rem;text-transform:uppercase;
                    letter-spacing:0.09em;margin-bottom:3px;">Deployed (cost basis)</div>
        <div style="color:{TEXT};font-family:'DM Mono',monospace;
                    font-size:1.4rem;font-weight:600;">
            {"$" + f"{_total_cost:,.0f}" if _total_cost > 0 else "—"}
        </div>
    </div>
    <div style="margin-left:auto;">
        <div style="color:{TEXT_DIM};font-size:0.65rem;text-transform:uppercase;
                    letter-spacing:0.09em;margin-bottom:3px;">Market</div>
        <div style="display:flex;align-items:center;gap:6px;">
            <span style="width:8px;height:8px;border-radius:50%;
                         background:{_ms_color2};display:inline-block;
                         {'animation:pulse 2s infinite;' if _ms_key2 == 'live' else ''}"></span>
            <span style="color:{_ms_color2};font-family:'DM Mono',monospace;
                         font-size:0.85rem;font-weight:600;">{_ms_label2}</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(section_header_html("Open Positions"), unsafe_allow_html=True)

if open_df.empty:
    st.info("No open positions.")
else:
    # Stale position check (>30 days)
    try:
        now = pd.Timestamp.now(tz="UTC")
        open_df["opened_at_dt"] = pd.to_datetime(open_df["opened_at"], utc=True, errors="coerce")
        stale_ids = set(open_df[((now - open_df["opened_at_dt"]).dt.days > 30)]["trade_id"].tolist())
    except Exception:
        stale_ids = set()

    # Metric selector + market status context
    _ms_key3, _ms_label3, _ms_color3 = _market_status()
    sel_metric = st.selectbox(
        "Show metric",
        _METRIC_OPTIONS,
        index=_METRIC_OPTIONS.index(st.session_state.get("pos_metric", "Last price")),
        key="pos_metric",
        label_visibility="collapsed",
    )

    # Build metric column header — add market status badge when showing price/return data
    _price_metrics = {"Last price", "Percent change", "Today's return", "Total return", "Total % change"}
    if sel_metric in _price_metrics:
        _metric_header_html = (
            f'<span style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;'
            f'letter-spacing:0.08em;">{sel_metric}&nbsp;</span>'
            + _status_badge_html(_ms_label3, _ms_color3)
        )
    else:
        _metric_header_html = (
            f'<span style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;'
            f'letter-spacing:0.08em;">{sel_metric}</span>'
        )

    # Table header
    h_cols = st.columns([0.4, 0.9, 0.8, 1.0, 1.1, 1.4, 0.6, 3.5])
    _headers = ["ID", "Symbol", "Shares", "Entry $", None, "Opened", "", "Chart"]
    for col, lbl in zip(h_cols, _headers):
        if lbl is None:
            col.markdown(_metric_header_html, unsafe_allow_html=True)
        else:
            col.markdown(
                f"<span style='color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;"
                f"letter-spacing:0.08em;'>{lbl}</span>",
                unsafe_allow_html=True,
            )
    st.markdown(f"<hr style='margin:4px 0 8px;border-color:{BORDER};opacity:1;'>",
                unsafe_allow_html=True)

    for _, row in open_df.iterrows():
        tid = int(row.trade_id)
        is_stale = tid in stale_ids
        opened = fmt_local_time(row.opened_at) if row.opened_at else "—"
        entry_price = float(row.entry_price) if row.entry_price else None
        shares = float(row.shares)

        pdata = _position_data(row.symbol)
        current = pdata.get("current")
        color = GREEN if (not entry_price or entry_price == 0 or not current or current >= entry_price) else RED
        metric_val, metric_color = _fmt_metric(sel_metric, pdata, shares, entry_price)

        r_cols = st.columns([0.4, 0.9, 0.8, 1.0, 1.1, 1.4, 0.6, 3.5])
        r_cols[0].markdown(f"<span style='color:{TEXT_DIM};font-family:DM Mono,monospace;'>#{tid}</span>",
                           unsafe_allow_html=True)
        equity_str = f"${shares * current:,.2f}" if current else ""
        stale_badge = (
            f' <span style="background:{AMBER}22;color:{AMBER};font-size:0.58rem;font-weight:600;'
            f'padding:1px 5px;border-radius:6px;vertical-align:middle;">30d+</span>'
        ) if is_stale else ""
        r_cols[1].markdown(
            f'<span style="font-family:DM Mono,monospace;font-weight:600;">{row.symbol}</span>'
            f'{stale_badge}'
            + (f"<br><span style='color:{color};font-size:0.72rem;font-family:DM Mono,monospace;'>{equity_str}</span>" if equity_str else ""),
            unsafe_allow_html=True,
        )
        r_cols[2].markdown(f"<span style='font-family:DM Mono,monospace;'>{shares:g}</span>",
                           unsafe_allow_html=True)
        r_cols[3].markdown(
            f"<span style='font-family:DM Mono,monospace;'>"
            f"{'$'+f'{entry_price:,.2f}' if entry_price else '—'}</span>",
            unsafe_allow_html=True,
        )
        r_cols[4].markdown(
            f"<span style='font-family:DM Mono,monospace;color:{metric_color};'>{metric_val}</span>",
            unsafe_allow_html=True,
        )
        r_cols[5].markdown(
            f"<span style='font-family:DM Mono,monospace;font-size:0.8rem;'>{opened}</span>",
            unsafe_allow_html=True,
        )
        thesis_text = str(row.thesis_text) if row.thesis_text else ""
        if thesis_text:
            with r_cols[6].popover("≡"):
                st.markdown(f"**#{tid} — {row.symbol} thesis**")
                st.write(thesis_text)
        else:
            r_cols[6].markdown(f"<span style='color:{TEXT_DIM};'>—</span>", unsafe_allow_html=True)

        entry_date = str(row.opened_at)[:10] if row.opened_at else ""
        if entry_date:
            rec_zone = getattr(row, "rec_entry_zone", None) or ""
            entry_zone_str = rec_zone or (f"${entry_price:.2f}" if entry_price else "")
            fig = _candle_chart(
                row.symbol,
                entry_zone_str=entry_zone_str,
                price=current,
                period="3mo",
                height=200,
                trade_entry_price=entry_price,
                trade_entry_date=entry_date,
            )
            if fig:
                r_cols[7].plotly_chart(
                    fig, use_container_width=True,
                    config={"displayModeBar": False},
                )

# ── Trade history ──────────────────────────────────────────────────────────────
st.markdown(section_header_html("Trade History"), unsafe_allow_html=True)

all_df = load_trades()
closed_df = all_df[all_df["exit_price"].notna()] if not all_df.empty else pd.DataFrame()

if closed_df.empty:
    st.info("No closed trades yet.")
else:
    display = closed_df[["trade_id", "symbol", "shares", "entry_price",
                          "exit_price", "pnl", "pnl_pct", "closed_at"]].copy()

    def fmt_pnl(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return "—"
        return f"+${x:.2f}" if x >= 0 else f"-${abs(x):.2f}"

    def fmt_pnl_pct(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return "—"
        return f"+{x*100:.1f}%" if x >= 0 else f"{x*100:.1f}%"

    display["pnl"] = display["pnl"].apply(fmt_pnl)
    display["pnl_pct"] = display["pnl_pct"].apply(fmt_pnl_pct)
    display["closed_at"] = display["closed_at"].apply(lambda x: str(x)[:10] if x else "—")
    display.columns = ["ID", "Symbol", "Shares", "Entry $", "Exit $", "P&L", "P&L %", "Closed"]
    display.index = range(1, len(display) + 1)
    st.dataframe(display, use_container_width=True)
