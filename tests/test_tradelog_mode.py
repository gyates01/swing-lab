def test_open_trade_defaults_to_live(db_conn):
    from swing_lab.tradelog import open_trade
    tid = open_trade(db_conn, "AAPL", 1.0, 100.0)
    row = db_conn.execute("SELECT mode FROM trades WHERE trade_id = ?", (tid,)).fetchone()
    assert row[0] == "live"


def test_open_trade_accepts_paper_mode(db_conn):
    from swing_lab.tradelog import open_trade
    tid = open_trade(db_conn, "AAPL", 1.0, 100.0, mode="paper")
    row = db_conn.execute("SELECT mode FROM trades WHERE trade_id = ?", (tid,)).fetchone()
    assert row[0] == "paper"
