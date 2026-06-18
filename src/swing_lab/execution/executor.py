"""Execute approved orders: re-check guardrails, fill at current quote, write paper trades.

The fill model (current market quote) is the only thing Phase 3 swaps for live fills.
"""
from datetime import datetime, timezone

from swing_lab.execution import guardrails, orders
from swing_lab.execution.paper_account import account_state_for_guardrails
from swing_lab.execution.quotes import get_quote
from swing_lab.tradelog import close_trade, open_trade


def _proposal_from_order(o: dict) -> dict:
    return {
        "mode": o["mode"], "side": o["side"], "symbol": o["symbol"],
        "shares": o["shares"], "est_price": o["est_price"],
        "est_notional": o["est_notional"], "reason": o["reason"],
        "rec_id": o["rec_id"], "trade_id": o["trade_id"],
        "entry_high": o.get("entry_high"),
    }


def execute_approved(conn, quote_fn=get_quote) -> dict:
    """Fill all approved orders. Return {filled, rejected, skipped} order-id lists."""
    filled, rejected, skipped = [], [], []
    for o in orders.list_orders(conn, status="approved"):
        oid = o["order_id"]
        proposal = _proposal_from_order(o)

        # Re-check against fresh state — state may have changed since approval
        state = account_state_for_guardrails(conn, quote_fn=quote_fn)
        violations = guardrails.check(proposal, state)
        if violations:
            orders.set_status(conn, oid, "rejected",
                              decided_at=datetime.now(timezone.utc).isoformat(),
                              notes="; ".join(violations))
            rejected.append(oid)
            continue

        quote = quote_fn(o["symbol"])
        if quote is None:
            orders.set_status(conn, oid, "approved", notes="no quote at execute")
            skipped.append(oid)
            continue

        filled_at = datetime.now(timezone.utc).isoformat()
        if o["side"] == "buy":
            trade_id = open_trade(conn, o["symbol"], o["shares"], quote,
                                  rec_id=o["rec_id"], mode="paper")
            orders.set_status(conn, oid, "filled", filled_at=filled_at,
                              fill_price=quote, trade_id=trade_id)
        else:
            close_trade(conn, o["trade_id"], quote, exit_reason="rebalance")
            orders.set_status(conn, oid, "filled", filled_at=filled_at, fill_price=quote)
        filled.append(oid)

    return {"filled": filled, "rejected": rejected, "skipped": skipped}
