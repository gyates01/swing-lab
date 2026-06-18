from datetime import datetime, timezone


def _insert_rec(conn, **levels):
    cols = ("rec_id", "batch_id", "created_at", "scan_id", "rank", "symbol",
            "sizing_pct", "gate_sizing", "entry_low", "entry_high",
            "support", "stop_price", "target")
    row = {
        "rec_id": 1, "batch_id": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "scan_id": 1, "rank": 1, "symbol": "ALB", "sizing_pct": 0.08, "gate_sizing": 1.0,
        "entry_low": 160.0, "entry_high": 168.0, "support": 150.0,
        "stop_price": 145.0, "target": 190.0,
    }
    row.update(levels)
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(f"INSERT INTO recommendations ({', '.join(cols)}) VALUES ({placeholders})",
                 tuple(row[c] for c in cols))
    conn.commit()


def test_load_recommendation_returns_levels(db_conn):
    from swing_lab.db import load_recommendation
    _insert_rec(db_conn)
    rec = load_recommendation(db_conn, 1)
    assert rec["symbol"] == "ALB"
    assert rec["entry_low"] == 160.0 and rec["entry_high"] == 168.0
    assert rec["support"] == 150.0 and rec["stop_price"] == 145.0 and rec["target"] == 190.0


def test_load_recommendation_missing_returns_none(db_conn):
    from swing_lab.db import load_recommendation
    assert load_recommendation(db_conn, 999) is None
