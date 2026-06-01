"""Layer 3 — Claude Analyst Review: blended scores, red flags, quant vs. Claude comparison."""
import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from swing_lab.dashboard.lib import load_scans, load_scans_with_reviews, load_reviews, fmt_local_time
import re as _re
from swing_lab.dashboard.theme import (
    inject, render_topbar, make_fig, metric_html, section_header_html,
    bull_bear_split_html,
    ACCENT, GREEN, RED, AMBER, PURPLE, BORDER, CARD, CARD2,
    TEXT, TEXT_DIM, TEXT_MUTED,
)

from swing_lab.dashboard import sidebar_chat

st.set_page_config(page_title="Claude Review — Swing Lab", layout="wide")
inject()
st.session_state["current_page"] = "review"
sidebar_chat.render()
render_topbar()

st.markdown(f"""
<div style="margin-bottom:6px;">
    <span style="color:{PURPLE};font-size:0.72rem;text-transform:uppercase;
                 letter-spacing:0.1em;">Layer 3</span>
    <h1 style="margin:2px 0 0;">Claude Analyst Review</h1>
</div>
<p style="color:{TEXT_DIM};font-size:0.85rem;margin-top:0;">
    Top 6 candidates scored on earnings quality, growth, margins, and balance sheet.
    Blended 60% quant / 40% Claude.
</p>
""", unsafe_allow_html=True)

with st.expander("How the blending works"):
    st.markdown("""
**Why blend quant and Claude scores?**

The quantitative scanner ranks stocks purely on *price momentum* — it doesn't know whether
a company's earnings are real, whether revenue growth is sustainable, or whether there are
hidden risks. Claude fills that gap by reading the fundamentals.

**The 60/40 blend:**
- **60% quant score** — rewards strong momentum, sector-relative strength
- **40% Claude score** — rewards earnings quality, growth trajectory, clean balance sheet

The quant score is given higher weight because momentum is the primary edge. Claude acts as
a *filter*, demoting candidates with fundamental red flags even when their price action is strong.

**Red flags:** Claude lists specific concerns (e.g. "margin compression", "high leverage",
"revenue concentration"). Three or more red flags is a significant warning.
""")

# ── Refresh button ─────────────────────────────────────────────────────────────
from swing_lab.dashboard.lib import load_reviews as _load_reviews_check
_last_review_scan_ids = load_scans_with_reviews()
_last_review_ts = "never"
if _last_review_scan_ids:
    _latest_review = _load_reviews_check(_last_review_scan_ids[0])
    if not _latest_review.empty and "run_at" in _latest_review.columns:
        _last_review_ts = fmt_local_time(_latest_review.iloc[0]["run_at"])

