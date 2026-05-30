"""Page 5 — Trade Recommendation Engine."""
import json
import re
import streamlit as st
from swing_lab.dashboard import sidebar_chat
from swing_lab.dashboard.theme import (
    inject, section_header_html, make_fig,
    BG, CARD, CARD2, BORDER, TEXT, TEXT_MUTED, TEXT_DIM,
    ACCENT, GREEN, RED, AMBER, BLUE,
)
from swing_lab.dashboard.lib import load_latest_recommendations

_PURPLE = "#a855f7"


@st.cache_data(ttl=300)
def _fetch_history(symbol: str, period: str):
    import yfinance as yf
    return yf.Ticker(symbol).history(period=period)


def _parse_entry_zone(text: str) -> tuple[float, float] | None:
    """Extract (low, high) from strings like '$142–$145' or '$142.00 – $145.00'. Returns None if unparseable."""
    # Require leading digit to avoid matching standalone commas (e.g. "…$1,640, near…")
    nums = [float(m.replace(",", "")) for m in re.findall(r"\d[\d,]*\.?\d*", text or "")]
    if len(nums) >= 2:
        return min(nums[0], nums[1]), max(nums[0], nums[1])
    return None


def _parse_entry_zone_extras(text: str) -> list[dict]:
    """Extract support shelf, chase limit, and stop levels from entry_zone text.

    Returns list of dicts:
      {"kind": "support"|"chase_limit"|"stop", "price": float}
    """
    if not text:
        return []

    def _clean(s: str) -> float:
        return float(s.replace(",", ""))

    levels: list[dict] = []
    seen: set[int] = set()

    def _add(kind: str, raw: str) -> None:
        try:
            p = _clean(raw)
        except ValueError:
            return
        if p <= 0 or round(p) in seen:
            return
        seen.add(round(p))
        levels.append({"kind": kind, "price": p})

    # Support: "$1,750 support" or "support at/near/shelf $1,750"
    for m in re.finditer(r'\$(\d[\d,]*\.?\d*)\s+support', text, re.IGNORECASE):
        _add("support", m.group(1))
    for m in re.finditer(r'support(?:\s+shelf)?\D{0,20}\$(\d[\d,]*\.?\d*)', text, re.IGNORECASE):
        _add("support", m.group(1))

    # Chase limit: "avoid chasing above $X" / "avoid above $X" / "do not chase above $X"
    for m in re.finditer(
        r"(?:avoid(?:\s+chasing?)?|do\s+not\s+chase?|don'?t\s+chase?)"
        r"\s+above\s+\$(\d[\d,]*\.?\d*)",
        text, re.IGNORECASE,
    ):
        _add("chase_limit", m.group(1))

    # Stop loss: "stop at/below/loss $X"
    for m in re.finditer(r'stop(?:\s+loss)?\s+(?:at|below|under)\s+\$(\d[\d,]*\.?\d*)', text, re.IGNORECASE):
        _add("stop", m.group(1))
    for m in re.finditer(r'stop(?:\s+loss)?\D{0,6}\$(\d[\d,]*\.?\d*)', text, re.IGNORECASE):
        _add("stop", m.group(1))

    return levels


