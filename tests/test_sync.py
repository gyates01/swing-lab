from swing_lab.sync import sync_account


class FakeClient:
    def __init__(self, positions=None, fills=None, snapshot=None):
        self._positions = positions or []
        self._fills = fills or []
        self._snapshot = snapshot or {"total_equity": 1000.0,
                                      "buying_power": 500.0, "cash": 100.0}

    def get_positions(self):
        return self._positions

    def get_filled_orders(self, since=None):
        return self._fills

    def get_account_snapshot(self):
        return self._snapshot


def _fill(symbol, side, shares, price, day, order_id, fees=0.0):
    return {"symbol": symbol, "side": side, "shares": shares, "price": price,
            "fees": fees, "filled_at": f"2026-06-{day:02d}T14:30:00+00:00",
            "order_id": order_id}


def test_sync_imports_closed_episode(db_conn):
    client = FakeClient(
        positions=[],
        fills=[_fill("AAPL", "buy", 10, 150.0, 1, "o1"),
               _fill("AAPL", "sell", 10, 165.0, 5, "o2")],
    )
    summary = sync_account(db_conn, client, lookback_days=90, match_window_days=5)
    assert summary["inserted"] == 1
    row = db_conn.execute(
        "SELECT symbol, exit_price, source, broker FROM trades"
    ).fetchone()
    assert row == ("AAPL", 165.0, "broker", "robinhood")


def test_sync_is_idempotent(db_conn):
    fills = [_fill("AAPL", "buy", 10, 150.0, 1, "o1"),
             _fill("AAPL", "sell", 10, 165.0, 5, "o2")]
    client = FakeClient(fills=fills)
    sync_account(db_conn, client, 90, 5)
    summary2 = sync_account(db_conn, client, 90, 5)
    assert summary2["inserted"] == 0
    assert summary2["skipped"] == 1
    count = db_conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    assert count == 1


def test_sync_updates_open_then_closed(db_conn):
    # First sync: only a buy -> open trade
    client1 = FakeClient(
        positions=[{"symbol": "AAPL", "quantity": 10.0, "average_buy_price": 150.0,
                    "market_value": 1500.0, "last_price": 150.0}],
        fills=[_fill("AAPL", "buy", 10, 150.0, 1, "o1")],
    )
    sync_account(db_conn, client1, 90, 5)
    assert db_conn.execute(
        "SELECT exit_price FROM trades").fetchone()[0] is None

    # Second sync: the sell appears -> same trade closes
    client2 = FakeClient(
        positions=[],
        fills=[_fill("AAPL", "buy", 10, 150.0, 1, "o1"),
               _fill("AAPL", "sell", 10, 165.0, 5, "o2")],
    )
    summary = sync_account(db_conn, client2, 90, 5)
    assert summary["updated"] == 1
    count = db_conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    assert count == 1
    assert db_conn.execute("SELECT exit_price FROM trades").fetchone()[0] == 165.0


def test_sync_matches_recommendation(db_conn):
    db_conn.execute(
        "INSERT INTO recommendations (rec_id, batch_id, created_at, scan_id, rank, "
        "symbol, sizing_pct, gate_sizing) VALUES "
        "(42, 1, '2026-06-01T00:00:00+00:00', 1, 1, 'AAPL', 5.0, 1.0)"
    )
    db_conn.commit()
    client = FakeClient(
        fills=[_fill("AAPL", "buy", 10, 150.0, 3, "o1"),   # opened within 5 td of rec
               _fill("AAPL", "sell", 10, 165.0, 5, "o2")],
    )
    sync_account(db_conn, client, 90, 5)
    assert db_conn.execute("SELECT rec_id FROM trades").fetchone()[0] == 42


def test_sync_discretionary_trade_has_null_rec(db_conn):
    client = FakeClient(
        fills=[_fill("TSLA", "buy", 1, 200.0, 1, "o1"),
               _fill("TSLA", "sell", 1, 210.0, 3, "o2")],
    )
    sync_account(db_conn, client, 90, 5)
    assert db_conn.execute("SELECT rec_id FROM trades").fetchone()[0] is None


def test_sync_populates_positions_snapshot(db_conn):
    client = FakeClient(
        positions=[{"symbol": "AAPL", "quantity": 10.0, "average_buy_price": 150.0,
                    "market_value": 1600.0, "last_price": 160.0}],
        fills=[_fill("AAPL", "buy", 10, 150.0, 1, "o1")],
    )
    summary = sync_account(db_conn, client, 90, 5)
    from swing_lab.db import load_positions
    held = load_positions(db_conn, "robinhood")
    assert len(held) == 1 and held[0]["symbol"] == "AAPL"
    assert summary["positions"] == 1


def test_sync_reconciliation_warns_on_mismatch(db_conn):
    # Reconstruction says 10 open; snapshot says 8 -> warning
    client = FakeClient(
        positions=[{"symbol": "AAPL", "quantity": 8.0, "average_buy_price": 150.0,
                    "market_value": 1280.0, "last_price": 160.0}],
        fills=[_fill("AAPL", "buy", 10, 150.0, 1, "o1")],
    )
    summary = sync_account(db_conn, client, 90, 5)
    assert any("AAPL" in w for w in summary["warnings"])
