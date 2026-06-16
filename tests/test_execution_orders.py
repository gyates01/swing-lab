def _prop(**kw):
    base = {"mode": "paper", "side": "buy", "symbol": "AAPL", "shares": 10.0,
            "est_price": 100.0, "est_notional": 1000.0, "reason": "open_rec",
            "rec_id": 1, "trade_id": None}
    base.update(kw)
    return base


def test_create_and_get_order(db_conn):
    from swing_lab.execution import orders
    oid = orders.create_order(db_conn, _prop(), guardrail=[])
    o = orders.get_order(db_conn, oid)
    assert o["symbol"] == "AAPL"
    assert o["status"] == "pending"
    assert o["guardrail_json"] == "[]"


def test_create_order_serializes_violations(db_conn):
    from swing_lab.execution import orders
    oid = orders.create_order(db_conn, _prop(), guardrail=["kill switch engaged"])
    assert orders.get_order(db_conn, oid)["guardrail_json"] == '["kill switch engaged"]'


def test_list_orders_filters_by_status(db_conn):
    from swing_lab.execution import orders
    orders.create_order(db_conn, _prop(symbol="AAPL"))
    oid2 = orders.create_order(db_conn, _prop(symbol="MSFT"))
    orders.set_status(db_conn, oid2, "approved", decided_at="2026-06-16T12:00:00Z")
    assert [o["symbol"] for o in orders.list_orders(db_conn, status="pending")] == ["AAPL"]
    assert len(orders.list_orders(db_conn)) == 2


def test_set_status_whitelists_fields(db_conn):
    from swing_lab.execution import orders
    oid = orders.create_order(db_conn, _prop())
    orders.set_status(db_conn, oid, "filled", filled_at="2026-06-16T12:00:00Z",
                      fill_price=101.0, trade_id=7, bogus="ignored")
    o = orders.get_order(db_conn, oid)
    assert o["status"] == "filled"
    assert o["fill_price"] == 101.0
    assert o["trade_id"] == 7
    assert "bogus" not in o


def test_pending_symbols(db_conn):
    from swing_lab.execution import orders
    orders.create_order(db_conn, _prop(symbol="AAPL", side="buy"))
    orders.create_order(db_conn, _prop(symbol="TSLA", side="sell"))
    assert orders.pending_symbols(db_conn) == {"AAPL", "TSLA"}
    assert orders.pending_symbols(db_conn, side="buy") == {"AAPL"}


def test_todays_stats_counts_filled_only(db_conn):
    from swing_lab.execution import orders
    o1 = orders.create_order(db_conn, _prop(est_notional=1000.0))
    orders.create_order(db_conn, _prop(symbol="MSFT", est_notional=500.0))  # stays pending
    orders.set_status(db_conn, o1, "filled")
    stats = orders.todays_stats(db_conn)
    assert stats["order_count"] == 1
    assert stats["notional"] == 1000.0


def test_expire_stale_marks_old_pending_and_approved(db_conn):
    from swing_lab.execution import orders
    db_conn.execute(
        """INSERT INTO orders (created_at, mode, side, symbol, shares, est_notional, status)
           VALUES ('2020-01-01T00:00:00Z', 'paper', 'buy', 'AAPL', 1.0, 100.0, 'pending')""")
    db_conn.execute(
        """INSERT INTO orders (created_at, mode, side, symbol, shares, est_notional, status)
           VALUES ('2020-01-01T00:00:00Z', 'paper', 'sell', 'MSFT', 1.0, 100.0, 'approved')""")
    db_conn.commit()
    assert orders.expire_stale(db_conn) == 2
    assert {o["symbol"] for o in orders.list_orders(db_conn, status="expired")} == {"AAPL", "MSFT"}
