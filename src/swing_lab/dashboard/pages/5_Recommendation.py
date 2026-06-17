"""Page 5 — Trade Recommendation Engine."""
import json
import re
import streamlit as st
from swing_lab.dashboard import sidebar_chat
from swing_lab.dashboard.theme import (
    inject, render_topbar, section_header_html,
    ticker_hero_html, bull_bear_split_html, risk_row_html,
    BG, CARD, CARD2, BORDER, TEXT, TEXT_MUTED, TEXT_DIM,
    ACCENT, GREEN, RED, AMBER, BLUE,
)
from swing_lab.dashboard.lib import load_latest_recommendations
from swing_lab.dashboard.charts import (
    candle_chart as _candle_chart,
    parse_entry_zone as _parse_entry_zone,
    parse_entry_zone_extras as _parse_entry_zone_extras,
)
from swing_lab.dashboard.theme import zone_kpi_grid_html as _zone_kpi_grid_html


@st.cache_data(ttl=86400)
def _company_name(symbol: str) -> str:
    try:
        import yfinance as yf
        return yf.Ticker(symbol).info.get("shortName") or ""
    except Exception:
        return ""


st.set_page_config(
    page_title="Recommendation — Swing Lab",
    layout="wide",
)
inject()
st.session_state["current_page"] = "recommendation"
sidebar_chat.render()
render_topbar()

st.title("Trade Recommendation Engine")
st.markdown(
    "Top 3 momentum picks synthesized from the macro gate, scanner, and Claude reviews. "
    "The #1 pick gets a live Claude synthesis; #2/#3 are composed from stored review data."
)

# ── Helpers for #1 pick display ───────────────────────────────────────────────

_SEV_ORDER = ["high", "med", "low"]


def _risks_to_rows(risks: list) -> str:
    """Convert a list of risk strings to risk_row_html blocks."""
    if not risks:
        return (
            f'<div style="color:{TEXT_DIM};font-size:0.8rem;padding:10px 14px;">None flagged</div>'
        )
    parts = []
    for i, risk in enumerate(risks):
        sev = _SEV_ORDER[min(i, len(_SEV_ORDER) - 1)]
        title = risk[:60].split("—")[0].split(":")[0].strip() if "—" in risk or ":" in risk else risk[:60]
        desc = risk[len(title):].lstrip("—: ").strip() or risk
        parts.append(risk_row_html(sev, title, desc))
    return "".join(parts)


def _parse_zone_levels(rec: dict, price: float | None) -> str | None:
    """Return zone_kpi_grid_html. Prefers DB columns; falls back to text-parse for legacy rows."""
    entry_lo  = rec.get("entry_low")
    entry_hi  = rec.get("entry_high")
    stop_val  = rec.get("stop_price")
    sup_val   = rec.get("support")
    tgt_val   = rec.get("target")

    try:
        # Prefer structured DB columns (new recs from tool_use path)
        if entry_lo is not None and entry_hi is not None:
            entry_lo, entry_hi = float(entry_lo), float(entry_hi)
            stop_val  = float(stop_val)  if stop_val  is not None else entry_lo * 0.93
            sup_val   = float(sup_val)   if sup_val   is not None else (stop_val + entry_lo) / 2
            tgt_val   = float(tgt_val)   if tgt_val   is not None else entry_hi * 1.14
        else:
            # Legacy text-parse fallback for rows created before M15
            ez = rec.get("entry_zone") or ""
            if not ez:
                return None
            zone = _parse_entry_zone(ez)
            if not zone:
                return None
            entry_lo, entry_hi = zone
            extras = _parse_entry_zone_extras(ez)
            stop_val  = next((x["price"] for x in extras if x["kind"] == "stop"),    None)
            sup_val   = next((x["price"] for x in extras if x["kind"] == "support"), None)
            if stop_val is None and sup_val is None:
                return None
            if stop_val is None:
                stop_val = entry_lo * 0.93
            if sup_val is None:
                sup_val = (stop_val + entry_lo) / 2
            tm = re.search(r'target\D{0,10}\$?([\d,]+\.?\d*)', ez, re.IGNORECASE)
            tgt_val = float(tm.group(1).replace(",", "")) if tm else entry_hi * 1.14

        entry_mid = (entry_lo + entry_hi) / 2
        current = price or entry_mid
        return _zone_kpi_grid_html(stop_val, sup_val, entry_mid, tgt_val, current,
                                   entry_range=(entry_lo, entry_hi))
    except Exception:
        return None