with st.expander("Run a new Claude review", expanded=False):
    st.markdown(
        f'<div style="background:{AMBER}11;border:1px solid {AMBER}44;border-radius:8px;'
        f'padding:10px 14px;margin-bottom:10px;color:{TEXT_MUTED};font-size:0.82rem;">'
        f'~6 Claude Opus API calls &nbsp;·&nbsp; Last: <strong style="color:{TEXT}">{_last_review_ts}</strong>'
        f' &nbsp;·&nbsp; Also runs a fresh scan first (~2–3 min total).'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.button("Run new review", type="primary", key="run_review_btn"):
        scan_bar = st.progress(0, text="Phase 1 — Scanning S&P 500…")
        scan_status = st.empty()
        review_bar = st.progress(0, text="Phase 2 — Claude review (waiting for scan)…")
        review_status = st.empty()

        def _scan_prog(current, total, symbol):
            pct = int(current / total * 100)
            scan_bar.progress(pct, text=f"Phase 1 — Scoring {symbol} ({current}/{total})")
            scan_status.markdown(
                f"<p style='color:{TEXT_DIM};font-size:0.8rem;'>{symbol}</p>",
                unsafe_allow_html=True,
            )

        def _review_prog(current, total, symbol):
            pct = int(current / total * 100)
            review_bar.progress(pct, text=f"Phase 2 — Reviewing {symbol} ({current}/{total})")
            review_status.markdown(
                f"<p style='color:{TEXT_DIM};font-size:0.8rem;'>{symbol}</p>",
                unsafe_allow_html=True,
            )

        try:
            from swing_lab.dashboard.actions import refresh_review
            scan_id, reviews_df = refresh_review(
                scan_progress=_scan_prog,
                review_progress=_review_prog,
            )
            scan_bar.progress(100, text="Phase 1 — Scan complete")
            review_bar.progress(100, text="Phase 2 — Review complete")
            st.success(
                f"Review complete — scan #{scan_id}, {len(reviews_df)} candidates scored."
            )
            st.rerun()
        except RuntimeError as e:
            scan_bar.empty()
            review_bar.empty()
            st.error(str(e))

scans_with_reviews = load_scans_with_reviews()

if not scans_with_reviews:
    st.warning("No reviews found. Use the 'Run a new Claude review' expander above.")
    st.stop()

scans_df = load_scans()
scan_map = {
    int(row.scan_id): f"#{int(row.scan_id)} — {fmt_local_time(row.run_at)}"
    for _, row in scans_df.iterrows()
    if int(row.scan_id) in scans_with_reviews
}
options = {v: k for k, v in scan_map.items()}
selected_label = st.selectbox("Select reviewed scan", list(options.keys()))
selected_scan_id = options[selected_label]
reviews = load_reviews(selected_scan_id)

if reviews.empty:
    st.warning(f"No review data found for scan #{selected_scan_id}.")
    st.stop()

# ── Summary metrics ────────────────────────────────────────────────────────────
flag_total = 0
all_flags: list[tuple[str, str]] = []
for _, row in reviews.iterrows():
    try:
        flags = json.loads(row.get("red_flags_json") or "[]")
        flag_total += len(flags)
        for f in flags:
            all_flags.append((row["symbol"], f))
    except Exception:
        pass

top = reviews.iloc[0] if not reviews.empty else None
avg_blended = reviews["blended_score"].dropna().mean() if not reviews.empty else None

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(metric_html("Symbols Reviewed", str(len(reviews)), accent_color=ACCENT),
                unsafe_allow_html=True)
with c2:
    if top is not None:
        st.markdown(metric_html(
            "Top Pick (Blended)",
            top["symbol"],
            sub=f'Blended score: {top.get("blended_score", 0):.2f}/10',
            accent_color=GREEN,
        ), unsafe_allow_html=True)
with c3:
    flag_color = RED if flag_total >= 5 else (AMBER if flag_total >= 2 else GREEN)
    st.markdown(metric_html("Total Red Flags", str(flag_total), accent_color=flag_color),
                unsafe_allow_html=True)

# ── Plain-English overview ─────────────────────────────────────────────────────
st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

if top is not None:
    top_score = top.get("blended_score") or 0
    top_claude = top.get("claude_score") or 0
    top_quant = top.get("quant_score") or 0
    top_flags = []
    try:
        top_flags = json.loads(top.get("red_flags_json") or "[]")
    except Exception:
        pass

    # Build a narrative based on the data — no extra Claude call
    if top_score >= 7.5:
        strength = f"a <strong style='color:{GREEN}'>strong</strong> signal"
        action = "This is a high-conviction candidate — the momentum is confirmed by solid fundamentals."
    elif top_score >= 6.0:
        strength = f"a <strong style='color:{AMBER}'>moderate</strong> signal"
        action = "Reasonable candidate. Check the red flags below before sizing in."
    else:
        strength = f"a <strong style='color:{RED}'>weak</strong> signal"
        action = "The blended score is below threshold. Consider waiting for a cleaner setup."

    quant_dominates = top_quant / 10 > top_claude * 1.5 if top_claude > 0 else False
    claude_dominates = top_claude > (top_quant / 10) * 1.5 if top_quant > 0 else False

    divergence_note = ""
    if quant_dominates:
        divergence_note = f"Price momentum is strong but Claude's fundamental score ({top_claude:.1f}/10) is relatively lower — the stock is performing well technically, but the underlying business quality may not fully support the move."
    elif claude_dominates:
        divergence_note = f"Claude rates the fundamentals highly ({top_claude:.1f}/10) but the momentum rank is weaker — this may be a quality name waiting for price to catch up, or one that missed the current trend."

    flag_note = ""
    if len(top_flags) >= 3:
        flag_note = f"**Caution:** The top pick has {len(top_flags)} red flags. Even with a strong score, multiple red flags suggest elevated risk — consider reducing position size or skipping."
    elif len(top_flags) >= 1:
        flag_note = f"The top pick has {len(top_flags)} red flag(s) — review them below before committing."

    clean_count = sum(1 for _, row in reviews.iterrows() if not json.loads(row.get("red_flags_json") or "[]"))

    # Build optional paragraphs without blank lines — blank lines inside an HTML
    # block cause Streamlit 1.57's markdown parser to close the block early,
    # turning indented content into a code block.
    _extra = ""
    if divergence_note:
        _extra += f'<p style="color:{TEXT_MUTED};margin:0 0 8px;line-height:1.65;">{divergence_note}</p>'
    if flag_note:
        _extra += f'<p style="color:{AMBER};margin:0;line-height:1.65;">{flag_note}</p>'
    st.markdown(
        f'<div style="background:{CARD};border:1px solid {BORDER};border-top:2px solid {ACCENT};'
        f'border-radius:10px;padding:18px 22px;margin-bottom:4px;">'
        f'<div style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;'
        f'letter-spacing:0.09em;margin-bottom:10px;">WHAT THIS REVIEW MEANS</div>'
        f'<p style="color:{TEXT_MUTED};margin:0 0 8px;line-height:1.65;">'
        f'The top pick is <strong style="color:{TEXT}">{top["symbol"]}</strong> with {strength}'
        f' (blended {top_score:.2f}/10). {action}</p>'
        f'{_extra}'
        f'<p style="color:{TEXT_DIM};font-size:0.8rem;margin:8px 0 0;">'
        f'{clean_count} of {len(reviews)} candidates have no red flags.'
        f' Average blended score: <strong style="color:{TEXT}">{avg_blended:.2f}/10</strong>.</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Score guide ────────────────────────────────────────────────────────────────
with st.expander("How to read these scores"):
    st.markdown(f"""
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:4px;">

<div style="background:{CARD};border:1px solid {BORDER};border-top:2px solid {AMBER};
            border-radius:8px;padding:14px 16px;">
    <div style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;
                letter-spacing:0.08em;margin-bottom:6px;">Quant Score (0–100)</div>
    <div style="color:{TEXT_MUTED};font-size:0.82rem;line-height:1.55;">
        Sector-relative momentum rank. A score of 80 means this stock is in the
        top 20% of its sector on 12-1 month momentum. <strong style="color:{TEXT}">Higher = stronger trend.</strong>
        Divided by 10 in the chart so it shares a scale with Claude's score.
    </div>
</div>

<div style="background:{CARD};border:1px solid {BORDER};border-top:2px solid {PURPLE};
            border-radius:8px;padding:14px 16px;">
    <div style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;
                letter-spacing:0.08em;margin-bottom:6px;">Claude Score (1–10)</div>
    <div style="color:{TEXT_MUTED};font-size:0.82rem;line-height:1.55;">
        Fundamental quality: earnings consistency, revenue growth, margins, balance sheet strength.
        <strong style="color:{TEXT}">8–10 = clean business.</strong> Below 5 = visible concerns.
        Claude penalises red flags even when the headline numbers look fine.
    </div>
</div>

<div style="background:{CARD};border:1px solid {BORDER};border-top:2px solid {ACCENT};
            border-radius:8px;padding:14px 16px;">
    <div style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;
                letter-spacing:0.08em;margin-bottom:6px;">Blended Score (0–10)</div>
    <div style="color:{TEXT_MUTED};font-size:0.82rem;line-height:1.55;">
        Final ranking score: 60% quant + 40% Claude.
        <strong style="color:{GREEN}">&gt;7.5 = strong buy candidate.</strong>
        5–7.5 = watchlist. Below 5 = pass.
        A high quant but low Claude score means price is running ahead of fundamentals.
    </div>
</div>

</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

# ── Blended score bar chart ────────────────────────────────────────────────────
st.markdown(section_header_html(
    "Blended Score Ranking",
    "60% quant momentum + 40% Claude fundamental quality"
), unsafe_allow_html=True)

symbols = reviews["symbol"].tolist()
blended = reviews["blended_score"].fillna(0).tolist()
quant_norm = [q / 10 for q in reviews["quant_score"].fillna(0).tolist()]  # normalize 0-100 → 0-10
claude_scores = reviews["claude_score"].fillna(0).tolist()

fig = make_fig(
    barmode="group",
    xaxis=dict(title_text=None, gridcolor="rgba(0,0,0,0)"),
    yaxis=dict(title_text="Score (0–10)", gridcolor=BORDER, range=[0, 10.5]),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    margin=dict(l=48, r=24, t=24, b=40),
)
fig.add_trace(go.Bar(
    name="Blended",
    x=symbols,
    y=blended,
    marker_color=ACCENT,
    marker_line_color=BORDER,
    marker_line_width=1,
    opacity=0.95,
    text=[f"{v:.2f}" for v in blended],
    textposition="outside",
    textfont=dict(color=TEXT_DIM, size=10),
    hovertemplate="%{x} — Blended: %{y:.2f}<extra></extra>",
))
fig.add_trace(go.Bar(
    name="Quant (÷10)",
    x=symbols,
    y=quant_norm,
    marker_color=AMBER,
    marker_line_color=BORDER,
    marker_line_width=1,
    opacity=0.8,
    hovertemplate="%{x} — Quant: %{y:.1f}/10<extra></extra>",
))
fig.add_trace(go.Bar(
    name="Claude",
    x=symbols,
    y=claude_scores,
    marker_color=PURPLE,
    marker_line_color=BORDER,
    marker_line_width=1,
    opacity=0.8,
    hovertemplate="%{x} — Claude: %{y:.1f}/10<extra></extra>",
))
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": "hover"})
st.caption(
    "Quant score divided by 10 so all three series share a 0–10 axis. "
    "Large divergence between Quant and Claude scores is worth investigating."
)

# ── Per-symbol cards ───────────────────────────────────────────────────────────
st.markdown(section_header_html("Candidate Detail"), unsafe_allow_html=True)

for _, row in reviews.iterrows():
    symbol = row["symbol"]
    blended_val = row.get("blended_score")
    quant_val = row.get("quant_score")
    claude_val = row.get("claude_score")
    summary = row.get("claude_summary") or "No summary available."

    try:
        red_flags = json.loads(row.get("red_flags_json") or "[]")
    except Exception:
        red_flags = []

    flag_count = len(red_flags)
    badge_color = RED if flag_count >= 3 else (AMBER if flag_count >= 1 else GREEN)
    badge_text = f"{flag_count} red flag{'s' if flag_count != 1 else ''}"
    title_html = (
        f"<b>{symbol}</b>"
        + (f"&nbsp;&nbsp;Blended: {blended_val:.2f}/10" if blended_val is not None else "")
        + f"&nbsp;&nbsp;<span style='color:{badge_color};font-size:0.78rem;'>{badge_text}</span>"
    )

    with st.expander(f"{symbol}  —  Blended: {blended_val:.2f}/10  ·  {badge_text}" if blended_val else symbol,
                     expanded=(flag_count >= 3)):

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(metric_html(
                "Quant Score", f"{quant_val:.0f}/100" if quant_val is not None else "—",
                sub="Sector-relative rank", accent_color=AMBER,
            ), unsafe_allow_html=True)
        with c2:
            st.markdown(metric_html(
                "Claude Score", f"{claude_val:.1f}/10" if claude_val is not None else "—",
                sub="Fundamental quality", accent_color=PURPLE,
            ), unsafe_allow_html=True)
        with c3:
            blend_color = GREEN if blended_val and blended_val >= 7 else (AMBER if blended_val and blended_val >= 5 else RED)
            st.markdown(metric_html(
                "Blended Score", f"{blended_val:.2f}/10" if blended_val is not None else "—",
                sub="60% quant + 40% Claude", accent_color=blend_color,
            ), unsafe_allow_html=True)

        # ── Bull / Bear split ──────────────────────────────────────────────
        bull_sentences = [
            s.strip()
            for s in _re.split(r'(?<=[.!?])\s+', summary)
            if len(s.strip()) > 15
        ][:3]
        st.markdown(
            bull_bear_split_html(bull_sentences, red_flags or ["No flags identified"]),
            unsafe_allow_html=True,
        )
