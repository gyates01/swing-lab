"""Swing Lab dashboard — landing page."""
import streamlit as st
from swing_lab.dashboard.lib import load_gate_runs, load_scans, load_open_trades, score_color, fmt_local_time
from swing_lab.dashboard.theme import (
    inject, render_topbar, metric_html, ACCENT, GREEN, AMBER, RED, PURPLE,
    CARD, BORDER, TEXT, TEXT_DIM, TEXT_MUTED
)
from swing_lab.dashboard import sidebar_chat

st.set_page_config(
    page_title="Swing Lab",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject()
st.session_state["current_page"] = "home"
sidebar_chat.render()
render_topbar()

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="margin-bottom:24px;">
    <div style="color:{TEXT};font-size:1.6rem;font-weight:700;
                font-family:'IBM Plex Sans',system-ui,sans-serif;letter-spacing:-0.02em;">
        Swing Lab
    </div>
    <div style="color:{TEXT_DIM};font-size:0.85rem;margin-top:4px;">
        Three-layer momentum system &nbsp;·&nbsp;
        Macro Gate → Quantitative Scanner → Claude Analyst Review
    </div>
</div>
""", unsafe_allow_html=True)

# ── Current status cards ───────────────────────────────────────────────────────
gate_df = load_gate_runs(limit=1)
scans_df = load_scans(limit=1)
open_df = load_open_trades()

c1, c2, c3 = st.columns(3)

with c1:
    if not gate_df.empty:
        row = gate_df.iloc[0]
        score = float(row["composite_score"])
        color = GREEN if score >= 70 else (AMBER if score >= 40 else RED)
        run_str = fmt_local_time(row["run_at"])
        st.markdown(metric_html(
            "Latest Gate Score",
            f"{score:.0f} / 100",
            sub=f'{row["label"]} &nbsp;·&nbsp; {run_str}',
            accent_color=color,
        ), unsafe_allow_html=True)
    else:
        st.markdown(metric_html("Latest Gate Score", "No data",
                                sub="Run uv run swing-lab gate"), unsafe_allow_html=True)

with c2:
    if not scans_df.empty:
        row = scans_df.iloc[0]
        run_str = fmt_local_time(row["run_at"])
        st.markdown(metric_html(
            "Latest Scan",
            f"#{int(row['scan_id'])}",
            sub=f'Gate {row["gate_score"]:.0f} &nbsp;·&nbsp; {row["sizing"]*100:.0f}% sizing &nbsp;·&nbsp; {run_str}',
            accent_color=ACCENT,
        ), unsafe_allow_html=True)
    else:
        st.markdown(metric_html("Latest Scan", "No data",
                                sub="Run uv run swing-lab scan"), unsafe_allow_html=True)

with c3:
    open_count = len(open_df)
    symbols_str = ""
    if open_count > 0:
        syms = ", ".join(open_df["symbol"].tolist()[:5])
        if open_count > 5:
            syms += f" +{open_count - 5} more"
        symbols_str = syms
    st.markdown(metric_html(
        "Open Positions",
        str(open_count),
        sub=symbols_str or "No open trades",
        accent_color=ACCENT if open_count > 0 else BORDER,
    ), unsafe_allow_html=True)

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ── System overview ────────────────────────────────────────────────────────────
with st.expander("How the Three-Layer System works", expanded=False):
    st.markdown(f"""
<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px;margin-top:4px;">

<div style="background:{CARD};border:1px solid {BORDER};border-radius:10px;padding:18px;">
    <div style="color:{GREEN};font-size:0.68rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">Layer 1</div>
    <div style="color:{TEXT};font-weight:600;font-size:0.9rem;margin-bottom:8px;">Macro Gate</div>
    <div style="color:{TEXT_MUTED};font-size:0.8rem;line-height:1.55;">
        Six market signals averaged into a 0–100 score. <br><br>
        ≥ 70 → <span style="color:{GREEN}">FULL</span> (100% sizing)<br>
        40–69 → <span style="color:{AMBER}">PARTIAL</span> (60%)<br>
        &lt; 40 → <span style="color:{RED}">STAND DOWN</span>
    </div>
</div>

<div style="background:{CARD};border:1px solid {BORDER};border-radius:10px;padding:18px;">
    <div style="color:{ACCENT};font-size:0.68rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">Layer 2</div>
    <div style="color:{TEXT};font-weight:600;font-size:0.9rem;margin-bottom:8px;">Quantitative Scanner</div>
    <div style="color:{TEXT_MUTED};font-size:0.8rem;line-height:1.55;">
        12-1 month momentum on the S&P 500 universe. Ranked <em>within each GICS sector</em> to avoid concentration. Top 20 candidates shortlisted.
    </div>
</div>

<div style="background:{CARD};border:1px solid {BORDER};border-radius:10px;padding:18px;">
    <div style="color:{PURPLE};font-size:0.68rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">Layer 3</div>
    <div style="color:{TEXT};font-weight:600;font-size:0.9rem;margin-bottom:8px;">Claude Review</div>
    <div style="color:{TEXT_MUTED};font-size:0.8rem;line-height:1.55;">
        Top 6 sent to Claude for fundamental scoring: earnings quality, growth, margins, balance sheet. Blended 60% quant / 40% Claude.
    </div>
</div>

<div style="background:{CARD};border:1px solid {BORDER};border-radius:10px;padding:18px;">
    <div style="color:{AMBER};font-size:0.68rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">Trade Log</div>
    <div style="color:{TEXT};font-weight:600;font-size:0.9rem;margin-bottom:8px;">Adaptation Loop</div>
    <div style="color:{TEXT_MUTED};font-size:0.8rem;line-height:1.55;">
        Log every position with a thesis and exit reason. The postmortem command identifies patterns in your winners and losers.
    </div>
</div>

</div>
""", unsafe_allow_html=True)

# ── Navigation ─────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;
            letter-spacing:0.08em;margin:24px 0 10px;">NAVIGATE</div>
""", unsafe_allow_html=True)

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.page_link("pages/1_Macro_Gate.py",    label="Layer 1 — Macro Gate")
c2.page_link("pages/2_Scanner.py",       label="Layer 2 — Scanner")
c3.page_link("pages/3_Claude_Review.py", label="Layer 3 — Claude Review")
c4.page_link("pages/4_Trade_Log.py",     label="Trade Log")
c5.page_link("pages/5_Recommendation.py", label="Recommendation")
c6.page_link("pages/6_Postmortem.py",    label="Postmortem")
