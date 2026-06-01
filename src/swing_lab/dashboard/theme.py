"""Warm Graphite visual theme for the Swing Lab Streamlit dashboard.

Shared by all pages — call inject() once per page after set_page_config().
"""
import streamlit as st
import plotly.graph_objects as go

# ── Palette (mirrors Finance Tracker / Hub design-tokens.css) ──────────────────
BG          = "#111216"
CARD        = "#1a1c22"
CARD2       = "#20222a"
BORDER      = "#272931"
SIDEBAR_BG  = "#0e0f13"
TEXT        = "#f2f2f5"
TEXT_MUTED  = "#9da0b8"
TEXT_DIM    = "#8c8fa8"
ACCENT      = "#6366f1"   # indigo
GREEN       = "#22c55e"
RED         = "#ef4444"
AMBER       = "#f59e0b"
BLUE        = "#3b82f6"
PURPLE      = "#7c6af7"

CHART_COLORS = [ACCENT, GREEN, AMBER, RED, BLUE, PURPLE, "#0ea5e9", "#f43f5e"]

# ── Type scale ──────────────────────────────────────────────────────────────────
FS_2XS  = "0.62rem"
FS_XS   = "0.68rem"
FS_SM   = "0.78rem"
FS_MD   = "0.85rem"
FS_BASE = "0.875rem"   # standard Streamlit UI text (nav, tabs, expanders, page links)
FS_LG   = "0.95rem"
FS_XL   = "1.05rem"
FS_2XL  = "1.6rem"
FS_3XL  = "2rem"
FS_4XL  = "2.8rem"
FS_5XL  = "4.5rem"

# ── Spacing scale (px) ──────────────────────────────────────────────────────────
SP_1 = "4px"
SP_2 = "8px"
SP_3 = "12px"
SP_4 = "16px"
SP_5 = "20px"
SP_6 = "24px"
SP_8 = "32px"
SP_9 = "36px"

# ── Component tokens ────────────────────────────────────────────────────────────
RADIUS    = "10px"   # standard cards, expanders
RADIUS_LG = "14px"   # hero / composite score cards
RADIUS_SM = "8px"    # tags, buttons, inputs
RADIUS_XS = "6px"    # inline chips
TRANS     = "0.15s ease"  # standard UI transition

# ── Plotly base layout ─────────────────────────────────────────────────────────
_PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",  # transparent — blends with page background
    plot_bgcolor=CARD,
    font=dict(
        family="'IBM Plex Sans', system-ui, sans-serif",
        color=TEXT,
        size=12,
    ),
    xaxis=dict(
        gridcolor=BORDER,
        linecolor=BORDER,
        tickfont=dict(color=TEXT_DIM, size=11, family="'DM Mono', monospace"),
        zerolinecolor=BORDER,
    ),
    yaxis=dict(
        gridcolor=BORDER,
        linecolor=BORDER,
        tickfont=dict(color=TEXT_DIM, size=11, family="'DM Mono', monospace"),
        zerolinecolor=BORDER,
    ),
    legend=dict(
        bgcolor=CARD2,
        bordercolor=BORDER,
        borderwidth=1,
        font=dict(color=TEXT_MUTED, size=11),
    ),
    margin=dict(l=48, r=32, t=36, b=40),
    hoverlabel=dict(
        bgcolor=CARD2,
        bordercolor=BORDER,
        font=dict(color=TEXT, size=12),
    ),
    title=dict(
        text="",  # explicit empty prevents Plotly.js from rendering "undefined"
        font=dict(color=TEXT_DIM, size=12, family="'DM Mono', 'IBM Plex Mono', monospace"),
        x=0,
        pad=dict(l=0, t=0),
    ),
)


def make_fig(**layout_overrides) -> go.Figure:
    """Return a pre-themed Plotly Figure. Pass keyword args to override layout."""
    fig = go.Figure()
    merged = {**_PLOTLY_LAYOUT}
    for k, v in layout_overrides.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    fig.update_layout(**merged)
    return fig


# ── HTML helpers ───────────────────────────────────────────────────────────────

