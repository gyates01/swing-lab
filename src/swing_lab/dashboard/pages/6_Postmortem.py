"""Page 6 — Trade Postmortem & Learning Engine."""
import json
import streamlit as st
import pandas as pd
from swing_lab.dashboard import sidebar_chat
from swing_lab.dashboard.theme import (
    inject, section_header_html,
    BG, CARD, CARD2, BORDER, TEXT, TEXT_MUTED, TEXT_DIM,
    ACCENT, GREEN, RED, AMBER, BLUE,
)
from swing_lab.dashboard.lib import load_latest_postmortem, load_trade_outcomes, fmt_local_time

st.set_page_config(
    page_title="Postmortem — Swing Lab",
    layout="wide",
)
inject()
st.session_state["current_page"] = "postmortem"
sidebar_chat.render()

st.title("Trade Postmortem")
st.markdown(
    "Claude analyzes your last 30 closed trades against their original predictions — "
    "which risks materialized, which exit triggers fired, and whether the thesis held up. "
    "The more outcome data you capture at close, the better the analysis."
)

# ── Run expander ───────────────────────────────────────────────────────────────

latest = load_latest_postmortem()
label = "Run postmortem" if not latest else "Run again (generates a new postmortem)"
with st.expander(label, expanded=latest is None):
    if latest:
        st.caption(
            f"Last run: {fmt_local_time(latest.get('run_at', ''))} — "
            f"{latest['trade_count']} trades, {latest['outcome_count']} with full outcome data."
        )
    st.warning(
        "This sends your recent trade history to Claude Opus. "
        "Expect 30–60 seconds and ~$0.05–0.15 in API cost.",
    )
    if st.button("Run postmortem analysis", type="primary"):
        from swing_lab.dashboard.actions import refresh_postmortem

        prog = st.progress(0.0, text="Loading trades…")

        def _prog(frac, text):
            prog.progress(frac, text=text)

        try:
            refresh_postmortem(progress_cb=_prog)
            prog.progress(1.0, text="Done!")
            st.success("Postmortem complete.")
            st.rerun()
        except Exception as exc:
            prog.empty()
            st.error(str(exc))

# ── Display latest postmortem ──────────────────────────────────────────────────

if not latest:
    st.markdown(
        f"""
<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;
            padding:32px;text-align:center;margin-top:24px;">
  <div style="color:{TEXT_DIM};font-size:1.5rem;margin-bottom:12px;">[postmortem]</div>
  <div style="color:{TEXT_MUTED};font-size:0.9rem;">
    No postmortem run yet.<br>
    Close some trades with outcome data, then click <strong>Run postmortem analysis</strong> above.
  </div>
</div>""",
        unsafe_allow_html=True,
    )
else:
    # Header meta
    run_at = fmt_local_time(latest.get("run_at", ""))
    model = latest.get("model", "")
    cache_hit = latest.get("cache_hit")
    cache_badge = (
        f'<span style="background:{GREEN}22;color:{GREEN};font-size:0.7rem;'
        f'padding:2px 8px;border-radius:10px;margin-left:8px;">cache hit</span>'
        if cache_hit else ""
    )
    st.markdown(
        f'<div style="color:{TEXT_DIM};font-size:0.72rem;margin-bottom:16px;">'
        f'Generated {run_at} &nbsp;·&nbsp; {model}{cache_badge} &nbsp;·&nbsp; '
        f'{latest["trade_count"]} trades ({latest["outcome_count"]} with full data)'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown(section_header_html("Analysis"), unsafe_allow_html=True)
    st.markdown(
        f"""
<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;
            padding:24px 28px;margin-bottom:24px;line-height:1.7;
            color:{TEXT_MUTED};font-size:0.875rem;white-space:pre-wrap;">
{latest['summary_text']}
</div>""",
        unsafe_allow_html=True,
    )

# ── Trade Outcomes Table ───────────────────────────────────────────────────────

st.markdown(section_header_html("Trade Outcomes"), unsafe_allow_html=True)
outcomes_df = load_trade_outcomes(limit=20)

if outcomes_df.empty:
    st.info("No closed trades yet.")
else:
    def _fmt_pnl_pct(x):
        try:
            if x is None or pd.isna(x):
                return "—"
            return f"{float(x)*100:+.1f}%"
        except Exception:
            return "—"

    def _count_json(s):
        try:
            return len(json.loads(s or "[]"))
        except Exception:
            return 0

    display = pd.DataFrame({
        "ID": outcomes_df["trade_id"].astype(int),
        "Symbol": outcomes_df["symbol"],
        "P&L": outcomes_df["pnl_pct"].apply(_fmt_pnl_pct),
        "Thesis": outcomes_df["thesis_validated"].fillna("—"),
        "Exit Driver": outcomes_df["exit_driver"].fillna("—"),
        "Risks Hit": outcomes_df["red_flags_materialized_json"].apply(_count_json),
        "Triggers Fired": outcomes_df["exit_triggers_fired_json"].apply(_count_json),
        "Macro OK": outcomes_df["macro_aligned"].fillna("—"),
        "Closed": outcomes_df["closed_at"].apply(lambda x: str(x)[:10] if x else "—"),
    })
    display.index = range(1, len(display) + 1)
    st.dataframe(display, use_container_width=True)
