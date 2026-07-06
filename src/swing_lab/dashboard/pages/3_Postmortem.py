"""Page 6 — Trade Postmortem & Learning Engine."""
import json
import streamlit as st
import pandas as pd
from swing_lab.dashboard import sidebar_chat
from swing_lab.dashboard.theme import (
    inject, render_topbar, section_header_html,
    BG, CARD, CARD2, BORDER, TEXT, TEXT_MUTED, TEXT_DIM,
    ACCENT, GREEN, RED, AMBER, BLUE,
)
from swing_lab.dashboard.lib import load_latest_postmortem, load_trade_outcomes, fmt_local_time


def _count_json(val) -> int:
    try:
        return len(json.loads(val or "[]"))
    except Exception:
        return 0


def _outcomes_table_html(df: pd.DataFrame) -> str:
    hdr = (
        f"color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;"
        f"letter-spacing:0.08em;padding:10px 14px;border-bottom:1px solid {BORDER};text-align:left;"
    )
    cell = f"padding:9px 14px;border-bottom:1px solid {BORDER}33;font-size:0.82rem;vertical-align:middle;"
    rows = ""
    for _, row in df.iterrows():
        pnl_raw = row.get("pnl_pct")
        try:
            pnl_val = float(pnl_raw) if pnl_raw is not None and not pd.isna(pnl_raw) else None
        except Exception:
            pnl_val = None
        pnl_str = f"{pnl_val*100:+.1f}%" if pnl_val is not None else "—"
        pnl_color = GREEN if (pnl_val and pnl_val > 0) else (RED if (pnl_val and pnl_val < 0) else TEXT_DIM)

        thesis = str(row.get("thesis_validated") or "—").strip()
        thesis_color = GREEN if thesis.lower() in ("yes", "true") else (RED if thesis.lower() in ("no", "false") else TEXT_MUTED)

        risks_hit = _count_json(row.get("red_flags_materialized_json"))
        triggers = _count_json(row.get("exit_triggers_fired_json"))
        macro = str(row.get("macro_aligned") or "—").strip()
        macro_color = GREEN if macro.lower() in ("yes", "true") else (AMBER if macro == "—" else RED)
        closed = str(row.get("closed_at") or "—")[:10]
        exit_driver = str(row.get("exit_driver") or "—")

        rows += (
            f'<tr>'
            f'<td style="{cell}color:{TEXT_DIM};">{int(row["trade_id"])}</td>'
            f'<td style="{cell}color:{TEXT};font-family:\'DM Mono\',monospace;font-weight:600;">{row["symbol"]}</td>'
            f'<td style="{cell}color:{pnl_color};font-family:\'DM Mono\',monospace;text-align:right;">{pnl_str}</td>'
            f'<td style="{cell}color:{thesis_color};">{thesis}</td>'
            f'<td style="{cell}color:{TEXT_MUTED};">{exit_driver}</td>'
            f'<td style="{cell}color:{RED if risks_hit > 0 else TEXT_DIM};text-align:center;">{risks_hit}</td>'
            f'<td style="{cell}color:{GREEN if triggers > 0 else TEXT_DIM};text-align:center;">{triggers}</td>'
            f'<td style="{cell}color:{macro_color};">{macro}</td>'
            f'<td style="{cell}color:{TEXT_DIM};">{closed}</td>'
            f'</tr>'
        )
    return (
        f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:10px;overflow:hidden;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>'
        f'<th style="{hdr}">ID</th>'
        f'<th style="{hdr}">Symbol</th>'
        f'<th style="{hdr}text-align:right;">P&amp;L</th>'
        f'<th style="{hdr}">Thesis</th>'
        f'<th style="{hdr}">Exit Driver</th>'
        f'<th style="{hdr}text-align:center;">Risks</th>'
        f'<th style="{hdr}text-align:center;">Triggers</th>'
        f'<th style="{hdr}">Macro</th>'
        f'<th style="{hdr}">Closed</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table>'
        f'</div>'
    )


st.set_page_config(
    page_title="Postmortem — Swing Lab",
    layout="wide",
)
inject()
st.session_state["current_page"] = "postmortem"
sidebar_chat.render()
render_topbar()

st.markdown(f"""
<div style="margin-bottom:6px;">
    <span style="color:{BLUE};font-size:0.72rem;text-transform:uppercase;
                 letter-spacing:0.1em;">Layer 6</span>
    <h1 style="margin:2px 0 0;">Trade Postmortem</h1>
</div>
<p style="color:{TEXT_DIM};font-size:0.85rem;margin-top:0;">
    Claude analyzes your last 30 closed trades — which risks materialized, which exit triggers fired,
    and whether each thesis held up. More outcome data at close = better analysis.
</p>
""", unsafe_allow_html=True)

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
        f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;'
        f'padding:32px;text-align:center;margin-top:24px;">'
        f'<div style="color:{TEXT_DIM};font-size:0.85rem;">'
        f'No postmortem run yet — close some trades with outcome data, then run the analysis above.'
        f'</div>'
        f'</div>',
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
    st.markdown(_outcomes_table_html(outcomes_df), unsafe_allow_html=True)
