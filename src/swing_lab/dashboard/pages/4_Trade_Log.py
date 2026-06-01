"""Trade Log — open, close, edit, and delete trades via UI forms."""
import json
import streamlit as st
import pandas as pd
from swing_lab.dashboard.lib import (
    load_trades, load_open_trades, load_scans, get_conn,
    load_trade_outcome_context, fmt_local_time,
)
from swing_lab.dashboard.theme import (
    inject, render_topbar, metric_html, section_header_html,
    ACCENT, GREEN, RED, AMBER, BORDER, CARD, CARD2,
    TEXT, TEXT_DIM, TEXT_MUTED,
)
from swing_lab.tradelog import open_trade, close_trade, edit_trade, delete_trade
from swing_lab.db import init_db
from swing_lab.config import OUTCOME_THESIS_OPTIONS, OUTCOME_DRIVER_OPTIONS
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
    Open positions are tracked live against your entry price. Changes write directly to swing.db.
</p>
""", unsafe_allow_html=True)

# ── Action tabs ────────────────────────────────────────────────────────────────
tab_open, tab_close, tab_edit = st.tabs(["Open Position", "Close Position", "Edit / Delete"])

# ── Tab 1: Open Position ───────────────────────────────────────────────────────
with tab_open:
    st.markdown(section_header_html("Log a Position"), unsafe_allow_html=True)

    # Pre-fill from Recommendation page "Open trade from this pick" button
    _prefill = st.session_state.get("open_from_rec") or {}
    _prefill_rec_id = _prefill.get("rec_id")
    _prefill_symbol = _prefill.get("symbol", "")
    _prefill_sizing = _prefill.get("sizing_pct", 0.0)

    if _prefill_symbol:
        st.info(
            f"Pre-filled from Recommendation: **{_prefill_symbol}** "
            f"(suggested size: {_prefill_sizing*100:.0f}% of budget). "
            "Adjust shares to match your actual order size."
        )

    st.caption(
        "Already holding a position? Enter your best estimate for entry price and date, "
        "or leave entry price at 0 — P&L tracking will be skipped for that trade."
    )

    _form_v = st.session_state.get("open_trade_form_v", 0)
    c1, c2, c3 = st.columns(3)
    symbol = c1.text_input(
        "Symbol", value=_prefill_symbol, placeholder="e.g. AAPL",
        key=f"sym_{_form_v}",
    ).strip().upper()
    shares = c2.number_input(
        "Shares", min_value=0.001, step=0.001, format="%.4f",
        key=f"shares_{_form_v}",
    )
    entry_price = c3.number_input(
        "Entry Price ($)",
        min_value=0.0, step=0.01, format="%.2f",
        help="Enter 0 if you don't know the exact price — P&L tracking will be skipped for this trade.",
        key=f"ep_{_form_v}",
    )

    if entry_price > 0 and shares > 0:
        st.caption(f"Estimated trade value: ${shares * entry_price:,.2f}")

    thesis = st.text_area(
        "Thesis / Notes (optional)",
        placeholder="Why did you enter? Or: 'Long-term hold, approx entry ~$X in YYYY-MM'",
        height=80,
        key=f"thesis_{_form_v}",
    )

    scans_df = load_scans(limit=10)
    scan_options: dict = {"None — no scan link": None}
    for _, row in scans_df.iterrows():
        scan_options[f"#{int(row.scan_id)} — {fmt_local_time(row.run_at)}"] = int(row.scan_id)
    scan_label = st.selectbox(
        "Link to scan (optional)", list(scan_options.keys()),
        key=f"scan_{_form_v}",
    )
    scan_id = scan_options[scan_label]

    submitted = st.button("Log Position", key=f"submit_{_form_v}", use_container_width=True, type="primary")

    if submitted:
        if not symbol:
            st.error("Symbol is required.")
        elif shares <= 0:
            st.error("Shares must be greater than zero.")
        else:
            conn = init_db()
            try:
                trade_id = open_trade(
                    conn, symbol, shares, entry_price or None,
                    scan_id, thesis, rec_id=_prefill_rec_id,
                )
                price_str = f"@ ${entry_price:.2f}" if entry_price > 0 else "(no entry price)"
                st.success(f"Trade #{trade_id} logged: {symbol} {shares:g} shares {price_str}")
                st.session_state["open_trade_form_v"] = _form_v + 1
                st.session_state.pop("open_from_rec", None)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save trade: {e}")
            finally:
                conn.close()

# ── Tab 2: Close Position ──────────────────────────────────────────────────────
with tab_close:
    st.markdown(section_header_html("Close an Open Position"), unsafe_allow_html=True)
    open_df_close = load_open_trades()

    if open_df_close.empty:
        st.info("No open positions to close.")
    else:
        trade_options = {
            f"#{int(row.trade_id)}: {row.symbol} — {row.shares:g} sh @ ${row.entry_price:.2f}": int(row.trade_id)
            for _, row in open_df_close.iterrows()
        }
        selected_label = st.selectbox("Select position to close", list(trade_options.keys()))
        selected_id = trade_options[selected_label]

        # Load rec context outside the form so multiselect options are dynamic
        rec_ctx = load_trade_outcome_context(selected_id)
        rec_risks = rec_ctx.get("risks", [])
        rec_triggers = rec_ctx.get("exit_triggers", [])

        with st.form("close_trade_form"):
            c1, c2 = st.columns(2)
            exit_price = c1.number_input("Exit Price ($)", min_value=0.01, step=0.01, format="%.2f")
            reason = c2.text_input("Exit Reason", placeholder="e.g. target hit, stop triggered")

            st.markdown(
                f'<div style="color:{TEXT_DIM};font-size:0.65rem;text-transform:uppercase;'
                f'letter-spacing:0.09em;margin:16px 0 8px;">Trade Outcome</div>',
                unsafe_allow_html=True,
            )

            oc1, oc2 = st.columns(2)
            thesis_validated = oc1.radio(
                "Thesis validated?",
                OUTCOME_THESIS_OPTIONS,
                horizontal=True,
            )
            exit_driver = oc2.selectbox("Exit driver", OUTCOME_DRIVER_OPTIONS)

            if rec_risks:
                materialized = st.multiselect(
                    "Predicted red flags that materialized",
                    options=rec_risks,
                    help="Which of the risks flagged at recommendation time actually played out?",
                )
            else:
                materialized = []

            if rec_triggers:
                triggers_fired = st.multiselect(
                    "Exit triggers that fired",
                    options=rec_triggers,
                    help="Which of the 'watch for' signals actually appeared?",
                )
            else:
                triggers_fired = []

            macro_aligned = st.radio(
                "Did macro regime align with the gate's read at entry?",
                ("yes", "no", "n/a"),
                horizontal=True,
            )
            notes = st.text_area("Lessons / notes (optional)", height=72)

            submitted = st.form_submit_button("Close Position", use_container_width=True, type="primary")

        if submitted:
            outcome = {
                "thesis_validated": thesis_validated,
                "exit_driver": exit_driver,
                "red_flags_materialized_json": json.dumps(materialized),
                "exit_triggers_fired_json": json.dumps(triggers_fired),
                "macro_aligned": macro_aligned,
                "notes": notes or None,
            }
            conn = init_db()
            try:
                result = close_trade(conn, selected_id, exit_price, reason, outcome=outcome)
                if result:
                    pnl = result.get("pnl", 0) or 0
                    pnl_pct = (result.get("pnl_pct", 0) or 0) * 100
                    sign = "+" if pnl >= 0 else ""
                    st.success(
                        f"Trade #{selected_id} closed: {sign}${pnl:.2f} ({sign}{pnl_pct:.1f}%)"
                    )
                    st.rerun()
                else:
                    st.error("Trade not found or already closed.")
            except Exception as e:
                st.error(f"Failed to close trade: {e}")
            finally:
                conn.close()

# ── Tab 3: Edit / Delete ───────────────────────────────────────────────────────
with tab_edit:
    c_edit, c_delete = st.columns(2)

    with c_edit:
        st.markdown(section_header_html("Edit a Trade", "Correct prices, update thesis, adjust shares."),
                    unsafe_allow_html=True)
        edit_id = st.number_input("Trade ID to edit", min_value=1, step=1, key="edit_id_input")
        all_trades = load_trades()
        trade_row = all_trades[all_trades["trade_id"] == edit_id]

        if st.button("Load Trade", key="load_edit"):
            if trade_row.empty:
                st.error(f"Trade #{edit_id} not found.")
            else:
                st.session_state["loaded_edit_trade"] = trade_row.iloc[0].to_dict()

        loaded = st.session_state.get("loaded_edit_trade")
        if loaded and int(loaded.get("trade_id", -1)) == edit_id:
            with st.form("edit_trade_form"):
                st.markdown(f"**Editing Trade #{int(loaded['trade_id'])}: {loaded['symbol']}**")
                c1, c2, c3 = st.columns(3)
                new_symbol = c1.text_input("Symbol", value=loaded.get("symbol", "")).strip().upper()
                new_shares = c2.number_input("Shares", value=float(loaded.get("shares") or 0),
                                              min_value=0.01, format="%.2f")
                new_entry = c3.number_input("Entry Price ($)", value=float(loaded.get("entry_price") or 0),
                                             min_value=0.01, format="%.2f")
                current_exit = loaded.get("exit_price")
                new_exit = st.number_input(
                    "Exit Price ($) — leave 0 if still open",
                    value=float(current_exit) if current_exit else 0.0,
                    min_value=0.0, format="%.2f",
                )
                new_thesis = st.text_area("Thesis", value=loaded.get("thesis_text") or "", height=80)
                new_reason = st.text_input("Exit Reason", value=loaded.get("exit_reason") or "")
                save = st.form_submit_button("Save Changes", use_container_width=True, type="primary")

            if save:
                conn = init_db()
                try:
                    result = edit_trade(conn, edit_id,
                                        symbol=new_symbol or None,
                                        shares=new_shares,
                                        entry_price=new_entry,
                                        exit_price=new_exit if new_exit > 0 else None,
                                        thesis_text=new_thesis or None,
                                        exit_reason=new_reason or None)
                    if result:
                        st.success(f"Trade #{edit_id} updated.")
                        st.session_state.pop("loaded_edit_trade", None)
                        st.rerun()
                    else:
                        st.error("No changes saved.")
                except Exception as e:
                    st.error(f"Failed to update: {e}")
                finally:
                    conn.close()

    with c_delete:
        st.markdown(section_header_html("Delete a Trade", "Permanently removes the row from swing.db."),
                    unsafe_allow_html=True)
        del_id = st.number_input("Trade ID to delete", min_value=1, step=1, key="del_id_input")

        if "all_trades" not in dir():
            all_trades = load_trades()
        del_row = all_trades[all_trades["trade_id"] == del_id] if not all_trades.empty else pd.DataFrame()
        if not del_row.empty:
            t = del_row.iloc[0]
            st.info(
                f"**#{int(t.trade_id)}** {t.symbol} — "
                f"{t.shares:g} sh @ ${t.entry_price:.2f} "
                f"(opened {fmt_local_time(t.opened_at)[:10]})"
            )

        confirm = st.checkbox(f"Confirm: permanently delete trade #{del_id}", key="del_confirm")
        if st.button("Delete Trade", disabled=not confirm, key="del_btn"):
            conn = init_db()
            try:
                deleted = delete_trade(conn, del_id)
                if deleted:
                    st.success(f"Trade #{del_id} deleted.")
                    st.rerun()
                else:
                    st.error(f"Trade #{del_id} not found.")
            except Exception as e:
                st.error(f"Failed to delete: {e}")
            finally:
                conn.close()

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
    h_cols = st.columns([0.4, 0.9, 0.8, 1.0, 1.1, 1.4, 0.6, 3.5, 0.7])
    _headers = ["ID", "Symbol", "Shares", "Entry $", None, "Opened", "", "Chart", ""]
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

        r_cols = st.columns([0.4, 0.9, 0.8, 1.0, 1.1, 1.4, 0.6, 3.5, 0.7])
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

        if r_cols[8].button("Close", key=f"rm_{tid}", help=f"Close or remove trade #{tid}"):
            st.session_state[f"confirm_rm_{tid}"] = True

        # Inline removal confirmation
        if st.session_state.get(f"confirm_rm_{tid}"):
            c_msg, c_yes, c_no = st.columns([4, 0.8, 0.6])
            c_msg.warning(
                f"Remove #{tid}: {row.symbol} {row.shares:g} sh @ ${row.entry_price:.2f}? "
                f"This deletes the trade record — use Close Position tab to log an exit instead."
            )
            if c_yes.button("Delete", key=f"yes_{tid}", type="primary"):
                conn = init_db()
                try:
                    delete_trade(conn, tid)
                    st.session_state.pop(f"confirm_rm_{tid}", None)
                    st.rerun()
                finally:
                    conn.close()
            if c_no.button("Cancel", key=f"no_{tid}"):
                st.session_state.pop(f"confirm_rm_{tid}", None)
                st.rerun()

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