def metric_html(label: str, value: str, sub: str = "", accent_color: str = ACCENT) -> str:
    sub_block = (
        f'<div style="color:{TEXT_DIM};font-size:{FS_SM};margin-top:{SP_1};">{sub}</div>'
        if sub else ""
    )
    return f"""
<div style="background:{CARD};border:1px solid {BORDER};border-top:2px solid {accent_color};
            border-radius:{RADIUS};padding:{SP_5} {SP_6};">
    <div style="color:{TEXT_DIM};font-size:{FS_XS};text-transform:uppercase;
                letter-spacing:0.09em;margin-bottom:{SP_2};">{label}</div>
    <div style="color:{TEXT};font-family:'DM Mono','IBM Plex Mono',monospace;
                font-size:{FS_2XL};font-weight:600;line-height:1.1;">{value}</div>
    {sub_block}
</div>"""


def score_card_html(name: str, val: float, flag_note: str = "") -> str:
    color = GREEN if val >= 70 else (AMBER if val >= 40 else RED)
    label = "Healthy" if val >= 70 else ("Caution" if val >= 40 else "Warning")
    flag_block = (
        f'<div style="color:{RED};font-size:{FS_SM};margin-top:{SP_2};line-height:1.35;">'
        f'[!] {flag_note}</div>'
    ) if flag_note and val < 20 else ""
    return f"""
<div style="background:{CARD};border:1px solid {BORDER};border-top:3px solid {color};
            border-radius:{RADIUS};padding:{SP_5} {SP_5};height:100%;box-sizing:border-box;">
    <div style="color:{TEXT_DIM};font-size:{FS_XS};text-transform:uppercase;
                letter-spacing:0.08em;margin-bottom:{SP_2};">{name}</div>
    <div style="color:{TEXT};font-family:'DM Mono','IBM Plex Mono',monospace;
                font-size:{FS_3XL};font-weight:700;line-height:1;">
        {val:.0f}<span style="color:{TEXT_DIM};font-size:{FS_XL};font-weight:400;">/100</span>
    </div>
    <div style="margin-top:{SP_2};">
        <span style="background:{color}22;color:{color};font-size:{FS_SM};font-weight:600;
                     padding:3px 10px;border-radius:20px;text-transform:uppercase;
                     letter-spacing:0.06em;">{label}</span>
    </div>
    {flag_block}
</div>"""


def composite_score_html(score: float, label: str, sizing: float, run_str: str) -> str:
    color = GREEN if score >= 70 else (AMBER if score >= 40 else RED)
    sizing_pct = int(sizing * 100)
    return f"""
<div style="background:{CARD};border:1px solid {BORDER};border-top:4px solid {color};
            border-radius:{RADIUS_LG};padding:{SP_8} {SP_9};text-align:center;margin-bottom:{SP_2};">
    <div style="color:{TEXT_DIM};font-size:{FS_SM};text-transform:uppercase;
                letter-spacing:0.1em;margin-bottom:{SP_4};">COMPOSITE GATE SCORE</div>
    <div style="color:{TEXT};font-family:'DM Mono','IBM Plex Mono',monospace;
                font-size:{FS_5XL};font-weight:700;line-height:1;">{score:.0f}</div>
    <div style="color:{TEXT_DIM};font-size:{FS_XL};margin-top:2px;">/ 100</div>
    <div style="margin-top:{SP_4};">
        <span style="background:{color}22;color:{color};font-size:{FS_MD};font-weight:600;
                     padding:7px 22px;border-radius:20px;text-transform:uppercase;
                     letter-spacing:0.06em;">{label}</span>
    </div>
    <div style="margin-top:{SP_4};color:{TEXT_MUTED};font-size:{FS_SM};">
        Deploy <strong style="color:{TEXT}">{sizing_pct}%</strong> of position budget
        &nbsp;·&nbsp; Last run: <strong style="color:{TEXT}">{run_str}</strong>
    </div>
</div>"""


