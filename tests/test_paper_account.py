from swing_lab.config import PAPER_STARTING_CASH


def _open_paper(conn, symbol, shares, entry):
    from swing_lab.tradelog import open_trade
    return open_trade(conn, symbol, shares, entry, mode="paper")


def test_empty_account_is_starting_cash(db_conn):
    from swing_lab.execution.paper_account import paper_account_state
    state = paper_account_state(db_conn, quote_fn=lambda s: None)
    assert state["cash"] == PAPER_STARTING_CASH
    assert state["equity"] == PAPER_STARTING_CASH
    assert state["open_positions"] == []
    assert state["open_symbols"] == set()


def test_open_position_reduces_cash_and_marks_to_market(db_conn):
    from swing_lab.execution.paper_account import paper_account_state
    _open_paper(db_conn, "AAPL", 10.0, 100.0)  # $1000 cost basis
    state = paper_account_state(db_conn, quote_fn=lambda s: 120.0)
    assert state["cash"] == PAPER_STARTING_CASH - 1000.0
    assert state["equity"] == PAPER_STARTING_CASH - 1000.0 + 1200.0
    assert state["unrealized"] == 200.0
    assert state["open_symbols"] == {"AAPL"}


def test_quote_none_falls_back_to_entry_price(db_conn):
    from swing_lab.execution.paper_account import paper_account_state
    _open_paper(db_conn, "AAPL", 10.0, 100.0)
    state = paper_account_state(db_conn, quote_fn=lambda s: None)
    assert state["unrealized"] == 0.0
    assert state["equity"] == PAPER_STARTING_CASH


def test_realized_pnl_returns_to_cash(db_conn):
    from swing_lab.tradelog import open_trade, close_trade
    from swing_lab.execution.paper_account import paper_account_state
    tid = open_trade(db_conn, "AAPL", 10.0, 100.0, mode="paper")
    close_trade(db_conn, tid, 110.0, exit_reason="test")  # +$100 realized
    state = paper_account_state(db_conn, quote_fn=lambda s: None)
    assert state["cash"] == PAPER_STARTING_CASH + 100.0
    assert state["open_positions"] == []


def test_live_trades_excluded(db_conn):
    from swing_lab.tradelog import open_trade
    from swing_lab.execution.paper_account import paper_account_state
    open_trade(db_conn, "LIVE", 10.0, 100.0)  # mode defaults to 'live'
    state = paper_account_state(db_conn, quote_fn=lambda s: 999.0)
    assert state["cash"] == PAPER_STARTING_CASH
    assert state["open_symbols"] == set()


def test_account_state_for_guardrails_includes_daily_stats(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.paper_account import account_state_for_guardrails
    oid = orders.create_order(db_conn, {"mode": "paper", "side": "buy", "symbol": "AAPL",
                                        "shares": 1.0, "est_price": 100.0,
                                        "est_notional": 100.0, "reason": "open_rec"})
    orders.set_status(db_conn, oid, "filled")
    state = account_state_for_guardrails(db_conn, quote_fn=lambda s: None)
    assert state["todays_order_count"] == 1
    assert state["todays_notional"] == 100.0
    assert state["equity"] == PAPER_STARTING_CASH
