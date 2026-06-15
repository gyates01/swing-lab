import json

OPEN_EPISODE = {
    "symbol": "AAPL", "opened_at": "2026-06-01T14:30:00+00:00",
    "closed_at": None, "shares": 10.0, "entry_price": 150.0,
    "exit_price": None, "fees": 0.05, "pnl": None, "pnl_pct": None,
    "broker_order_ids": ["ord-open-1"], "opening_order_id": "ord-open-1",
}
CLOSED_EPISODE = {
    "symbol": "AAPL", "opened_at": "2026-06-01T14:30:00+00:00",
    "closed_at": "2026-06-05T18:00:00+00:00", "shares": 10.0, "entry_price": 150.0,
    "exit_price": 165.0, "fees": 0.10, "pnl": 149.90, "pnl_pct": 0.0999,
    "broker_order_ids": ["ord-open-1", "ord-close-1"], "opening_order_id": "ord-open-1",
}


def test_insert_broker_episode_open(db_conn):
    from swing_lab.db import insert_broker_episode
    trade_id = insert_broker_episode(db_conn, "robinhood", OPEN_EPISODE, rec_id=None)
    db_conn.commit()
    row = db_conn.execute(
        "SELECT symbol, shares, entry_price, exit_price, source, broker, mode, "
        "broker_order_ids_json FROM trades WHERE trade_id = ?", (trade_id,)
    ).fetchone()
    assert row[0] == "AAPL" and row[3] is None  # exit_price NULL -> open
    assert row[4] == "broker" and row[5] == "robinhood" and row[6] == "live"
    assert json.loads(row[7]) == ["ord-open-1"]


def test_find_trade_by_opening_order(db_conn):
    from swing_lab.db import insert_broker_episode, find_trade_by_opening_order
    tid = insert_broker_episode(db_conn, "robinhood", OPEN_EPISODE, rec_id=None)
    db_conn.commit()
    found = find_trade_by_opening_order(db_conn, "robinhood", "ord-open-1")
    assert found["trade_id"] == tid and found["exit_price"] is None
    assert find_trade_by_opening_order(db_conn, "robinhood", "nope") is None


def test_update_trade_close_from_broker(db_conn):
    from swing_lab.db import insert_broker_episode, update_trade_close_from_broker
    tid = insert_broker_episode(db_conn, "robinhood", OPEN_EPISODE, rec_id=None)
    update_trade_close_from_broker(db_conn, tid, CLOSED_EPISODE)
    db_conn.commit()
    row = db_conn.execute(
        "SELECT exit_price, closed_at, pnl, fees, broker_order_ids_json "
        "FROM trades WHERE trade_id = ?", (tid,)
    ).fetchone()
    assert row[0] == 165.0 and row[1] is not None
    assert json.loads(row[4]) == ["ord-open-1", "ord-close-1"]


def test_load_recent_recs_for_symbol(db_conn):
    from swing_lab.db import load_recent_recs_for_symbol
    db_conn.execute(
        "INSERT INTO recommendations (rec_id, batch_id, created_at, scan_id, rank, "
        "symbol, sizing_pct, gate_sizing) VALUES "
        "(1, 1, '2026-06-01T00:00:00+00:00', 1, 1, 'AAPL', 5.0, 1.0)"
    )
    db_conn.execute(
        "INSERT INTO recommendations (rec_id, batch_id, created_at, scan_id, rank, "
        "symbol, sizing_pct, gate_sizing) VALUES "
        "(2, 2, '2026-06-03T00:00:00+00:00', 2, 1, 'MSFT', 5.0, 1.0)"
    )
    db_conn.commit()
    recs = load_recent_recs_for_symbol(db_conn, "AAPL")
    assert [r["rec_id"] for r in recs] == [1]
    assert recs[0]["created_at"] == "2026-06-01T00:00:00+00:00"
