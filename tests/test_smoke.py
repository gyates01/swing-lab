def test_db_fixture_creates_trades_table(db_conn):
    cur = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='trades'"
    )
    assert cur.fetchone() is not None
