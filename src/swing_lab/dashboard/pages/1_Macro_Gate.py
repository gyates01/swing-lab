"""Layer 1 — Macro Gate: six-signal composite score and component history."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timezone
from swing_lab.dashboard.lib import (
    load_gate_runs, GATE_DESCRIPTIONS, FLAG_NOTES, COMPONENT_DISPLAY_NAMES, fmt_local_time,
)
from swing_lab.dashboard.theme import (
    inject, make_fig, composite_score_html, score_card_html, section_header_html,
    ACCENT, GREEN, RED, AMBER, BLUE, PURPLE, BORDER, CARD, CARD2,
    TEXT, TEXT_MUTED, TEXT_DIM, CHART_COLORS,
)
from swing_lab.config import GATE_FULL, GATE_PARTIAL

from swing_lab.dashboard import sidebar_chat

st.set_page_config(page_title="Macro Gate — Swing Lab", layout="wide")
inject()
st.session_state["current_page"] = "macro_gate"
sidebar_chat.render()

st.markdown(f"""
<div style="margin-bottom:6px;">
    <span style="color:{GREEN};font-size:0.72rem;text-transform:uppercase;
                 letter-spacing:0.1em;">Layer 1</span>
    <h1 style="margin:2px 0 0;">Macro Gate</h1>
</div>
<p style="color:{TEXT_DIM};font-size:0.85rem;margin-top:0;">
    Six market signals determine whether conditions favour deploying capital.
    &nbsp;≥70 = FULL (100% sizing) &nbsp;|&nbsp; 40–69 = PARTIAL (60%) &nbsp;|&nbsp; &lt;40 = STAND DOWN
</p>
""", unsafe_allow_html=True)

df = load_gate_runs()

if df.empty:
    st.warning("No gate runs found. Run `uv run swing-lab gate` to populate.")
    st.stop()

latest = df.iloc[0]
score = float(latest["composite_score"])
sizing = float(latest["sizing"])
label = str(latest["label"])
run_str = fmt_local_time(latest["run_at"])

# ── Main score + action row ────────────────────────────────────────────────────
col_score, col_action = st.columns([3, 1])

with col_score:
    st.markdown(composite_score_html(score, label, sizing, run_str), unsafe_allow_html=True)

with col_action:
    st.markdown(f"<div style='height:16px;'></div>", unsafe_allow_html=True)

    # Detect whether a gate run already happened today (UTC)
    today_utc = datetime.now(timezone.utc).date()
    latest_date = latest["run_at"].date() if latest["run_at"] is not None else None
    already_ran_today = (latest_date == today_utc)

    if already_ran_today:
        run_time = fmt_local_time(latest["run_at"])
        btn_label = "Refresh today's gate"
        btn_type = "secondary"
        st.markdown(
            f"<p style='color:{TEXT_DIM};font-size:0.75rem;margin-bottom:6px;'>"
            f"Already ran today at {run_time}.<br>"
            f"Refreshing overwrites — total runs won't change.</p>",
            unsafe_allow_html=True,
        )
    else:
        btn_label = "Run gate"
        btn_type = "primary"
        st.markdown(
            f"<p style='color:{TEXT_DIM};font-size:0.78rem;margin-bottom:6px;'>"
            f"Live yfinance fetch — takes 30–60 s.</p>",
            unsafe_allow_html=True,
        )

    if st.button(btn_label, use_container_width=True, type=btn_type):
        with st.spinner("Fetching live market data..."):
            from swing_lab.dashboard.actions import refresh_gate
            gate = refresh_gate()
        st.success(f"Done: {gate['score']:.1f}/100 — {gate['label']}")
        st.rerun()

    today_note = " · Today: 1 run" if already_ran_today else ""
    st.markdown(
        f"<p style='color:{TEXT_DIM};font-size:0.75rem;margin-top:6px;'>"
        f"Total runs: {len(df)}{today_note}</p>",
        unsafe_allow_html=True,
    )

# ── Component cards ────────────────────────────────────────────────────────────
st.markdown(section_header_html(
    "Component Signals",
    "Each signal scored 0–100. Composite = simple average of all six."
), unsafe_allow_html=True)

comp_keys = ["vix_level", "vix_term_structure", "breadth", "credit_spread", "put_call", "factor_crowding"]
components = [(k, latest.get(k)) for k in comp_keys]

# Row 1: radar chart + 3 cards
col_radar, *score_cols = st.columns([2, 1, 1, 1])

# Radar chart
with col_radar:
    vals = []
    cat_names = []
    for k, v in components:
        vals.append(float(v) if v is not None and not pd.isna(v) else 0.0)
        cat_names.append(COMPONENT_DISPLAY_NAMES.get(k, k))

    # Close the polygon
    vals_closed = vals + [vals[0]]
    cats_closed = cat_names + [cat_names[0]]

    fig = make_fig(
        polar=dict(
            bgcolor=CARD2,
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(color=TEXT_DIM, size=9, family="'DM Mono', monospace"),
                gridcolor=BORDER,
                linecolor=BORDER,
                dtick=25,
            ),
            angularaxis=dict(
                tickfont=dict(color=TEXT_MUTED, size=11),
                gridcolor=BORDER,
                linecolor=BORDER,
            ),
        ),
        showlegend=False,
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor=CARD,
    )
    fig.add_trace(go.Scatterpolar(
        r=vals_closed,
        theta=cats_closed,
        fill="toself",
        fillcolor=f"rgba(99,102,241,0.18)",
        line=dict(color=ACCENT, width=2),
        mode="lines+markers",
        marker=dict(size=6, color=ACCENT),
        hovertemplate="%{theta}: %{r:.0f}/100<extra></extra>",
    ))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# Score cards: first 3
for col, (key, val) in zip(score_cols, components[:3]):
    with col:
        name = COMPONENT_DISPLAY_NAMES.get(key, key)
        if val is None or pd.isna(val):
            st.markdown(f"""
