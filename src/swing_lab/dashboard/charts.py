"""Shared Plotly chart helpers for the Swing Lab dashboard."""
import re
import streamlit as st
import pandas as pd
from swing_lab.dashboard.theme import (
    make_fig, CARD, GREEN, RED, AMBER, BLUE, ACCENT,
    TEXT, TEXT_DIM,
)

_PURPLE = "#a855f7"


@st.cache_data(ttl=300)
def fetch_history(symbol: str, period: str, interval: str = "1d"):
    import yfinance as yf
    return yf.Ticker(symbol).history(period=period, interval=interval)


def parse_entry_zone(text: str) -> tuple[float, float] | None:
    """Extract (low, high) from strings like '$142–$145'. Returns None if unparseable."""
    nums = [float(m.replace(",", "")) for m in re.findall(r"\d[\d,]*\.?\d*", text or "")]
    if len(nums) >= 2:
        return min(nums[0], nums[1]), max(nums[0], nums[1])
    return None


def parse_entry_zone_extras(text: str) -> list[dict]:
    """Extract support shelf, chase limit, and stop levels from entry_zone text."""
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

    for m in re.finditer(r'\$(\d[\d,]*\.?\d*)\s+support', text, re.IGNORECASE):
        _add("support", m.group(1))
    for m in re.finditer(r'support(?:\s+shelf)?\D{0,20}\$(\d[\d,]*\.?\d*)', text, re.IGNORECASE):
        _add("support", m.group(1))

    for m in re.finditer(
        r"(?:avoid(?:\s+chasing?)?|do\s+not\s+chase?|don'?t\s+chase?)"
        r"\s+above\s+\$(\d[\d,]*\.?\d*)",
        text, re.IGNORECASE,
    ):
        _add("chase_limit", m.group(1))

    for m in re.finditer(r'stop(?:\s+loss)?\s+(?:at|below|under)\s+\$(\d[\d,]*\.?\d*)', text, re.IGNORECASE):
        _add("stop", m.group(1))
    for m in re.finditer(r'stop(?:\s+loss)?\D{0,6}\$(\d[\d,]*\.?\d*)', text, re.IGNORECASE):
        _add("stop", m.group(1))

    return levels


def parse_price_levels(text: str) -> list[dict]:
    """Extract named price ranges and single levels from Claude summary text."""
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

        for m in re.finditer(r'\$(\d[\d,]*\.?\d*)\s*(?:–|-|to)\s*\$?(\d[\d,]*\.?\d*)', text):
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


