"""Page 7 — Paper Execution: review/approve/reject/execute the order queue."""
from datetime import datetime, timezone

import streamlit as st

from swing_lab.dashboard import sidebar_chat
from swing_lab.dashboard.charts import candle_chart
from swing_lab.dashboard.theme import inject, render_topbar, zone_kpi_grid_html
from swing_lab.db import init_db, load_recommendation
from swing_lab.execution import guardrails, orders
from swing_lab.execution.executor import execute_approved
from swing_lab.execution.paper_account import (
    account_state_for_guardrails,
    paper_account_state,
)
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
# Re-evaluate guardrails against *current* state; flags stored at create-time can be
# stale (e.g. an after-hours proposal still tagged "outside regular trading hours").
guard_state = account_state_for_guardrails(conn) if pending else None
for o in pending:
    flags = guardrails.check(o, guard_state)
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
    if o["side"] == "buy":
        rec = load_recommendation(conn, o["rec_id"]) if o["rec_id"] is not None else None
        has_levels = bool(rec and rec.get("entry_low") is not None
                          and rec.get("stop_price") is not None)
        if has_levels:
            entry_mid = (rec["entry_low"] + rec["entry_high"]) / 2
            st.markdown(
                zone_kpi_grid_html(rec["stop_price"], rec["support"], entry_mid,
                                   rec["target"], o["est_price"],
                                   entry_range=(rec["entry_low"], rec["entry_high"])),
                unsafe_allow_html=True,
            )
        with st.expander(f"{o['symbol']} chart"):
            chart = candle_chart(
                o["symbol"], price=o["est_price"], period="3mo", height=320,
                trade_entry_price=o["est_price"],
                entry_low=rec["entry_low"] if has_levels else None,
                entry_high=rec["entry_high"] if has_levels else None,
                support=rec["support"] if has_levels else None,
                stop=rec["stop_price"] if has_levels else None,
                target=rec["target"] if has_levels else None,
            )
            if chart:
                st.plotly_chart(chart, use_container_width=True)

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
