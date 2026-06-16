from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _rth(monkeypatch):
    from zoneinfo import ZoneInfo
    monkeypatch.setattr("swing_lab.execution.guardrails._now_et",
                        lambda: datetime(2026, 6, 17, 12, 0, tzinfo=ZoneInfo("America/New_York")))


def _approved(conn, **kw):
    """Create an order and move it to 'approved'. Return order_id."""
    from swing_lab.execution import orders
    base = {"mode": "paper", "side": "buy", "symbol": "AAPL", "shares": 5.0,
            "est_price": 100.0, "est_notional": 500.0, "reason": "open_rec",
            "rec_id": 1, "trade_id": None}
    base.update(kw)
    oid = orders.create_order(conn, base)
    orders.set_status(conn, oid, "approved", decided_at=datetime.now(timezone.utc).isoformat())
    return oid


def test_buy_fills_and_opens_paper_trade(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.executor import execute_approved
    from swing_lab.tradelog import open_trades
    oid = _approved(db_conn)
    result = execute_approved(db_conn, quote_fn=lambda s: 100.0)
    assert result["filled"] == [oid]
    o = orders.get_order(db_conn, oid)
    assert o["status"] == "filled" and o["fill_price"] == 100.0 and o["trade_id"] is not None
    opens = open_trades(db_conn)
    assert len(opens) == 1 and opens[0]["symbol"] == "AAPL" and opens[0]["mode"] == "paper"


def test_sell_closes_paper_trade(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.executor import execute_approved
    from swing_lab.tradelog import open_trade
    tid = open_trade(db_conn, "AAPL", 10.0, 100.0, mode="paper")
    oid = _approved(db_conn, side="sell", symbol="AAPL", shares=10.0,
                    est_notional=1000.0, reason="rebalance_close", rec_id=None, trade_id=tid)
    result = execute_approved(db_conn, quote_fn=lambda s: 110.0)
    assert result["filled"] == [oid]
    closed = db_conn.execute("SELECT exit_price, pnl FROM trades WHERE trade_id = ?", (tid,)).fetchone()
    assert closed[0] == 110.0 and closed[1] == 100.0  # (110-100)*10


def test_quote_none_keeps_approved(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.executor import execute_approved
    oid = _approved(db_conn)
    result = execute_approved(db_conn, quote_fn=lambda s: None)
    assert result["skipped"] == [oid] and result["filled"] == []
    assert orders.get_order(db_conn, oid)["status"] == "approved"


def test_late_guardrail_rejection(db_conn, monkeypatch):
    from swing_lab.execution import guardrails, orders
    from swing_lab.execution.executor import execute_approved
    oid = _approved(db_conn)
    monkeypatch.setattr(guardrails.config, "EXECUTION_KILL_SWITCH", True)
    result = execute_approved(db_conn, quote_fn=lambda s: 100.0)
    assert result["rejected"] == [oid]
    o = orders.get_order(db_conn, oid)
    assert o["status"] == "rejected" and "kill switch" in o["notes"]


def test_partial_batch_independence(db_conn):
    from swing_lab.execution.executor import execute_approved
    good = _approved(db_conn, symbol="AAPL")
    bad = _approved(db_conn, symbol="MSFT")
    result = execute_approved(db_conn, quote_fn=lambda s: 100.0 if s == "AAPL" else None)
    assert result["filled"] == [good] and result["skipped"] == [bad]