def section_header_html(title: str, subtitle: str = "") -> str:
    sub = (
        f'<div style="color:{TEXT_DIM};font-size:{FS_SM};margin-top:{SP_1};">{subtitle}</div>'
        if subtitle else ""
    )
    return f"""
<div style="margin:{SP_6} 0 {SP_4};">
    <div style="color:{TEXT};font-size:{FS_XL};font-weight:600;
                font-family:\'IBM Plex Sans\',system-ui,sans-serif;">{title}</div>
    {sub}
</div>"""


def ticker_hero_html(symbol: str, price: str, badge_label: str, badge_color: str, sub_label: str = "") -> str:
    """Oversized ticker header (TradingAgents-style). badge_color is a hex color string."""
    sub = (
        f'<div style="color:{TEXT_DIM};font-size:{FS_SM};margin-top:{SP_1};'
        f'font-family:\'DM Mono\',\'IBM Plex Mono\',monospace;">{sub_label}</div>'
    ) if sub_label else ""
    return f"""
<div style="background:{CARD};border:1px solid {BORDER};border-top:4px solid {badge_color};
            border-radius:{RADIUS_LG};padding:{SP_6} {SP_8};margin-bottom:{SP_5};">
  <div style="display:flex;align-items:flex-start;justify-content:space-between;">
    <div>
      <div style="color:{TEXT_DIM};font-size:{FS_2XS};text-transform:uppercase;
                  letter-spacing:0.1em;margin-bottom:{SP_1};">TOP PICK</div>
      <div style="color:{TEXT};font-family:\'DM Mono\',\'IBM Plex Mono\',monospace;
                  font-size:{FS_4XL};font-weight:800;letter-spacing:-1px;line-height:1;">{symbol}</div>
      {sub}
    </div>
    <div style="text-align:right;">
      <div style="color:{TEXT};font-family:\'DM Mono\',\'IBM Plex Mono\',monospace;
                  font-size:{FS_3XL};font-weight:700;line-height:1;">{price}</div>
      <span style="display:inline-block;background:{badge_color}1f;border:1px solid {badge_color}59;
                   color:{badge_color};font-size:{FS_SM};font-weight:700;padding:4px 14px;
                   border-radius:999px;margin-top:{SP_2};letter-spacing:0.06em;">● {badge_label}</span>
    </div>
  </div>
</div>"""


def zone_kpi_grid_html(stop: float, support: float, entry: float, target: float, current_price: float, entry_range: tuple | None = None) -> str:
    """4-card KPI grid for entry zone levels with % delta from current price.
    entry_range=(lo, hi) shows the full zone band instead of the midpoint."""
    def _pct(level: float) -> str:
        if current_price and current_price > 0:
            d = (level - current_price) / current_price * 100
            sign = "+" if d >= 0 else ""
            return f"{sign}{d:.1f}%"
        return "—"

    def _card(label: str, value: float, color: str, value_str: str | None = None) -> str:
        display_val = value_str if value_str else f"${value:,.2f}"
        font_size = FS_LG if value_str else "1.2rem"
        return (
            f'<div style="background:{CARD};border:1px solid {BORDER};border-top:2px solid {color};'
            f'border-radius:{RADIUS};padding:{SP_4} {SP_4};text-align:center;">'
            f'<div style="color:{TEXT_DIM};font-size:{FS_2XS};text-transform:uppercase;'
            f'letter-spacing:0.09em;margin-bottom:{SP_1};">{label}</div>'
            f'<div style="color:{TEXT};font-family:\'DM Mono\',\'IBM Plex Mono\',monospace;'
            f'font-size:{font_size};font-weight:600;white-space:nowrap;">{display_val}</div>'
            f'<div style="color:{color};font-size:{FS_SM};margin-top:{SP_1};font-weight:500;">{_pct(value)}</div>'
            f'</div>'
        )

    entry_str = None
    if entry_range:
        lo, hi = entry_range
        entry_str = f"${lo:,.2f} – ${hi:,.2f}"

    cards = (
        _card("STOP", stop, RED)
        + _card("SUPPORT", support, AMBER)
        + _card("ENTRY", entry, ACCENT, entry_str)
        + _card("TARGET", target, BLUE)
    )
    return (
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));'
        f'gap:{SP_2};margin-bottom:{SP_4};">{cards}</div>'
    )


