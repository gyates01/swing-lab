"""Page 7 — Paper Execution: review/approve/reject/execute the order queue."""
import json
from datetime import datetime, timezone

import streamlit as st

from swing_lab.dashboard import sidebar_chat
from swing_lab.dashboard.theme import inject, render_topbar
from swing_lab.db import init_db
from swing_lab.execution import orders
from swing_lab.execution.executor import execute_approved
from swing_lab.execution.paper_account import paper_account_state
from swing_lab.execution.proposals import generate_proposals

st.set_page_config(page_title="Execution — Swing Lab", layout="wide")
inject()
sidebar_chat.render()
render_topbar()

conn = init_db()

st.header("Paper Execution")

col_a, col_b = st.columns(2)
if col_a.button("Generate proposals", use_container_width=True):
    result = generate_proposals(conn)
    for w in result["warnings"]:
        st.warning(w)
    st.success(f"{len(result['created'])} new proposal(s) queued.")
if col_b.button("Execute approved", use_container_width=True):
    result = execute_approved(conn)
    st.success(f"Filled {len(result['filled'])}, rejected {len(result['rejected'])}, "
               f"skipped {len(result['skipped'])}.")

# --- Pending queue ---
st.subheader("Pending queue")
pending = orders.list_orders(conn, status="pending")
if not pending:
    st.caption("No pending orders. Click 'Generate proposals' to build the queue.")
for o in pending:
    flags = json.loads(o["guardrail_json"])
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    c1.write(f"**{o['side'].upper()} {o['symbol']}** — {o['shares']:.4f} sh "
             f"(~${o['est_notional']:.2f}) · {o['reason']}")
    if flags:
        c2.error("; ".join(flags))
    else:
        c2.success("guardrails ok")
    if c3.button("Approve", key=f"approve_{o['order_id']}", disabled=bool(flags)):
        orders.set_status(conn, o["order_id"], "approved",
                          decided_at=datetime.now(timezone.utc).isoformat())
        st.rerun()
    if c4.button("Reject", key=f"reject_{o['order_id']}"):
        orders.set_status(conn, o["order_id"], "rejected",
                          decided_at=datetime.now(timezone.utc).isoformat())
        st.rerun()

# --- Approved (awaiting execution) ---
approved = orders.list_orders(conn, status="approved")
if approved:
    st.subheader("Approved — awaiting execution")
    st.dataframe([{"id": o["order_id"], "side": o["side"], "symbol": o["symbol"],
                   "shares": o["shares"], "est_notional": o["est_notional"]} for o in approved],
                 use_container_width=True)

# --- Paper portfolio ---
st.subheader("Paper portfolio")
state = paper_account_state(conn)
m1, m2, m3 = st.columns(3)
m1.metric("Equity", f"${state['equity']:,.2f}")
m2.metric("Cash", f"${state['cash']:,.2f}")
m3.metric("Unrealized P&L", f"${state['unrealized']:,.2f}")
if state["open_positions"]:
    st.dataframe([{"symbol": p["symbol"], "shares": p["shares"],
                   "entry": p["entry_price"], "quote": p["quote"],
                   "market_value": p["market_value"], "unrealized": p["unrealized"]}
                  for p in state["open_positions"]], use_container_width=True)
else:
    st.caption("No open paper positions.")