def _parse_price_levels(text: str) -> list[dict]:
    """Extract named price ranges and single levels from Claude summary text.

    Returns list of dicts:
      {"type": "range", "lo": float, "hi": float, "label": str}
      {"type": "single", "price": float, "label": str}
    """
    if not text:
        return []
    try:
        levels = []
        seen: set[int] = set()

        def _clean(s: str) -> float:
            v = s.replace(",", "")
            if not v:
                raise ValueError(f"empty after strip: {s!r}")
            return float(v)

        # Ranges: "$142–$145", "$142-$145", "$142 to $145"
        for m in re.finditer(
            r'\$(\d[\d,]*\.?\d*)\s*(?:–|-|to)\s*\$?(\d[\d,]*\.?\d*)', text
        ):
            try:
                lo, hi = _clean(m.group(1)), _clean(m.group(2))
            except (ValueError, ZeroDivisionError):
                continue
            if lo <= 0 or hi <= 0:
                continue
            if lo > hi:
                lo, hi = hi, lo
            if lo == hi or (hi - lo) / lo > 0.5:
                continue
            ctx = text[max(0, m.start() - 35):m.start()].lower()
            label = (
                "Support" if "support" in ctx else
                "Resistance" if "resist" in ctx else
                "Target" if "target" in ctx else
                "Fair value" if "fair" in ctx else
                "Range"
            )
            levels.append({"type": "range", "lo": lo, "hi": hi, "label": label})
            seen.update([round(lo), round(hi)])

        # Single levels: "support at $142", "resistance near $160", "target of $170"
        for m in re.finditer(
            r'(support|resistance|target|fair[\s\-]?value)\D{0,20}\$(\d[\d,]*\.?\d*)',
            text, re.IGNORECASE,
        ):
            try:
                p = _clean(m.group(2))
            except ValueError:
                continue
            if p <= 1 or round(p) in seen:
                continue
            levels.append({"type": "single", "price": p, "label": m.group(1).strip().title()})
            seen.add(round(p))

        return levels
    except Exception:
        return []


