"""Derive the paper portfolio from `trades` where mode='paper'. No separate table."""
from swing_lab.config import PAPER_STARTING_CASH
from swing_lab.execution.quotes import get_quote


def _open_paper_trades(conn) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM trades WHERE mode = 'paper' AND exit_price IS NULL ORDER BY trade_id")
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _realized_pnl(conn) -> float:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(SUM(pnl), 0.0) FROM trades WHERE mode = 'paper' AND exit_price IS NOT NULL")
    return cursor.fetchone()[0]


def paper_account_state(conn, quote_fn=get_quote) -> dict:
    """{cash, equity, unrealized, open_positions, open_symbols}, marked to market."""
    opens = _open_paper_trades(conn)
    cost_basis = sum(t["shares"] * t["entry_price"] for t in opens)
    cash = PAPER_STARTING_CASH + _realized_pnl(conn) - cost_basis

    positions, market_value, unrealized = [], 0.0, 0.0
    for t in opens:
        quote = quote_fn(t["symbol"])
        mark = quote if quote is not None else t["entry_price"]
        value = t["shares"] * mark
        basis = t["shares"] * t["entry_price"]
        market_value += value
        unrealized += value - basis
        positions.append({
            "trade_id": t["trade_id"], "symbol": t["symbol"], "shares": t["shares"],
            "entry_price": t["entry_price"], "quote": quote,
            "market_value": value, "unrealized": value - basis,
            "opened_at": t["opened_at"],
        })

    return {
        "cash": cash,
        "equity": cash + market_value,
        "unrealized": unrealized,
        "open_positions": positions,
        "open_symbols": {p["symbol"] for p in positions},
    }


def account_state_for_guardrails(conn, quote_fn=get_quote) -> dict:
    """The slimmer state guardrails need, plus today's filled-order stats."""
    from swing_lab.execution import orders
    state = paper_account_state(conn, quote_fn=quote_fn)
    stats = orders.todays_stats(conn)
    return {
        "cash": state["cash"],
        "equity": state["equity"],
        "open_symbols": state["open_symbols"],
        "todays_order_count": stats["order_count"],
        "todays_notional": stats["notional"],
    }