<div style="background:{CARD};border:1px solid {BORDER};border-radius:10px;
            padding:18px 20px;">
    <div style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;
                letter-spacing:0.08em;">{name}</div>
    <div style="color:{TEXT_DIM};font-size:1.5rem;margin-top:8px;">N/A</div>
</div>""", unsafe_allow_html=True)
        else:
            flag = FLAG_NOTES.get(key, "") if float(val) < 20 else ""
            st.markdown(score_card_html(name, float(val), flag), unsafe_allow_html=True)
        with st.expander("What does this measure?"):
            st.markdown(GATE_DESCRIPTIONS.get(key, ""))

# Row 2: last 3 cards
row2 = st.columns(3)
for col, (key, val) in zip(row2, components[3:]):
    with col:
        name = COMPONENT_DISPLAY_NAMES.get(key, key)
        if val is None or pd.isna(val):
            st.markdown(f"""
<div style="background:{CARD};border:1px solid {BORDER};border-radius:10px;
            padding:18px 20px;">
    <div style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;
                letter-spacing:0.08em;">{name}</div>
    <div style="color:{TEXT_DIM};font-size:1.5rem;margin-top:8px;">N/A</div>
</div>""", unsafe_allow_html=True)
        else:
            flag = FLAG_NOTES.get(key, "") if float(val) < 20 else ""
            st.markdown(score_card_html(name, float(val), flag), unsafe_allow_html=True)
        with st.expander("What does this measure?"):
            st.markdown(GATE_DESCRIPTIONS.get(key, ""))

# ── Flags ──────────────────────────────────────────────────────────────────────
flags = [
    (k, v) for k, v in components
    if v is not None and not pd.isna(v) and float(v) < 20
]
if flags:
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    for key, val in flags:
        note = FLAG_NOTES.get(key, "")
        name = COMPONENT_DISPLAY_NAMES.get(key, key)
        st.error(f"**{name}** is at {float(val):.0f}/100 — {note}")

# ── History chart ──────────────────────────────────────────────────────────────
st.markdown(section_header_html("Gate Score History"), unsafe_allow_html=True)

if len(df) < 2:
    st.info("Run the gate a few more times to see the history chart here.")
else:
    df_chart = df.sort_values("gate_id").reset_index(drop=True)

    fig = make_fig(
        yaxis=dict(range=[0, 105], title_text="Composite Score", gridcolor=BORDER, linecolor=BORDER,
                   tickfont=dict(color=TEXT_DIM, size=11)),
        xaxis=dict(title_text="Gate Run (oldest → newest)", gridcolor=BORDER, linecolor=BORDER,
                   tickfont=dict(color=TEXT_DIM, size=11)),
        showlegend=False,
    )

    # Threshold band fills
    fig.add_hrect(y0=GATE_FULL, y1=105, fillcolor=GREEN, opacity=0.05, line_width=0)
    fig.add_hrect(y0=GATE_PARTIAL, y1=GATE_FULL, fillcolor=AMBER, opacity=0.05, line_width=0)
    fig.add_hrect(y0=0, y1=GATE_PARTIAL, fillcolor=RED, opacity=0.05, line_width=0)

    # Threshold lines
    fig.add_hline(y=GATE_FULL, line_dash="dash", line_color=GREEN, line_width=1, opacity=0.5,
                  annotation_text=f"FULL ≥{GATE_FULL}", annotation_font_color=GREEN,
                  annotation_font_size=10)
    fig.add_hline(y=GATE_PARTIAL, line_dash="dash", line_color=AMBER, line_width=1, opacity=0.5,
                  annotation_text=f"PARTIAL ≥{GATE_PARTIAL}", annotation_font_color=AMBER,
                  annotation_font_size=10)

    # Score line
    fig.add_trace(go.Scatter(
        x=list(range(len(df_chart))),
        y=df_chart["composite_score"].tolist(),
        mode="lines+markers",
        line=dict(color=ACCENT, width=2.5),
        marker=dict(size=7, color=ACCENT, line=dict(color=CARD, width=2)),
        hovertemplate="Run %{x} &nbsp; Score: %{y:.1f}<extra></extra>",
    ))

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": "hover"})

    with st.expander("Individual component history"):
        fig2 = make_fig(
            yaxis=dict(range=[0, 105], title_text="Score (0–100)", gridcolor=BORDER),
            xaxis=dict(title_text="Gate Run", gridcolor=BORDER),
        )
        for i, key in enumerate(comp_keys):
            if key not in df_chart.columns:
                continue
            fig2.add_trace(go.Scatter(
                x=list(range(len(df_chart))),
                y=df_chart[key].tolist(),
                mode="lines+markers",
                name=COMPONENT_DISPLAY_NAMES.get(key, key),
                line=dict(color=CHART_COLORS[i % len(CHART_COLORS)], width=1.8),
                marker=dict(size=5),
                hovertemplate=f"{COMPONENT_DISPLAY_NAMES.get(key, key)}: %{{y:.1f}}<extra></extra>",
            ))
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": "hover"})
        st.caption("All signals scored 0–100. Composite = simple average of all six.")
