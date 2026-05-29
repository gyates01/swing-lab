"""Layer 2 — Quantitative Scanner: momentum picks, sector breakdown, distribution."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from swing_lab.dashboard.lib import load_scans, load_scan_picks, fmt_local_time
from swing_lab.dashboard.theme import (
    inject, make_fig, metric_html, section_header_html,
    ACCENT, GREEN, RED, AMBER, BORDER, CARD, TEXT, TEXT_DIM, TEXT_MUTED,
)

from swing_lab.dashboard import sidebar_chat

st.set_page_config(page_title="Scanner — Swing Lab", layout="wide")
inject()
st.session_state["current_page"] = "scanner"
sidebar_chat.render()

st.markdown(f"""
<div style="margin-bottom:6px;">
    <span style="color:{ACCENT};font-size:0.72rem;text-transform:uppercase;
                 letter-spacing:0.1em;">Layer 2</span>
    <h1 style="margin:2px 0 0;">Quantitative Scanner</h1>
</div>
<p style="color:{TEXT_DIM};font-size:0.85rem;margin-top:0;">
    12-1 month momentum ranked within each GICS sector.
    Top 20 names by sector-relative score shortlisted for Layer 3.
</p>
""", unsafe_allow_html=True)

with st.expander("How the momentum signal works"):
    st.markdown("""
**12-1 Month Momentum**

The strategy buys stocks with strong *recent* performance but skips the most recent month.
Why skip the last month? Because very short-term returns tend to *mean-revert* (winners give
back gains), while the 2–12 month window shows *momentum continuation*.

**Formula:** `(price 1 month ago) / (price 12 months ago) − 1`

**Sector-relative ranking:** Each stock is ranked against *peers in its own GICS sector*. This
prevents the scanner filling up with 20 names from one hot sector. Each pick must be exceptional
within its sector, not just riding a sector tailwind.

