from swing_lab.reconcile import reconcile


def test_no_warnings_when_consistent():
    open_eps = [{"symbol": "AAPL", "shares": 10.0}]
    snapshot = [{"symbol": "AAPL", "quantity": 10.0}]
    assert reconcile(open_eps, snapshot) == []


def test_quantity_mismatch_warns():
    open_eps = [{"symbol": "AAPL", "shares": 10.0}]
    snapshot = [{"symbol": "AAPL", "quantity": 8.0}]
    warnings = reconcile(open_eps, snapshot)
    assert len(warnings) == 1 and "AAPL" in warnings[0]


def test_reconstructed_open_missing_from_snapshot_warns():
    open_eps = [{"symbol": "AAPL", "shares": 10.0}]
    warnings = reconcile(open_eps, [])
    assert len(warnings) == 1 and "AAPL" in warnings[0]


def test_snapshot_holding_without_episode_warns():
    snapshot = [{"symbol": "TSLA", "quantity": 3.0}]
    warnings = reconcile([], snapshot)
    assert len(warnings) == 1 and "TSLA" in warnings[0]