def _candle_chart(symbol: str, entry_zone_str: str = "", price: float | None = None,
                  session: str = "", period: str = "3mo", height: int = 380,
                  claude_summary: str = ""):
    """Return a themed Plotly candlestick figure, or None on failure."""
    import plotly.graph_objects as go
    _DISPLAY_DAYS = {"1mo": 21, "2mo": 42, "3mo": 63, "6mo": 126}
    try:
        # Always fetch 6mo to warm up both SMAs; trim to display period afterward
        hist_full = _fetch_history(symbol, "6mo")
        if hist_full is None or hist_full.empty:
            return None

        sma20 = hist_full["Close"].rolling(20).mean()
        sma50 = hist_full["Close"].rolling(50).mean()

        n = _DISPLAY_DAYS.get(period, 63)
        hist = hist_full.iloc[-n:]
        sma20 = sma20.iloc[-n:]
        sma50 = sma50.iloc[-n:]

        fig = make_fig(
            height=height,
            title=dict(text=f"{symbol} · {period}", font=dict(size=11)),
            xaxis=dict(rangeslider=dict(visible=False), type="date"),
            yaxis=dict(tickprefix="$"),
            showlegend=False,
        )

        fig.add_trace(go.Scatter(
            x=hist.index, y=sma50,
            mode="lines",
            line=dict(color=AMBER, width=1, dash="dot"),
            name="SMA50", showlegend=False,
            hovertemplate="SMA50: $%{y:,.2f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=hist.index, y=sma20,
            mode="lines",
            line=dict(color=BLUE, width=1, dash="dot"),
            fill="tonexty",
            fillcolor="rgba(59,130,246,0.07)",
            name="SMA20", showlegend=False,
            hovertemplate="SMA20: $%{y:,.2f}<extra></extra>",
        ))

        # SMA labels at rightmost point
        last_x = hist.index[-1]
        if len(sma20.dropna()) > 0:
            fig.add_annotation(
                x=last_x, y=sma20.dropna().iloc[-1],
                xref="x", yref="y",
                text="20d", showarrow=False,
                font=dict(color=BLUE, size=8),
                xanchor="left", yanchor="middle",
                bgcolor=CARD, borderpad=1,
            )
        if len(sma50.dropna()) > 0:
            fig.add_annotation(
                x=last_x, y=sma50.dropna().iloc[-1],
                xref="x", yref="y",
                text="50d", showarrow=False,
                font=dict(color=AMBER, size=8),
                xanchor="left", yanchor="middle",
                bgcolor=CARD, borderpad=1,
            )

        fig.add_trace(go.Candlestick(
            x=hist.index,
            open=hist["Open"],
            high=hist["High"],
            low=hist["Low"],
            close=hist["Close"],
            increasing=dict(line=dict(color=GREEN, width=1), fillcolor="rgba(34,197,94,0.45)"),
            decreasing=dict(line=dict(color=RED, width=1), fillcolor="rgba(239,68,68,0.45)"),
            name=symbol,
            showlegend=False,
            hovertemplate=(
                "<b>%{x|%b %d}</b><br>"
                "O: $%{open:,.2f}  H: $%{high:,.2f}<br>"
                "L: $%{low:,.2f}  C: $%{close:,.2f}<extra></extra>"
            ),
        ))

        # Collect all horizontal level labels; draw hlines/hrects now, labels later.
        # All level labels go on the LEFT to keep the right side clear for recent action.
        # left_labels: list of (price, text, color, font_size)
        left_labels: list[tuple[float, str, str, int]] = []

        # Entry zone band (or single-price fallback)
        zone = _parse_entry_zone(entry_zone_str)
        if zone:
            z_lo, z_hi = zone
            fig.add_hrect(
                y0=z_lo, y1=z_hi,
                fillcolor="rgba(34,197,94,0.10)",
                layer="below",
                line=dict(color=GREEN, width=0.8, dash="dot"),
            )
            left_labels.append((z_hi, f"Entry  ${z_lo:,.2f}–${z_hi:,.2f}", GREEN, 9))
        else:
            single = re.findall(r"[\d,]+\.?\d*", entry_zone_str or "")
            if single:
                ep = float(single[0].replace(",", ""))
                fig.add_hline(y=ep, line=dict(color=GREEN, dash="dot", width=1))
                left_labels.append((ep, f"Entry  ${ep:,.2f}", GREEN, 9))

        # Entry-zone extras: support shelf, chase limit, stop loss
        _KIND_STYLE = {
            "support":     (AMBER, "Support",     "dash"),
            "chase_limit": (RED,   "Avoid above", "dash"),
            "stop":        (RED,   "Stop",        "dashdot"),
        }
        for lvl in _parse_entry_zone_extras(entry_zone_str):
            color, label, dash = _KIND_STYLE.get(lvl["kind"], (TEXT_DIM, lvl["kind"].title(), "dot"))
            p = lvl["price"]
            fig.add_hline(y=p, line=dict(color=color, dash=dash, width=0.9))
            left_labels.append((p, f"{label}  ${p:,.2f}", color, 9))

        # Claude analysis levels (support/resistance/targets from review text)
        for lvl in _parse_price_levels(claude_summary):
            if lvl["type"] == "range":
                fig.add_hrect(
                    y0=lvl["lo"], y1=lvl["hi"],
                    fillcolor="rgba(168,85,247,0.07)",
                    layer="below",
                    line=dict(color=_PURPLE, width=0.5, dash="dot"),
                )
                left_labels.append((lvl["hi"], f"{lvl['label']}  ${lvl['lo']:,.0f}–${lvl['hi']:,.0f}", _PURPLE, 8))
            else:
                fig.add_hline(y=lvl["price"], line=dict(color=_PURPLE, dash="dot", width=0.8))
                left_labels.append((lvl["price"], f"{lvl['label']}  ${lvl['price']:,.2f}", _PURPLE, 8))

        # Place all left-side labels: sort ascending by price, strictly alternate
        # yanchor bottom/top so every consecutive pair lands on opposite sides of
        # its line — guarantees no overlap regardless of how close the prices are.
        # "bottom" → text floats above the line; "top" → text hangs below.
        if left_labels:
            sorted_labels = sorted(left_labels, key=lambda t: t[0])
            left_x = hist.index[0]
            anchors = ["bottom", "top"]
            for i, (lbl_price, lbl_text, lbl_color, lbl_size) in enumerate(sorted_labels):
                fig.add_annotation(
                    x=left_x, y=lbl_price,
                    xref="x", yref="y",
                    text=lbl_text,
                    showarrow=False,
                    font=dict(color=lbl_color, size=lbl_size),
                    xanchor="left", yanchor=anchors[i % 2],
                    bgcolor=CARD, borderpad=2,
                )

        # Current price line — right side only, so it doesn't compete with level labels
        if price:
            price_label = f"${price:,.2f}"
            if session:
                price_label += f"  [{session}]"
            fig.add_hline(
                y=price,
                line=dict(color=ACCENT, dash="dash", width=1.2),
            )
            fig.add_annotation(
                x=hist.index[-1], y=price,
                xref="x", yref="y",
                text=price_label,
                showarrow=False,
                font=dict(color=ACCENT, size=9),
                xanchor="right", yanchor="bottom",
                bgcolor=CARD, borderpad=2,
            )

        return fig
    except Exception as _e:
        import traceback
        traceback.print_exc()
        return None