**Top-20 cutoff:** The 20 highest sector-relative scores are passed to Layer 3 (Claude review),
which further filters to the top 6.
""")

# ── Refresh button ─────────────────────────────────────────────────────────────
with st.expander("Run a new scan", expanded=False):
    st.markdown(
        f"<p style='color:{TEXT_DIM};font-size:0.85rem;margin:0;'>"
        f"Scores all ~500 S&P 500 symbols on 12-1 month momentum. Takes 2–3 minutes.</p>",
        unsafe_allow_html=True,
    )
    if st.button("Run new scan", type="primary", key="run_scan_btn"):
        prog_bar = st.progress(0, text="Starting scan…")
        status = st.empty()

        def _scan_progress(current, total, symbol):
            pct = int(current / total * 100)
            prog_bar.progress(pct, text=f"Scoring {symbol} ({current}/{total})")
            status.markdown(
                f"<p style='color:{TEXT_DIM};font-size:0.8rem;'>{symbol}</p>",
                unsafe_allow_html=True,
            )

        try:
            from swing_lab.dashboard.actions import refresh_scan
            scan_id, gate, _ = refresh_scan(progress=_scan_progress)
            prog_bar.progress(100, text="Done")
            st.success(
                f"Scan #{scan_id} complete — gate {gate['score']:.1f}/100 ({gate['label']})"
            )
            st.rerun()
        except RuntimeError as e:
            prog_bar.empty()
            st.error(str(e))

scans_df = load_scans()

if scans_df.empty:
    st.warning("No scans found. Use the 'Run a new scan' expander above.")
    st.stop()

# ── Scan selector ──────────────────────────────────────────────────────────────
scan_options = {
    f"#{int(row.scan_id)} — {fmt_local_time(row.run_at)} (gate: {row.gate_score:.1f}, sizing: {row.sizing*100:.0f}%)": int(row.scan_id)
    for _, row in scans_df.iterrows()
}
selected_label = st.selectbox("Select scan", list(scan_options.keys()))
selected_scan_id = scan_options[selected_label]

scan_row = scans_df[scans_df["scan_id"] == selected_scan_id].iloc[0]
picks = load_scan_picks(selected_scan_id)

if picks.empty:
    st.warning(f"No picks found for scan #{selected_scan_id}.")
    st.stop()

# ── Summary metrics ────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(metric_html("Scan ID", f"#{selected_scan_id}", accent_color=ACCENT), unsafe_allow_html=True)
with c2:
    gate_color = GREEN if scan_row.gate_score >= 70 else (AMBER if scan_row.gate_score >= 40 else RED)
    st.markdown(metric_html("Gate Score at Scan", f"{scan_row.gate_score:.1f}/100",
                            accent_color=gate_color), unsafe_allow_html=True)
with c3:
    st.markdown(metric_html("Deployment Sizing", f"{scan_row.sizing*100:.0f}%",
                            accent_color=ACCENT), unsafe_allow_html=True)
with c4:
    st.markdown(metric_html("Picks", str(len(picks)), accent_color=ACCENT), unsafe_allow_html=True)

st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

# ── Charts row ─────────────────────────────────────────────────────────────────
chart_l, chart_r = st.columns(2)

with chart_l:
    st.markdown(section_header_html("Picks by Sector"), unsafe_allow_html=True)
    sector_counts = picks.groupby("sector")["symbol"].count().sort_values()
    colors = [ACCENT] * len(sector_counts)
    max_sector_pct = 0.0

    # Highlight most concentrated sector
    if len(sector_counts) > 0:
        max_sector_pct = sector_counts.max() / len(picks)
        if max_sector_pct > 0.4:
            colors[-1] = AMBER  # top bar in amber as a concentration warning

    fig = make_fig(
        xaxis=dict(title_text="Number of Picks", gridcolor=BORDER),
        yaxis=dict(gridcolor="rgba(0,0,0,0)"),
        margin=dict(l=10, r=40, t=10, b=40),
    )
    fig.add_trace(go.Bar(
        y=sector_counts.index.tolist(),
        x=sector_counts.values.tolist(),
        orientation="h",
        marker_color=colors,
        text=sector_counts.values.tolist(),
        textposition="outside",
        textfont=dict(color=TEXT_DIM, size=11),
        hovertemplate="%{y}: %{x} picks<extra></extra>",
    ))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    if max_sector_pct > 0.4:
        dominant = sector_counts.idxmax()
        st.warning(
            f"**Concentration flag:** {dominant} makes up {max_sector_pct*100:.0f}% of picks. "
            "High sector concentration increases correlated drawdown risk."
        )

with chart_r:
    st.markdown(section_header_html("Momentum Distribution"), unsafe_allow_html=True)
    valid_mom = picks["momentum"].dropna() * 100
    median_val = float(valid_mom.median()) if not valid_mom.empty else 0.0

    fig = make_fig(
        xaxis=dict(title_text="12-1 Month Momentum (%)", gridcolor=BORDER),
        yaxis=dict(title_text="Count", gridcolor=BORDER),
        margin=dict(l=48, r=32, t=10, b=40),
    )
    fig.add_trace(go.Histogram(
        x=valid_mom.tolist(),
        nbinsx=15,
        marker_color=ACCENT,
        marker_line_color=BORDER,
        marker_line_width=1,
        opacity=0.88,
        name="Momentum",
        hovertemplate="Momentum: %{x:.1f}%<br>Count: %{y}<extra></extra>",
    ))
    fig.add_vline(x=0, line_dash="dash", line_color=RED, line_width=1.5,
                  annotation_text="Zero", annotation_font_color=RED, annotation_font_size=10)
    fig.add_vline(x=median_val, line_dash="dash", line_color=GREEN, line_width=1.5,
                  annotation_text=f"Median {median_val:.1f}%",
                  annotation_font_color=GREEN, annotation_font_size=10)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ── Picks table ────────────────────────────────────────────────────────────────
st.markdown(section_header_html("Top 20 Picks"), unsafe_allow_html=True)

missing_count = picks["momentum"].isna().sum()
if missing_count > 0:
    st.warning(f"**Data quality flag:** {missing_count} symbol(s) missing momentum data (yfinance fetch failed).")

display = picks.copy()
display["momentum_pct"] = display["momentum"].apply(
    lambda x: f"{x*100:.1f}%" if pd.notna(x) else "—"
)
display["rank_score_fmt"] = display["rank_score"].apply(
    lambda x: f"{x:.1f}" if pd.notna(x) else "—"
)
table = display[["symbol", "sector", "momentum_pct", "rank_score_fmt"]].copy()
table.columns = ["Symbol", "Sector", "12-1m Momentum", "Sector Rank (0–100)"]
table.index = range(1, len(table) + 1)
st.dataframe(table, use_container_width=True)
st.caption(
    "Sector Rank is a percentile within the symbol's GICS sector (100 = top of sector). "
    "Picks are sorted by sector rank descending."
)
