from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _rth(monkeypatch):
    """Pin guardrail clock to a weekday noon so propose-time checks are deterministic."""
    from zoneinfo import ZoneInfo
    monkeypatch.setattr("swing_lab.execution.guardrails._now_et",
                        lambda: datetime(2026, 6, 17, 12, 0, tzinfo=ZoneInfo("America/New_York")))


def _seed_scan(conn, symbols):
    cur = conn.cursor()
    cur.execute("INSERT INTO scans (run_at, gate_score, sizing) VALUES (?, 1.0, 1.0)",
                (datetime.now(timezone.utc).isoformat(),))
    sid = cur.lastrowid
    for i, s in enumerate(symbols):
        cur.execute("INSERT INTO scan_picks (scan_id, symbol, rank_score) VALUES (?, ?, ?)",
                    (sid, s, float(len(symbols) - i)))
    conn.commit()
    return sid


def _seed_recs(conn, scan_id, recs):
    """recs: list of (rank, symbol, sizing_pct)."""
    created_at = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    for rank, symbol, sizing_pct in recs:
        cur.execute(
            """INSERT INTO recommendations
               (batch_id, created_at, scan_id, rank, symbol, sizing_pct, gate_sizing)
               VALUES (1, ?, ?, ?, ?, ?, 1.0)""",
            (created_at, scan_id, rank, symbol, sizing_pct))
    conn.commit()


def test_generates_buy_from_rec(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.proposals import generate_proposals
    sid = _seed_scan(db_conn, ["AAPL"])
    _seed_recs(db_conn, sid, [(1, "AAPL", 0.05)])
    result = generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    assert len(result["created"]) == 1
    o = result["created"][0]
    assert o["side"] == "buy" and o["symbol"] == "AAPL"
    assert o["shares"] == 5.0 and o["est_notional"] == 500.0
    assert orders.list_orders(db_conn, status="pending")[0]["symbol"] == "AAPL"


def test_full_size_open_not_flagged_by_rounding(db_conn):
    """sizing_pct == MAX_POSITION_PCT must not trip 'exceeds max' via share rounding."""
    import json
    from swing_lab import config
    from swing_lab.execution.proposals import generate_proposals
    sid = _seed_scan(db_conn, ["XYZ"])
    _seed_recs(db_conn, sid, [(1, "XYZ", config.MAX_POSITION_PCT)])  # exactly at the cap
    result = generate_proposals(db_conn, quote_fn=lambda s: 166.11)  # doesn't divide evenly
    o = result["created"][0]
    cap = config.MAX_POSITION_PCT * config.PAPER_STARTING_CASH
    assert o["est_notional"] <= cap + 1e-6
    assert "position exceeds max position size" not in json.loads(o["guardrail_json"])


def test_skips_held_symbol(db_conn):
    from swing_lab.tradelog import open_trade
    from swing_lab.execution.proposals import generate_proposals
    open_trade(db_conn, "AAPL", 5.0, 100.0, mode="paper")
    sid = _seed_scan(db_conn, ["AAPL"])
    _seed_recs(db_conn, sid, [(1, "AAPL", 0.05)])
    result = generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    assert result["created"] == []  # held -> no buy; still a top-pick -> no close


def test_dedup_idempotent(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.proposals import generate_proposals
    sid = _seed_scan(db_conn, ["AAPL"])
    _seed_recs(db_conn, sid, [(1, "AAPL", 0.05)])
    generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    generate_proposals(db_conn, quote_fn=lambda s: 100.0)  # re-run
    assert len(orders.list_orders(db_conn, status="pending")) == 1


def test_below_min_notional_skipped(db_conn):
    from swing_lab.execution.proposals import generate_proposals
    sid = _seed_scan(db_conn, ["AAPL"])
    _seed_recs(db_conn, sid, [(1, "AAPL", 0.00001)])  # 0.00001*10000 = $0.10 notional
    result = generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    assert result["created"] == []
    assert any("minimum" in w for w in result["warnings"])


def test_close_on_scan_dropout(db_conn):
    from swing_lab.tradelog import open_trade
    from swing_lab.execution.proposals import generate_proposals
    open_trade(db_conn, "OLD", 10.0, 100.0, mode="paper")  # held, not in scan
    sid = _seed_scan(db_conn, ["NEW"])                     # OLD has dropped out
    _seed_recs(db_conn, sid, [(1, "NEW", 0.05)])
    result = generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    sells = [o for o in result["created"] if o["side"] == "sell"]
    assert len(sells) == 1
    assert sells[0]["symbol"] == "OLD" and sells[0]["shares"] == 10.0
    assert sells[0]["trade_id"] is not None


def test_no_recs_warns(db_conn):
    from swing_lab.execution.proposals import generate_proposals
    _seed_scan(db_conn, ["AAPL"])  # scan but no recs today
    result = generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    assert result["created"] == []
    assert any("recommend" in w for w in result["warnings"])


def test_quote_none_skips_open(db_conn):
    from swing_lab.execution.proposals import generate_proposals
    sid = _seed_scan(db_conn, ["AAPL"])
    _seed_recs(db_conn, sid, [(1, "AAPL", 0.05)])
    result = generate_proposals(db_conn, quote_fn=lambda s: None)
    assert result["created"] == []
    assert any("no quote" in w for w in result["warnings"])
