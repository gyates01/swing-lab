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
TEXT_DIM    = "#7a7e96"
ACCENT      = "#6366f1"   # indigo
GREEN       = "#22c55e"
RED         = "#ef4444"
AMBER       = "#f59e0b"
BLUE        = "#3b82f6"
PURPLE      = "#7c6af7"

CHART_COLORS = [ACCENT, GREEN, AMBER, RED, BLUE, PURPLE, "#0ea5e9", "#f43f5e"]

# ── Plotly base layout ─────────────────────────────────────────────────────────
_PLOTLY_LAYOUT = dict(
    paper_bgcolor=CARD,
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
    margin=dict(l=48, r=32, t=44, b=40),
    hoverlabel=dict(
        bgcolor=CARD2,
        bordercolor=BORDER,
        font=dict(color=TEXT, size=12),
    ),
    title=dict(
        font=dict(color=TEXT_MUTED, size=13, family="'IBM Plex Sans', system-ui, sans-serif"),
        x=0,
        pad=dict(l=0),
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
        f'<div style="color:{TEXT_DIM};font-size:0.73rem;margin-top:5px;">{sub}</div>'
        if sub else ""
    )
    return f"""
<div style="background:{CARD};border:1px solid {BORDER};border-top:2px solid {accent_color};
            border-radius:10px;padding:18px 22px;">
    <div style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;
                letter-spacing:0.09em;margin-bottom:8px;">{label}</div>
    <div style="color:{TEXT};font-family:'DM Mono','IBM Plex Mono',monospace;
                font-size:1.6rem;font-weight:600;line-height:1.1;">{value}</div>
    {sub_block}
</div>"""


def score_card_html(name: str, val: float, flag_note: str = "") -> str:
    color = GREEN if val >= 70 else (AMBER if val >= 40 else RED)
    label = "Healthy" if val >= 70 else ("Caution" if val >= 40 else "Warning")
    flag_block = (
        f'<div style="color:{RED};font-size:0.7rem;margin-top:8px;line-height:1.35;">'
        f'[!] {flag_note}</div>'
    ) if flag_note and val < 20 else ""
    return f"""
<div style="background:{CARD};border:1px solid {BORDER};border-top:3px solid {color};
            border-radius:10px;padding:18px 20px;height:100%;box-sizing:border-box;">
    <div style="color:{TEXT_DIM};font-size:0.68rem;text-transform:uppercase;
                letter-spacing:0.08em;margin-bottom:10px;">{name}</div>
    <div style="color:{TEXT};font-family:'DM Mono','IBM Plex Mono',monospace;
                font-size:2rem;font-weight:700;line-height:1;">
        {val:.0f}<span style="color:{TEXT_DIM};font-size:1rem;font-weight:400;">/100</span>
    </div>
    <div style="margin-top:10px;">
        <span style="background:{color}22;color:{color};font-size:0.7rem;font-weight:600;
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
            border-radius:14px;padding:28px 36px;text-align:center;margin-bottom:8px;">
    <div style="color:{TEXT_DIM};font-size:0.72rem;text-transform:uppercase;
                letter-spacing:0.1em;margin-bottom:14px;">COMPOSITE GATE SCORE</div>
    <div style="color:{TEXT};font-family:'DM Mono','IBM Plex Mono',monospace;
                font-size:4.5rem;font-weight:700;line-height:1;">{score:.0f}</div>
    <div style="color:{TEXT_DIM};font-size:1rem;margin-top:2px;">/ 100</div>
    <div style="margin-top:16px;">
        <span style="background:{color}22;color:{color};font-size:0.875rem;font-weight:600;
                     padding:7px 22px;border-radius:20px;text-transform:uppercase;
                     letter-spacing:0.06em;">{label}</span>
    </div>
    <div style="margin-top:14px;color:{TEXT_MUTED};font-size:0.82rem;">
        Deploy <strong style="color:{TEXT}">{sizing_pct}%</strong> of position budget
        &nbsp;·&nbsp; Last run: <strong style="color:{TEXT}">{run_str}</strong>
    </div>
</div>"""


def section_header_html(title: str, subtitle: str = "") -> str:
    sub = (
        f'<div style="color:{TEXT_DIM};font-size:0.82rem;margin-top:4px;">{subtitle}</div>'
        if subtitle else ""
    )
    return f"""
<div style="margin:24px 0 14px;">
    <div style="color:{TEXT};font-size:1.05rem;font-weight:600;
                font-family:\'IBM Plex Sans\',system-ui,sans-serif;">{title}</div>
    {sub}
</div>"""


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
    font-size: 0.78rem !important;
}}