st.set_page_config(
    page_title="Recommendation — Swing Lab",
    layout="wide",
)
inject()
st.session_state["current_page"] = "recommendation"
sidebar_chat.render()

st.title("Trade Recommendation Engine")
st.markdown(
    "Top 3 momentum picks synthesized from the macro gate, scanner, and Claude reviews. "
    "The #1 pick gets a live Claude synthesis; #2/#3 are composed from stored review data."
)

# ── Helper: hero card for #1 pick ─────────────────────────────────────────────

def _hero_html(rec: dict) -> str:
    score = rec.get("blended_score") or 0
    symbol = rec["symbol"]
    sizing = rec["sizing_pct"] * 100
    rationale = rec.get("rationale") or "—"
    entry_zone = rec.get("entry_zone", "")
    price = rec.get("price_at_scan")
    price_session = rec.get("price_session") or ""
    price_label = price_session if price_session else "close"
    price_html = (
        f'<div style="color:{TEXT_DIM};font-size:0.75rem;margin-top:6px;'
        f'font-family:\'DM Mono\',\'IBM Plex Mono\',monospace;">'
        f'${price:,.2f}&nbsp;<span style="font-size:0.65rem;letter-spacing:0.05em;">{price_label}</span></div>'
    ) if price else ""

    risks = []
    try:
        risks = json.loads(rec.get("risks_json") or "[]")
    except Exception:
        pass

    exit_triggers = []
    try:
        exit_triggers = json.loads(rec.get("exit_triggers_json") or "[]")
    except Exception:
        pass

    risks_html = "".join(
        f'<li style="color:{TEXT_MUTED};margin-bottom:6px;">{r}</li>'
        for r in risks
    ) if risks else f'<li style="color:{TEXT_DIM};">None flagged</li>'

    exit_html_items = "".join(
        f'<li style="color:{TEXT_MUTED};margin-bottom:6px;">{t}</li>'
        for t in exit_triggers
    ) if exit_triggers else f'<li style="color:{TEXT_DIM};">—</li>'

    entry_html = (
        f'<div style="margin-top:20px;padding:10px 14px;background:{CARD2};'
        f'border-radius:8px;border-left:3px solid {ACCENT};">'
        f'<span style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;'
        f'letter-spacing:0.09em;">Entry zone</span>'
        f'<div style="color:{TEXT};font-size:0.9rem;margin-top:4px;">{entry_zone}</div>'
        f'</div>'
    ) if entry_zone else ""

    return f"""
<div style="background:{CARD};border:1px solid {BORDER};border-top:4px solid {GREEN};
            border-radius:14px;padding:28px 32px;margin-bottom:24px;">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px;">
    <div>
      <div style="color:{TEXT_DIM};font-size:0.65rem;text-transform:uppercase;
                  letter-spacing:0.1em;margin-bottom:6px;">&gt;&gt; TOP RECOMMENDATION</div>
      <div style="color:{TEXT};font-family:'DM Mono','IBM Plex Mono',monospace;
                  font-size:2.6rem;font-weight:700;line-height:1;">{symbol}</div>{price_html}
    </div>
    <div style="text-align:right;">
      <span style="background:{GREEN}22;color:{GREEN};font-size:0.8rem;font-weight:600;
                   padding:6px 20px;border-radius:20px;text-transform:uppercase;
                   letter-spacing:0.06em;">BUY</span>
      <div style="color:{TEXT_DIM};font-size:0.72rem;margin-top:10px;">
        Blended score &nbsp;
        <span style="color:{TEXT};font-family:'DM Mono',monospace;font-size:1.15rem;
                     font-weight:700;">{score:.1f}
          <span style="font-size:0.72rem;font-weight:400;color:{TEXT_DIM};">/100</span>
        </span>
      </div>
    </div>
  </div>
  <div style="background:{CARD2};border-radius:8px;padding:10px 16px;margin-bottom:22px;">
    <span style="color:{ACCENT};font-size:0.95rem;margin-right:8px;">▶</span>
    <span style="color:{TEXT};font-size:0.875rem;">
      Deploy <strong>{sizing:.0f}%</strong> of portfolio budget
    </span>
  </div>
  <div style="color:{TEXT_DIM};font-size:0.65rem;text-transform:uppercase;
              letter-spacing:0.09em;margin-bottom:8px;">WHY THIS TRADE</div>
  <div style="color:{TEXT_MUTED};font-size:0.875rem;line-height:1.65;
              margin-bottom:22px;">{rationale}</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:4px;">
    <div>
      <div style="color:{TEXT_DIM};font-size:0.65rem;text-transform:uppercase;
                  letter-spacing:0.09em;margin-bottom:8px;">KEY RISKS</div>
      <ul style="color:{TEXT_MUTED};font-size:0.875rem;line-height:1.6;
                 padding-left:18px;margin:0;">
        {risks_html}
      </ul>
    </div>
    <div>
      <div style="color:{AMBER};font-size:0.65rem;text-transform:uppercase;
                  letter-spacing:0.09em;margin-bottom:8px;">WHAT WOULD MAKE THIS WRONG</div>
      <ul style="color:{TEXT_MUTED};font-size:0.875rem;line-height:1.6;
                 padding-left:18px;margin:0;">
        {exit_html_items}
      </ul>
    </div>
  </div>
  {entry_html}
</div>"""


