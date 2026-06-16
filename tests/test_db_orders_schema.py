from datetime import datetime, timezone


def test_orders_table_exists(db_conn):
    cur = db_conn.execute("PRAGMA table_info(orders)")
    cols = {row[1] for row in cur.fetchall()}
    assert {"order_id", "created_at", "mode", "side", "symbol", "shares",
            "est_price", "est_notional", "reason", "rec_id", "trade_id",
            "status", "guardrail_json", "decided_at", "filled_at",
            "fill_price", "notes"} <= cols


def test_load_latest_scan_picks_orders_by_rank_desc(db_conn):
    from swing_lab.db import load_latest_scan_picks
    cur = db_conn.cursor()
    cur.execute("INSERT INTO scans (run_at, gate_score, sizing) VALUES (?, 1.0, 1.0)",
                (datetime.now(timezone.utc).isoformat(),))
    sid = cur.lastrowid
    cur.execute("INSERT INTO scan_picks (scan_id, symbol, rank_score) VALUES (?, 'AAPL', 5.0)", (sid,))
    cur.execute("INSERT INTO scan_picks (scan_id, symbol, rank_score) VALUES (?, 'MSFT', 9.0)", (sid,))
    db_conn.commit()
    picks = load_latest_scan_picks(db_conn)
    assert [p["symbol"] for p in picks] == ["MSFT", "AAPL"]


def test_load_latest_scan_picks_only_latest_scan(db_conn):
    from swing_lab.db import load_latest_scan_picks
    cur = db_conn.cursor()
    cur.execute("INSERT INTO scans (run_at, gate_score, sizing) VALUES (?, 1.0, 1.0)",
                (datetime.now(timezone.utc).isoformat(),))
    old = cur.lastrowid
    cur.execute("INSERT INTO scan_picks (scan_id, symbol, rank_score) VALUES (?, 'OLD', 1.0)", (old,))
    cur.execute("INSERT INTO scans (run_at, gate_score, sizing) VALUES (?, 1.0, 1.0)",
                (datetime.now(timezone.utc).isoformat(),))
    new = cur.lastrowid
    cur.execute("INSERT INTO scan_picks (scan_id, symbol, rank_score) VALUES (?, 'NEW', 1.0)", (new,))
    db_conn.commit()
    assert [p["symbol"] for p in load_latest_scan_picks(db_conn)] == ["NEW"]