def bull_bear_split_html(bull_items: list, bear_items: list) -> str:
    """Two-column tinted card: green bull case + red bear case."""
    def _rows(items: list, prefix: str, color: str) -> str:
        if not items:
            return f'<div style="color:{TEXT_DIM};font-size:{FS_SM};">—</div>'
        return "".join(
            f'<div style="color:{TEXT_MUTED};font-size:{FS_SM};line-height:1.55;margin-bottom:{SP_1};">'
            f'<span style="color:{color};font-weight:600;">{prefix} </span>{item}</div>'
            for item in items
        )

    return f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:{SP_3};margin-bottom:{SP_4};">
  <div style="background:rgba(34,197,94,0.06);border:1px solid rgba(34,197,94,0.20);
              border-radius:{RADIUS};padding:{SP_4} {SP_4};">
    <div style="color:{GREEN};font-size:{FS_2XS};font-weight:700;text-transform:uppercase;
                letter-spacing:0.09em;margin-bottom:{SP_2};">BULL CASE</div>
    {_rows(bull_items, '+', GREEN)}
  </div>
  <div style="background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.20);
              border-radius:{RADIUS};padding:{SP_4} {SP_4};">
    <div style="color:{RED};font-size:{FS_2XS};font-weight:700;text-transform:uppercase;
                letter-spacing:0.09em;margin-bottom:{SP_2};">BEAR CASE</div>
    {_rows(bear_items, '−', RED)}
  </div>
</div>"""


def risk_row_html(severity: str, title: str, description: str) -> str:
    """Single risk row with severity dot. severity ∈ {'high','med','low'}."""
    dot_color = {"high": RED, "med": AMBER, "low": BLUE}.get(severity.lower(), TEXT_DIM)
    return (
        f'<div style="display:flex;gap:{SP_3};align-items:flex-start;padding:{SP_2} {SP_4};'
        f'background:{CARD};border:1px solid {BORDER};border-radius:{RADIUS_SM};margin-bottom:{SP_1};">'
        f'<div style="min-width:58px;display:flex;align-items:center;gap:{SP_1};padding-top:2px;">'
        f'<div style="width:7px;height:7px;border-radius:50%;background:{dot_color};flex-shrink:0;"></div>'
        f'<span style="color:{dot_color};font-size:{FS_2XS};font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.08em;">{severity.upper()}</span>'
        f'</div>'
        f'<div>'
        f'<div style="color:{TEXT};font-size:{FS_SM};font-weight:600;margin-bottom:2px;">{title}</div>'
        f'<div style="color:{TEXT_MUTED};font-size:{FS_SM};line-height:1.5;">{description}</div>'
        f'</div>'
        f'</div>'
    )


# ── Global CSS ─────────────────────────────────────────────────────────────────
_CSS = f"""
<link href="https://fonts.googleapis.com/icon?family=Material+Icons+Sharp" rel="stylesheet">

<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap');

/* ── Page & sidebar backgrounds ───────────────────────────── */
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main,
[data-testid="stMainBlockContainer"] {{
    background: {BG} !important;
}}
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child {{
    background: {SIDEBAR_BG} !important;
    border-right: 1px solid {BORDER};
}}
[data-testid="stHeader"] {{
    background: {BG} !important;
    border-bottom: 1px solid {BORDER};
}}
[data-testid="stBottom"] {{
    background: {BG} !important;
    border-top: 1px solid {BORDER};
}}

/* Typography: NO wildcard font override — it breaks Material Icons
   (icon names render as raw text instead of symbols).
   Target specific containers only. */
body,
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
.stApp p, .stApp label, .stApp span:not([class*="material"]):not([data-testid="stIconMaterial"]) {{
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
}}

/* Restore Material Icons for Streamlit's icon elements (Emotion classes don't contain "material") */
[data-testid="stIconMaterial"] {{
    font-family: 'Material Icons', 'Material Icons Sharp' !important;
    font-feature-settings: 'liga' !important;
    -webkit-font-feature-settings: 'liga' !important;
    overflow: hidden;
}}