def _runner_html(rec: dict, rank: int, company_name: str = "") -> str:
    score = rec.get("blended_score") or 0
    symbol = rec["symbol"]
    sizing = rec["sizing_pct"] * 100
    rationale = rec.get("rationale") or "—"
    if len(rationale) > 240:
        rationale = rationale[:240].rsplit(".", 1)[0] + "."

    exit_triggers = []
    try:
        exit_triggers = json.loads(rec.get("exit_triggers_json") or "[]")
    except Exception:
        pass
    exit_text = exit_triggers[0] if exit_triggers else ""

    price = rec.get("price_at_scan")
    price_session = rec.get("price_session") or ""
    price_label = price_session if price_session else "close"
    price_span = (
        f'<span style="color:{TEXT_DIM};font-size:0.75rem;">'
        f'<span style="color:{TEXT};font-family:\'DM Mono\',monospace;">${price:,.2f}</span>'
        f'&nbsp;<span style="font-size:0.65rem;">{price_label}</span>'
        f'</span>'
    ) if price else ""

    color = BLUE if rank == 2 else AMBER

    exit_block = (
        f'<div style="margin-top:10px;padding:8px 10px;background:{CARD2};'
        f'border-radius:6px;border-left:2px solid {AMBER};">'
        f'<span style="color:{AMBER};font-size:0.65rem;text-transform:uppercase;'
        f'letter-spacing:0.08em;">Watch for</span>'
        f'<div style="color:{TEXT_MUTED};font-size:0.78rem;margin-top:3px;">{exit_text}</div>'
        f'</div>'
    ) if exit_text else ""

    co_line = (
        f'<div style="color:{TEXT_DIM};font-size:0.72rem;margin-bottom:8px;">{company_name}</div>'
        if company_name else ""
    )
    return f"""
<div style="background:{CARD};border:1px solid {BORDER};border-top:3px solid {color};
            border-radius:10px;padding:20px 22px;box-sizing:border-box;min-height:200px;">
  <div style="color:{TEXT_DIM};font-size:0.65rem;text-transform:uppercase;
              letter-spacing:0.09em;margin-bottom:6px;">#{rank} PICK</div>
  <div style="color:{TEXT};font-family:'DM Mono','IBM Plex Mono',monospace;
              font-size:1.75rem;font-weight:700;margin-bottom:2px;">{symbol}</div>
  {co_line}
  <div style="display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap;">
    <span style="color:{TEXT_DIM};font-size:0.75rem;">
      Score: <span style="color:{TEXT};font-family:'DM Mono',monospace;font-weight:600;">{score:.1f}</span>/100
    </span>
    <span style="color:{TEXT_DIM};font-size:0.75rem;">
      Deploy: <span style="color:{TEXT};font-weight:600;">{sizing:.0f}%</span>
    </span>{price_span}
  </div>
  <div style="color:{TEXT_MUTED};font-size:0.8rem;line-height:1.6;">{rationale}</div>
  {exit_block}
</div>"""


# ── Load today's existing recs ─────────────────────────────────────────────────

existing_recs = load_latest_recommendations()
already_ran = len(existing_recs) > 0

# ── Run expander ───────────────────────────────────────────────────────────────

