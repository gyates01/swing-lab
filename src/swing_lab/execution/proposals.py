"""Build the pending order queue: opens from latest recs, closes from scan dropout."""
from swing_lab import config
from swing_lab.db import load_latest_recommendations, load_latest_scan_picks
from swing_lab.execution import guardrails, orders
from swing_lab.execution.paper_account import (
    account_state_for_guardrails,
    paper_account_state,
)
from swing_lab.execution.quotes import get_quote

_MIN_NOTIONAL = 1.0  # RH fractional-share minimum


def generate_proposals(conn, quote_fn=get_quote) -> dict:
    """Return {created: [order dicts], warnings: [str]}. Idempotent via dedup."""
    warnings: list[str] = []
    orders.expire_stale(conn)

    recs = load_latest_recommendations(conn)
    picks = load_latest_scan_picks(conn)
    if not recs:
        warnings.append("no saved recommendations today — run `swing-lab recommend` first")

    account = paper_account_state(conn, quote_fn=quote_fn)
    guard_state = account_state_for_guardrails(conn, quote_fn=quote_fn)
    held = account["open_symbols"]
    pending_buys = orders.pending_symbols(conn, side="buy")
    pending_sells = orders.pending_symbols(conn, side="sell")

    created = []

    # Opens — from the latest rec batch
    for rec in recs:
        symbol = rec["symbol"]
        if symbol in held or symbol in pending_buys:
            continue
        quote = quote_fn(symbol)
        if quote is None:
            warnings.append(f"{symbol}: no quote, skipped open")
            continue
        shares = round(rec["sizing_pct"] * account["equity"] / quote, 6)
        notional = shares * quote
        if notional < _MIN_NOTIONAL:
            warnings.append(f"{symbol}: below ${_MIN_NOTIONAL:.0f} minimum, skipped")
            continue
        proposal = {
            "mode": config.EXECUTION_MODE, "side": "buy", "symbol": symbol,
            "shares": shares, "est_price": quote, "est_notional": notional,
            "reason": "open_rec", "rec_id": rec["rec_id"], "trade_id": None,
        }
        oid = orders.create_order(conn, proposal,
                                  guardrail=guardrails.check(proposal, guard_state))
        created.append(orders.get_order(conn, oid))

    # Closes — open positions that dropped out of the scan top-picks
    top_symbols = {p["symbol"] for p in picks[:config.TOP_N_PICKS]}
    for pos in account["open_positions"]:
        symbol = pos["symbol"]
        if symbol in top_symbols or symbol in pending_sells:
            continue
        quote = quote_fn(symbol)
        if quote is None:
            warnings.append(f"{symbol}: no quote, skipped close")
            continue
        notional = pos["shares"] * quote
        proposal = {
            "mode": config.EXECUTION_MODE, "side": "sell", "symbol": symbol,
            "shares": pos["shares"], "est_price": quote, "est_notional": notional,
            "reason": "rebalance_close", "rec_id": None, "trade_id": pos["trade_id"],
        }
        oid = orders.create_order(conn, proposal,
                                  guardrail=guardrails.check(proposal, guard_state))
        created.append(orders.get_order(conn, oid))

    return {"created": created, "warnings": warnings}