/* Headings — only inside markdown, not Streamlit UI chrome */
[data-testid="stMarkdownContainer"] h1,
[data-testid="stHeadingWithActionElements"] h1 {{
    color: {TEXT} !important;
    font-weight: 600;
    letter-spacing: -0.02em;
}}
[data-testid="stMarkdownContainer"] h2,
[data-testid="stHeadingWithActionElements"] h2 {{
    color: {TEXT} !important;
    font-weight: 600;
    letter-spacing: -0.01em;
}}
[data-testid="stMarkdownContainer"] h3 {{
    color: {TEXT} !important;
    font-weight: 600;
}}

/* Material Icons — preserve icon font, never override */
.material-icons,
.material-icons-sharp,
.material-icons-outlined,
.material-symbols-rounded,
[class*="material-icons"],
[class*="material-symbols"] {{
    font-family: 'Material Icons Sharp', 'Material Icons' !important;
    font-size: 20px !important;
    line-height: 1 !important;
    font-feature-settings: 'liga' !important;
    -webkit-font-feature-settings: 'liga' !important;
    display: inline-block;
    overflow: hidden;
}}

p, .stMarkdown p {{ color: {TEXT_MUTED}; line-height: 1.6; }}
[data-testid="stCaptionContainer"], .stCaption, small {{
    color: {TEXT_DIM} !important;
    font-size: {FS_SM} !important;
}}

/* ── Sidebar text & nav links ───────────────────────────── */
[data-testid="stSidebar"] * {{ color: {TEXT_MUTED}; }}
[data-testid="stSidebarNavLink"] {{
    border-radius: {RADIUS_SM};
    padding: 6px 12px;
    font-size: {FS_BASE};
    transition: background {TRANS};
    color: {TEXT_DIM};
}}
[data-testid="stSidebarNavLink"]:hover {{
    background: {CARD};
    color: {TEXT};
}}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: {CARD};
    color: {TEXT};
    border-left: 2px solid {ACCENT};
}}

/* ── Metric cards ────────────────────────────────────────── */
[data-testid="stMetric"] {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
    padding: {SP_4} {SP_5};
}}
[data-testid="stMetricValue"] {{
    color: {TEXT} !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 1.5rem !important;
    font-weight: 600 !important;
}}
[data-testid="stMetricLabel"] > div {{
    color: {TEXT_DIM} !important;
    font-size: {FS_XS} !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}}
[data-testid="stMetricDelta"] {{
    font-size: {FS_SM} !important;
}}

/* ── Buttons ──────────────────────────────────────────────── */
.stButton > button {{
    background: {CARD2};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
    font-weight: 500;
    transition: background {TRANS}, border-color {TRANS};
    font-size: {FS_MD};
}}
.stButton > button:hover {{
    background: {BORDER};
    border-color: {ACCENT};
    color: {TEXT};
}}
.stButton > button[kind="primary"] {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #fff;
}}
.stButton > button[kind="primary"]:hover {{
    background: #5254e0;
    border-color: #5254e0;
}}

/* ── Forms ───────────────────────────────────────────────── */
[data-testid="stForm"] {{
    background: {CARD};
    border: 1px solid {BORDER} !important;
    border-radius: {RADIUS};
    padding: {SP_5};
}}
.stTextInput input,
.stNumberInput input,
.stTextArea textarea {{
    background: {CARD2} !important;
    color: {TEXT} !important;
    border-color: {BORDER} !important;
    border-radius: {RADIUS_SM} !important;
    font-family: 'IBM Plex Sans', system-ui, sans-serif !important;
}}
.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus {{
    border-color: {ACCENT} !important;
    box-shadow: 0 0 0 2px rgba(99,102,241,0.2) !important;
}}
.stSelectbox > div > div {{
    background: {CARD2} !important;
    color: {TEXT} !important;
    border-color: {BORDER} !important;
    border-radius: {RADIUS_SM} !important;
}}
.stSelectbox svg {{ fill: {TEXT_DIM}; }}

