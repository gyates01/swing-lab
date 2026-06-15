def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_trades_has_broker_columns(db_conn):
    cols = _columns(db_conn, "trades")
    assert {"broker", "broker_order_ids_json", "source", "mode", "fees"} <= cols


def test_trades_mode_defaults_to_live(db_conn):
    db_conn.execute(
        "INSERT INTO trades (opened_at, symbol, side, shares, entry_price) "
        "VALUES ('2026-06-01T00:00:00+00:00', 'AAPL', 'long', 10, 150.0)"
    )
    row = db_conn.execute("SELECT mode FROM trades").fetchone()
    assert row[0] == "live"


def test_positions_table_exists_with_unique_constraint(db_conn):
    cols = _columns(db_conn, "positions")
    assert {"symbol", "quantity", "average_buy_price", "market_value",
            "last_price", "broker", "synced_at"} <= cols
    db_conn.execute(
        "INSERT INTO positions (synced_at, broker, symbol, quantity) "
        "VALUES ('t', 'robinhood', 'AAPL', 5)"
    )
    import sqlite3
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            "INSERT INTO positions (synced_at, broker, symbol, quantity) "
            "VALUES ('t2', 'robinhood', 'AAPL', 7)"
        )


def test_account_snapshots_table_exists(db_conn):
    cols = _columns(db_conn, "account_snapshots")
    assert {"snapshot_id", "synced_at", "broker", "total_equity",
            "buying_power", "cash"} <= cols
