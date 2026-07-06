"""Pipeline — the research layers behind Recommendation, condensed into one page.

Macro Gate, Scanner, Claude Review, and Trade Log live here as tabs. They feed the
Recommendation engine; day-to-day you rarely need them individually.
"""
import streamlit as st

from swing_lab.dashboard import sidebar_chat
from swing_lab.dashboard.theme import inject, render_topbar
from swing_lab.dashboard.views import macro_gate, scanner, claude_review, trade_log

st.set_page_config(page_title="Pipeline — Swing Lab", layout="wide")
inject()
st.session_state["current_page"] = "pipeline"
sidebar_chat.render()
render_topbar()

tab_gate, tab_scan, tab_review, tab_log = st.tabs(
    ["Macro Gate", "Scanner", "Claude Review", "Trade Log"]
)
with tab_gate:
    macro_gate.render()
with tab_scan:
    scanner.render()
with tab_review:
    claude_review.render()
with tab_log:
    trade_log.render()