/* ── Tabs — scoped to stTabs to avoid stomping on dropdowns ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    background: {CARD};
    border-bottom: 1px solid {BORDER};
    border-radius: {RADIUS} {RADIUS} 0 0;
    gap: 2px;
    padding: 6px 8px 0;
    overflow-x: auto;
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
    background: transparent !important;
    color: {TEXT_DIM} !important;
    border-radius: {RADIUS_SM} {RADIUS_SM} 0 0 !important;
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
    font-size: {FS_BASE};
    font-weight: 500;
    white-space: nowrap;
    flex-shrink: 0;
}}
[data-testid="stTabs"] [aria-selected="true"][data-baseweb="tab"] {{
    background: {CARD2} !important;
    color: {TEXT} !important;
    border-bottom: 2px solid {ACCENT} !important;
}}

/* ── Expanders ───────────────────────────────────────────── */
[data-testid="stExpander"] {{
    background: {CARD};
    border: 1px solid {BORDER} !important;
    border-radius: {RADIUS} !important;
    overflow: hidden;
}}
[data-testid="stExpander"] summary {{
    color: {TEXT_MUTED} !important;
    font-weight: 500;
    font-size: {FS_BASE};
    padding: {SP_2} {SP_4};
}}

@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
    }}
}}
</style>"""

# Part 2 — injected separately to stay under Streamlit 1.57's markdown HTML-block limit.
_CSS2 = f"""<style>
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: {RADIUS}; overflow: hidden; }}
[data-testid="stAlert"] {{ border-radius: {RADIUS} !important; }}
hr {{ border-color: {BORDER} !important; opacity: 1; }}
[data-baseweb="popover"] [data-baseweb="menu"] {{ background: {CARD2} !important; border: 1px solid {BORDER} !important; border-radius: {RADIUS_SM} !important; }}
[data-baseweb="menu"] li {{ color: {TEXT_MUTED} !important; }}
[data-baseweb="menu"] li:hover {{ background: {BORDER} !important; color: {TEXT} !important; }}
::-webkit-scrollbar {{ width: 5px; height: 5px; }}
::-webkit-scrollbar-track {{ background: {CARD}; }}
::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: {CARD2}; }}
[data-testid="stPageLink"] a {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: {RADIUS_SM}; color: {TEXT_MUTED}; padding: {SP_2} {SP_4}; display: block; text-decoration: none; font-size: {FS_BASE}; transition: border-color {TRANS}, color {TRANS}; }}
[data-testid="stPageLink"] a:hover {{ border-color: {ACCENT}; color: {TEXT}; }}
</style>
"""


# Part 3 — analyst chat bubble styles (used in st.dialog, not sidebar).
_CSS3 = f"""<style>
.sl-chat-msg {{
    color: {TEXT} !important;
    font-size: {FS_MD};
    line-height: 1.55;
    margin-bottom: 2px;
    word-wrap: break-word;
    white-space: pre-wrap;
}}
.sl-chat-meta {{
    color: {TEXT_DIM} !important;
    font-size: {FS_XS};
    margin-bottom: {SP_2};
    line-height: 1.4;
}}
.sl-chat-bubble {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM};
    padding: {SP_2} {SP_2};
    margin-bottom: 2px;
}}
.sl-chat-bubble-user {{
    background: {CARD2};
    border-color: {ACCENT}44;
}}
</style>
"""


# Part 4 — floating chat button + sidebar section labels + header bar.
_CSS4 = f"""<style>
/* ── Floating analyst chat button ───────────────────────────── */
/* Targets st.button(help="Open Analyst Chat") wrapper so it floats */
div[data-testid="stButton"]:has(button[title="Open Analyst Chat"]) {{
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 9999;
}}
div[data-testid="stButton"]:has(button[title="Open Analyst Chat"]) button {{
    width: 56px !important;
    height: 56px !important;
    border-radius: 50% !important;
    background: linear-gradient(135deg, {PURPLE}, #22c1ff) !important;
    border: none !important;
    color: #fff !important;
    font-size: 1.4rem !important;
    padding: 0 !important;
    box-shadow: 0 8px 24px rgba(124,106,247,.45);
    transition: transform {TRANS}, box-shadow {TRANS};
}}
div[data-testid="stButton"]:has(button[title="Open Analyst Chat"]) button:hover {{
    transform: scale(1.07);
    box-shadow: 0 12px 32px rgba(124,106,247,.6);
}}
/* ── Sidebar section eyebrow labels via CSS :before ────────── */
/* Home = first nav item → WORKSPACE label */
[data-testid="stSidebarNavItems"] > li:first-child::before {{
    content: "WORKSPACE";
    display: block;
    color: {TEXT_DIM};
    font-size: {FS_2XS};
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.10em;
    padding: {SP_4} {SP_4} {SP_1};
    line-height: 1;
}}
/* Second item (first page) → BROWSE label */
[data-testid="stSidebarNavItems"] > li:nth-child(2)::before {{
    content: "BROWSE";
    display: block;
    color: {TEXT_DIM};
    font-size: {FS_2XS};
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.10em;
    padding: {SP_4} {SP_4} {SP_1};
    line-height: 1;
}}
/* ── Header topbar pill + ⌘K button ─────────────────────────── */
.sl-topbar-pill {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XS};
    padding: {SP_1} {SP_2};
    color: {TEXT_DIM};
    font-size: {FS_SM};
    font-family: 'DM Mono', 'IBM Plex Mono', monospace;
}}
div[data-testid="stButton"]:has(button[title="Swing Lab page guide"]) button {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    color: {TEXT_DIM} !important;
    font-size: {FS_SM} !important;
    border-radius: {RADIUS_XS} !important;
    font-family: 'IBM Plex Sans', system-ui, sans-serif !important;
    padding: 5px 10px !important;
}}
div[data-testid="stButton"]:has(button[title="Swing Lab page guide"]) button:hover {{
    border-color: {ACCENT} !important;
    color: {TEXT_MUTED} !important;
    background: {CARD2} !important;
}}
</style>
"""


@st.dialog("Find on Swing Lab", width="small")
def _topbar_help_dialog() -> None:
    st.markdown(f"""