label = "Run a new recommendation" if not already_ran else "Run again (replace today's)"
with st.expander(label, expanded=not already_ran):
    if already_ran:
        st.caption("Today: 1 run — re-running will overwrite today's recommendations.")
    st.markdown(
        f'<div style="background:{AMBER}11;border:1px solid {AMBER}44;border-radius:8px;'
        f'padding:10px 14px;margin-bottom:10px;color:{TEXT_MUTED};font-size:0.82rem;">'
        f'Full gate + scan + Claude review + Opus synthesis &nbsp;·&nbsp; ~2–4 min &nbsp;·&nbsp; ~$0.05–0.15'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.button("Generate recommendations", type="primary"):
        from swing_lab.dashboard.actions import refresh_recommend

        prog_bar = st.progress(0, text="Starting…")
        prog_placeholder = st.empty()

        TOTAL_STEPS = 3  # scan, review, recommend

        def scan_cb(cur, total, sym):
            frac = 0.0 + 0.35 * (cur / max(total, 1))
            prog_bar.progress(frac, text=f"Scanning {cur}/{total}: {sym}")

        def review_cb(cur, total, sym):
            frac = 0.35 + 0.50 * (cur / max(total, 1))
            prog_bar.progress(frac, text=f"Reviewing {cur}/{total}: {sym}")

        def rec_cb(cur, total, sym):
            prog_bar.progress(0.90, text=sym)

        try:
            batch_id, recs = refresh_recommend(
                scan_progress=scan_cb,
                review_progress=review_cb,
                rec_progress=rec_cb,
            )
            prog_bar.progress(1.0, text="Done!")
            st.session_state["rec_results"] = recs
            st.success(f"Recommendations generated — batch {batch_id}.")
            st.rerun()
        except RuntimeError as exc:
            prog_bar.empty()
            st.error(str(exc))

# ── Resolve which recs to display ─────────────────────────────────────────────

display_recs = st.session_state.get("rec_results") or existing_recs

# ── Display ────────────────────────────────────────────────────────────────────

if not display_recs:
    st.markdown(
        f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;'
        f'padding:32px;text-align:center;margin-top:24px;">'
        f'<div style="color:{TEXT_DIM};font-size:0.85rem;">'
        f'No recommendations yet for today — click <strong>Generate recommendations</strong> above to run the engine.'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
else:
    recs_by_rank = {r["rank"]: r for r in display_recs}
    top = recs_by_rank.get(1)
    second = recs_by_rank.get(2)
    third = recs_by_rank.get(3)

    st.markdown(section_header_html("Today's Top Pick"), unsafe_allow_html=True)

    if top:
        claude_summary = top.get("claude_summary") or ""
        symbol = top["symbol"]
        price = top.get("price_at_scan")
        price_session = top.get("price_session") or "close"
        score = top.get("blended_score") or 0
        sizing = top["sizing_pct"] * 100

        # ── Ticker hero ────────────────────────────────────────────────────
        price_str = f"${price:,.2f}" if price else "—"
        company = _company_name(symbol)
        sub_label = (
            (f'{company} &nbsp;·&nbsp; ' if company else '')
            + f'{price_session} &nbsp;·&nbsp; Score {score:.1f}/100 &nbsp;·&nbsp; Deploy {sizing:.0f}%'
        )
        st.markdown(
            ticker_hero_html(symbol, price_str, "BUY", GREEN, sub_label),
            unsafe_allow_html=True,
        )

        # ── Bull / Bear split (rationale vs exit triggers) ─────────────────
        rationale = top.get("rationale") or ""
        exit_triggers = []
        try:
            exit_triggers = json.loads(top.get("exit_triggers_json") or "[]")
        except Exception:
            pass

        import re as _re
        bull_sentences = [s.strip() for s in _re.split(r'(?<=[.!?])\s+', rationale) if len(s.strip()) > 20][:3]
        st.markdown(bull_bear_split_html(bull_sentences, exit_triggers), unsafe_allow_html=True)

        # ── Zone KPI grid (above candlestick) ─────────────────────────────
        zone_grid = _parse_zone_levels(top, price)
        if zone_grid:
            st.markdown(zone_grid, unsafe_allow_html=True)
        elif top.get("is_synthesized"):
            st.markdown(
                risk_row_html("medium", "Price levels unavailable",
                              "Re-run Rebalance to regenerate overlays."),
                unsafe_allow_html=True,
            )

        # ── Candlestick chart ──────────────────────────────────────────────
        hero_chart = _candle_chart(
            symbol,
            entry_zone_str=top.get("entry_zone", ""),
            price=price,
            session=price_session,
            period="3mo",
            height=380,
            claude_summary=claude_summary,
            entry_low=top.get("entry_low"),
            entry_high=top.get("entry_high"),
            support=top.get("support"),
            stop=top.get("stop_price"),
            target=top.get("target"),
        )
        if hero_chart:
            st.plotly_chart(hero_chart, use_container_width=True)

        # ── Key risks (severity-dot rows) ──────────────────────────────────
        risks = []
        try:
            risks = json.loads(top.get("risks_json") or "[]")
        except Exception:
            pass
        if risks:
            st.markdown(
                f'<div style="color:{TEXT_DIM};font-size:0.65rem;text-transform:uppercase;'
                f'letter-spacing:0.09em;margin:16px 0 8px;">KEY RISKS</div>',
                unsafe_allow_html=True,
            )
            st.markdown(_risks_to_rows(risks), unsafe_allow_html=True)

        # ── Claude analysis expander ───────────────────────────────────────
        if claude_summary:
            with st.expander("Claude's full analysis", expanded=False):
                st.markdown(
                    f'<div style="color:{TEXT_MUTED};font-size:0.875rem;line-height:1.75;'
                    f'white-space:pre-wrap;">{claude_summary}</div>',
                    unsafe_allow_html=True,
                )

    if second or third:
        st.markdown(section_header_html("Runner-Ups"), unsafe_allow_html=True)
        col2, col3 = st.columns(2)
        if second:
            col2.markdown(_runner_html(second, 2, _company_name(second["symbol"])), unsafe_allow_html=True)
            runner2_chart = _candle_chart(
                second["symbol"],
                entry_zone_str=second.get("entry_zone", ""),
                price=second.get("price_at_scan"),
                session=second.get("price_session", ""),
                period="2mo",
                height=220,
                claude_summary=second.get("claude_summary") or "",
            )
            if runner2_chart:
                col2.plotly_chart(runner2_chart, use_container_width=True)
        if third:
            col3.markdown(_runner_html(third, 3, _company_name(third["symbol"])), unsafe_allow_html=True)
            runner3_chart = _candle_chart(
                third["symbol"],
                entry_zone_str=third.get("entry_zone", ""),
                price=third.get("price_at_scan"),
                session=third.get("price_session", ""),
                period="2mo",
                height=220,
                claude_summary=third.get("claude_summary") or "",
            )
            if runner3_chart:
                col3.plotly_chart(runner3_chart, use_container_width=True)


    # Provenance footer
    if display_recs:
        rec = display_recs[0]
        st.markdown(
            f'<div style="color:{TEXT_DIM};font-size:0.72rem;margin-top:28px;">'
            f'Gate sizing: {rec["gate_sizing"]*100:.0f}% &nbsp;·&nbsp; '
            f'Per-position: {rec["sizing_pct"]*100:.0f}% &nbsp;·&nbsp; '
            f'scan_id: {rec.get("scan_id", "—")}'
            f'</div>',
            unsafe_allow_html=True,
        )
