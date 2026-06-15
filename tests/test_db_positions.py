def test_replace_positions_upserts_and_removes_sold(db_conn):
    from swing_lab.db import replace_positions, load_positions
    first = [
        {"symbol": "AAPL", "quantity": 10, "average_buy_price": 150.0,
         "market_value": 1600.0, "last_price": 160.0},
        {"symbol": "MSFT", "quantity": 5, "average_buy_price": 300.0,
         "market_value": 1550.0, "last_price": 310.0},
    ]
    replace_positions(db_conn, "robinhood", first)
    db_conn.commit()
    held = {p["symbol"]: p["quantity"] for p in load_positions(db_conn, "robinhood")}
    assert held == {"AAPL": 10, "MSFT": 5}

    # Second sync: MSFT sold out, AAPL changed -> snapshot fully replaced
    second = [{"symbol": "AAPL", "quantity": 8, "average_buy_price": 150.0,
               "market_value": 1280.0, "last_price": 160.0}]
    replace_positions(db_conn, "robinhood", second)
    db_conn.commit()
    held = {p["symbol"]: p["quantity"] for p in load_positions(db_conn, "robinhood")}
    assert held == {"AAPL": 8}


def test_replace_positions_does_not_commit(db_conn):
    from swing_lab.db import replace_positions
    replace_positions(db_conn, "robinhood",
                      [{"symbol": "AAPL", "quantity": 1, "average_buy_price": 1.0,
                        "market_value": 1.0, "last_price": 1.0}])
    db_conn.rollback()  # uncommitted -> rollback must wipe it
    rows = db_conn.execute("SELECT COUNT(*) FROM positions").fetchone()
    assert rows[0] == 0


def test_save_account_snapshot(db_conn):
    from swing_lab.db import save_account_snapshot
    save_account_snapshot(db_conn, "robinhood",
                          {"total_equity": 5000.0, "buying_power": 1200.0, "cash": 300.0})
    db_conn.commit()
    row = db_conn.execute(
        "SELECT total_equity, buying_power, cash FROM account_snapshots"
    ).fetchone()
    assert row == (5000.0, 1200.0, 300.0)