def candle_chart(symbol: str, entry_zone_str: str = "", price: float | None = None,
                 session: str = "", period: str = "3mo", height: int = 380,
                 claude_summary: str = "",
                 trade_entry_price: float | None = None,
                 trade_entry_date: str | None = None,
                 *,
                 entry_low: float | None = None, entry_high: float | None = None,
                 support: float | None = None, stop: float | None = None,
                 target: float | None = None,
                 swing_lows: list | None = None,
                 swing_highs: list | None = None):
    """Themed Plotly candlestick with entry/support/stop/target overlays. Returns None on failure.

    Explicit keyword args (entry_low/entry_high/support/stop/target) take priority over
    text-parsing entry_zone_str. Pass them from DB columns to guarantee consistent overlays.

    trade_entry_price / trade_entry_date: actual filled price and date for an open position.
    Rendered as a distinct white dotted hline + vertical entry marker.
    """
    import plotly.graph_objects as go
    _DISPLAY_DAYS = {"1mo": 21, "2mo": 42, "3mo": 63, "6mo": 126}
    try:
        hist_full = fetch_history(symbol, "1y")
        if hist_full is None or hist_full.empty:
            return None

        sma20  = hist_full["Close"].rolling(20).mean()
        sma50  = hist_full["Close"].rolling(50).mean()
        sma200 = hist_full["Close"].rolling(200).mean()

        n = _DISPLAY_DAYS.get(period, 63)
        hist   = hist_full.iloc[-n:]
        sma20  = sma20.iloc[-n:]
        sma50  = sma50.iloc[-n:]
        sma200 = sma200.iloc[-n:]

        fig = make_fig(
            height=height,
            title=dict(text=symbol, pad=dict(l=12, t=8)),
            margin=dict(l=48, r=32, t=48, b=40),
            xaxis=dict(rangeslider=dict(visible=False), type="date"),
            yaxis=dict(tickprefix="$"),
            showlegend=False,
        )

        _sma200_clean = sma200.dropna()
        if len(_sma200_clean) > 0:
            fig.add_trace(go.Scatter(
                x=sma200.index, y=sma200,
                mode="lines",
                line=dict(color=_PURPLE, width=1, dash="dot"),
                name="SMA200", showlegend=False,
                hovertemplate="SMA200: $%{y:,.2f}<extra></extra>",
            ))

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
        if len(_sma200_clean) > 0:
            fig.add_annotation(
                x=last_x, y=_sma200_clean.iloc[-1],
                xref="x", yref="y",
                text="200d", showarrow=False,
                font=dict(color=_PURPLE, size=8),
                xanchor="left", yanchor="middle",
                bgcolor=CARD, borderpad=1,
            )

        # Swing pivot markers — orange triangles showing what was fed to Claude
        _PIVOT_COLOR = "rgba(251,146,60,0.85)"
        _now = pd.Timestamp.now(tz=hist.index.tz)
        if swing_lows:
            fig.add_trace(go.Scatter(
                x=[_now - pd.Timedelta(days=d) for _, d in swing_lows],
                y=[p for p, _ in swing_lows],
                mode="markers",
                marker=dict(symbol="triangle-up", color=_PIVOT_COLOR, size=9,
                            line=dict(color="rgba(0,0,0,0.3)", width=1)),
                name="Swing Low", showlegend=False,
                hovertemplate="Swing Low (fed to Claude): $%{y:,.2f}<extra></extra>",
            ))
        if swing_highs:
            fig.add_trace(go.Scatter(
                x=[_now - pd.Timedelta(days=d) for _, d in swing_highs],
                y=[p for p, _ in swing_highs],
                mode="markers",
                marker=dict(symbol="triangle-down", color=_PIVOT_COLOR, size=9,
                            line=dict(color="rgba(0,0,0,0.3)", width=1)),
                name="Swing High", showlegend=False,
                hovertemplate="Swing High (fed to Claude): $%{y:,.2f}<extra></extra>",
            ))

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

        left_labels: list[tuple[float, str, str, int, str]] = []

        _KIND_STYLE = {
            "support":     (AMBER, "Support",     "dash",    "top"),
            "chase_limit": (RED,   "Avoid above", "dash",    "bottom"),
            "stop":        (RED,   "Stop",        "dashdot", "top"),
            "target":      (BLUE,  "Target",      "dot",     "bottom"),
        }

        # Use explicit structured levels when provided (new recs), else text-parse (legacy)
        _use_explicit = all(v is not None for v in (entry_low, entry_high, support, stop, target))
        if _use_explicit:
            zone = (float(entry_low), float(entry_high))
            z_lo, z_hi = zone
            fig.add_hrect(
                y0=z_lo, y1=z_hi,
                fillcolor="rgba(34,197,94,0.10)",
                layer="below",
                line=dict(color=GREEN, width=0.8, dash="dot"),
            )
            left_labels.append((z_hi, f"Entry  ${z_lo:,.2f}–${z_hi:,.2f}", GREEN, 9, "top"))
            extras = [
                {"kind": "support", "price": float(support)},
                {"kind": "stop",    "price": float(stop)},
                {"kind": "target",  "price": float(target)},
            ]
        else:
            zone = parse_entry_zone(entry_zone_str)
            if zone:
                z_lo, z_hi = zone
                fig.add_hrect(
                    y0=z_lo, y1=z_hi,
                    fillcolor="rgba(34,197,94,0.10)",
                    layer="below",
                    line=dict(color=GREEN, width=0.8, dash="dot"),
                )
                left_labels.append((z_hi, f"Entry  ${z_lo:,.2f}–${z_hi:,.2f}", GREEN, 9, "top"))
            else:
                single = re.findall(r"[\d,]+\.?\d*", entry_zone_str or "")
                if single:
                    ep = float(single[0].replace(",", ""))
                    fig.add_hline(y=ep, line=dict(color=GREEN, dash="dot", width=1))
                    left_labels.append((ep, f"Entry  ${ep:,.2f}", GREEN, 9, "bottom"))

            extras = parse_entry_zone_extras(entry_zone_str)
            _seen_kinds = {x["kind"] for x in extras}

            if zone and "stop" not in _seen_kinds:
                extras.append({"kind": "stop", "price": round(zone[0] * 0.93, 2)})

            if "target" not in _seen_kinds and "chase_limit" not in _seen_kinds:
                _tm = re.search(r'target\D{0,10}\$?([\d,]+\.?\d*)', entry_zone_str or "", re.IGNORECASE)
                _tp = float(_tm.group(1).replace(",", "")) if _tm else (zone[1] * 1.14 if zone else None)
                if _tp:
                    extras.append({"kind": "target", "price": round(_tp, 2)})

        for lvl in extras:
            color, label, dash, yanchor = _KIND_STYLE.get(
                lvl["kind"], (TEXT_DIM, lvl["kind"].title(), "dot", "bottom")
            )
            p = lvl["price"]
            fig.add_hline(y=p, line=dict(color=color, dash=dash, width=0.9))
            left_labels.append((p, f"{label}  ${p:,.2f}", color, 9, yanchor))

        for i, lvl in enumerate(parse_price_levels(claude_summary)):
            if lvl["type"] == "range":
                fig.add_hrect(
                    y0=lvl["lo"], y1=lvl["hi"],
                    fillcolor="rgba(168,85,247,0.07)",
                    layer="below",
                    line=dict(color=_PURPLE, width=0.5, dash="dot"),
                )
                left_labels.append((lvl["hi"], f"{lvl['label']}  ${lvl['lo']:,.0f}–${lvl['hi']:,.0f}", _PURPLE, 8, "top"))
            else:
                fig.add_hline(y=lvl["price"], line=dict(color=_PURPLE, dash="dot", width=0.8))
                left_labels.append((lvl["price"], f"{lvl['label']}  ${lvl['price']:,.2f}", _PURPLE, 8, "bottom" if i % 2 == 0 else "top"))

        if left_labels:
            left_x = hist.index[0]
            for lbl_price, lbl_text, lbl_color, lbl_size, lbl_anchor in left_labels:
                fig.add_annotation(
                    x=left_x, y=lbl_price,
                    xref="x", yref="y",
                    text=lbl_text,
                    showarrow=False,
                    font=dict(color=lbl_color, size=lbl_size),
                    xanchor="left", yanchor=lbl_anchor,
                    bgcolor=CARD, borderpad=2,
                )

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

        # Trade entry markers: actual fill price (hline) + entry date (vline)
        _WHITE = "rgba(255,255,255,0.55)"
        if trade_entry_price and trade_entry_price > 0:
            fig.add_hline(
                y=trade_entry_price,
                line=dict(color=_WHITE, dash="dot", width=1),
            )
            fig.add_annotation(
                x=hist.index[-1], y=trade_entry_price,
                xref="x", yref="y",
                text=f"My entry  ${trade_entry_price:,.2f}",
                showarrow=False,
                font=dict(color=_WHITE, size=8),
                xanchor="right", yanchor="top",
                bgcolor=CARD, borderpad=2,
            )
        if trade_entry_date:
            try:
                entry_ts = pd.Timestamp(trade_entry_date[:10]).tz_localize("UTC")
                if hist.index[0] <= entry_ts <= hist.index[-1]:
                    fig.add_vline(
                        x=entry_ts.isoformat(),
                        line=dict(color=_WHITE, dash="dot", width=1),
                    )
            except Exception:
                pass

        return fig
    except Exception:
        import traceback
        traceback.print_exc()
        return None