def _runner_html(rec: dict, rank: int) -> str:
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

    return f"""
<div style="background:{CARD};border:1px solid {BORDER};border-top:3px solid {color};
            border-radius:10px;padding:20px 22px;box-sizing:border-box;min-height:200px;">
  <div style="color:{TEXT_DIM};font-size:0.65rem;text-transform:uppercase;
              letter-spacing:0.09em;margin-bottom:6px;">#{rank} PICK</div>
  <div style="color:{TEXT};font-family:'DM Mono','IBM Plex Mono',monospace;
              font-size:1.75rem;font-weight:700;margin-bottom:10px;">{symbol}</div>
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
    st.warning(
        "This runs a full gate + scan + Claude review, then calls Claude Opus once "
        "to synthesize the #1 pick. Expect 2–4 minutes and ~$0.05–0.15 in API cost.",
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
        f"""
<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;
            padding:32px;text-align:center;margin-top:24px;">
  <div style="color:{TEXT_DIM};font-size:1.5rem;margin-bottom:12px;">[empty]</div>
  <div style="color:{TEXT_MUTED};font-size:0.9rem;">
    No recommendations yet for today.<br>
    Click <strong>Generate recommendations</strong> above to run the engine.
  </div>
</div>""",
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
        st.markdown(_hero_html(top), unsafe_allow_html=True)
        hero_chart = _candle_chart(
            top["symbol"],
            entry_zone_str=top.get("entry_zone", ""),
            price=top.get("price_at_scan"),
            session=top.get("price_session", ""),
            period="3mo",
            height=380,
            claude_summary=claude_summary,
        )
        if hero_chart:
            st.plotly_chart(hero_chart, use_container_width=True)
        if claude_summary:
            with st.expander("Claude's full analysis", expanded=False):
                st.markdown(
                    f'<div style="color:{TEXT_MUTED};font-size:0.875rem;line-height:1.75;'
                    f'white-space:pre-wrap;">{claude_summary}</div>',
                    unsafe_allow_html=True,
                )
        if top.get("rec_id"):
            if st.button(
                f"Open trade from this pick — {top['symbol']}",
                type="primary",
                key="open_from_rec_btn",
            ):
                st.session_state["open_from_rec"] = {
                    "symbol": top["symbol"],
                    "sizing_pct": top["sizing_pct"],
                    "rec_id": top["rec_id"],
                }
                st.switch_page("pages/4_Trade_Log.py")

    if second or third:
        st.markdown(section_header_html("Runner-Ups"), unsafe_allow_html=True)
        col2, col3 = st.columns(2)
        if second:
            col2.markdown(_runner_html(second, 2), unsafe_allow_html=True)
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
            col3.markdown(_runner_html(third, 3), unsafe_allow_html=True)
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