<div style="font-size:{FS_MD};line-height:1.8;color:{TEXT_MUTED};">
<strong style="color:{TEXT};">Pages</strong><br>
· <strong>Gate</strong> — 6-signal macro score (VIX, SPY trend, HYG, yield curve, breadth, VIX term)<br>
· <strong>Scanner</strong> — top-20 momentum picks ranked within sector<br>
· <strong>Review</strong> — per-symbol Claude fundamental analysis<br>
· <strong>Recommendation</strong> — synthesized top-3 picks with entry zones<br>
· <strong>Trade Log</strong> — open/close positions with thesis and exit notes<br>
· <strong>Postmortem</strong> — Claude pattern analysis across closed trades<br>
<br><strong style="color:{TEXT};">CLI commands</strong><br>
<code>uv run swing-lab gate · scan · review · log · rebalance</code>
</div>""", unsafe_allow_html=True)


def render_topbar(run_label: str = "") -> None:
    """Render the header bar with optional run-timestamp pill and ⌘K help button."""
    c_left, c_right = st.columns([5, 1])
    if run_label:
        c_left.markdown(
            f'<div style="padding-top:4px;">'
            f'<span class="sl-topbar-pill">{run_label}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c_right:
        if st.button("🔎 ⌘K", key="sl_topbar_search_btn",
                     help="Swing Lab page guide", use_container_width=True):
            _topbar_help_dialog()
    st.markdown(
        f'<hr style="border:none;border-top:1px solid {BORDER};margin:4px 0 18px;">',
        unsafe_allow_html=True,
    )


def inject() -> None:
    """Inject the Warm Graphite CSS theme. Call once per page after set_page_config()."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(_CSS2, unsafe_allow_html=True)
    st.markdown(_CSS3, unsafe_allow_html=True)
    st.markdown(_CSS4, unsafe_allow_html=True)