/* ── Sidebar text & nav links ───────────────────────────── */
[data-testid="stSidebar"] * {{ color: {TEXT_MUTED}; }}
[data-testid="stSidebarNavLink"] {{
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 0.875rem;
    transition: background 0.15s;
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
    border-radius: 10px;
    padding: 16px 20px;
}}
[data-testid="stMetricValue"] {{
    color: {TEXT} !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 1.5rem !important;
    font-weight: 600 !important;
}}
[data-testid="stMetricLabel"] > div {{
    color: {TEXT_DIM} !important;
    font-size: 0.7rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}}
[data-testid="stMetricDelta"] {{
    font-size: 0.78rem !important;
}}

/* ── Buttons ──────────────────────────────────────────────── */
.stButton > button {{
    background: {CARD2};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
    font-weight: 500;
    transition: background 0.15s, border-color 0.15s;
    font-size: 0.85rem;
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
    background: #4f52d9;
    border-color: #4f52d9;
}}

/* ── Forms ───────────────────────────────────────────────── */
[data-testid="stForm"] {{
    background: {CARD};
    border: 1px solid {BORDER} !important;
    border-radius: 12px;
    padding: 20px;
}}
.stTextInput input,
.stNumberInput input,
.stTextArea textarea {{
    background: {CARD2} !important;
    color: {TEXT} !important;
    border-color: {BORDER} !important;
    border-radius: 8px !important;
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
    border-radius: 8px !important;
}}
.stSelectbox svg {{ fill: {TEXT_DIM}; }}

/* ── Tabs — scoped to stTabs to avoid stomping on dropdowns ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    background: {CARD};
    border-bottom: 1px solid {BORDER};
    border-radius: 10px 10px 0 0;
    gap: 2px;
    padding: 6px 8px 0;
    overflow-x: auto;
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
    background: transparent !important;
    color: {TEXT_DIM} !important;
    border-radius: 8px 8px 0 0 !important;
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
    font-size: 0.875rem;
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
    border-radius: 10px !important;
    overflow: hidden;
}}
[data-testid="stExpander"] summary {{
    color: {TEXT_MUTED} !important;
    font-weight: 500;
    font-size: 0.875rem;
    padding: 10px 14px;
}}
</style>"""

# Part 2 — injected separately to stay under Streamlit 1.57's markdown HTML-block limit.
_CSS2 = f"""<style>
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 10px; overflow: hidden; }}
[data-testid="stAlert"] {{ border-radius: 10px !important; }}
hr {{ border-color: {BORDER} !important; opacity: 1; }}
[data-baseweb="popover"] [data-baseweb="menu"] {{ background: {CARD2} !important; border: 1px solid {BORDER} !important; border-radius: 8px !important; }}
[data-baseweb="menu"] li {{ color: {TEXT_MUTED} !important; }}
[data-baseweb="menu"] li:hover {{ background: {BORDER} !important; color: {TEXT} !important; }}
::-webkit-scrollbar {{ width: 5px; height: 5px; }}
::-webkit-scrollbar-track {{ background: {CARD}; }}
::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: #363940; }}
[data-testid="stPageLink"] a {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; color: {TEXT_MUTED}; padding: 10px 16px; display: block; text-decoration: none; font-size: 0.875rem; transition: border-color 0.15s, color 0.15s; }}
[data-testid="stPageLink"] a:hover {{ border-color: {ACCENT}; color: {TEXT}; }}
</style>
"""


# Part 3 — sidebar chat widget overrides (separate chunk; do not merge into _CSS or _CSS2).
_CSS3 = f"""<style>
/* ── Analyst sidebar chat: override [data-testid="stSidebar"] * wildcard ── */
[data-testid="stSidebar"] .sl-chat-msg {{
    color: {TEXT} !important;
    font-size: 0.855rem;
    line-height: 1.55;
    margin-bottom: 2px;
    word-wrap: break-word;
    white-space: pre-wrap;
}}
[data-testid="stSidebar"] .sl-chat-meta {{
    color: {TEXT_DIM} !important;
    font-size: 0.68rem;
    margin-bottom: 10px;
    line-height: 1.4;
}}
[data-testid="stSidebar"] .sl-chat-bubble {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    margin-bottom: 2px;
}}
[data-testid="stSidebar"] .sl-chat-bubble-user {{
    background: {CARD2};
    border-color: {ACCENT}44;
}}
</style>
"""


def inject() -> None:
    """Inject the Warm Graphite CSS theme. Call once per page after set_page_config()."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(_CSS2, unsafe_allow_html=True)
    st.markdown(_CSS3, unsafe_allow_html=True)
