import types
import pytest


def _fake_rh(**overrides):
    """Build a fake robin_stocks.robinhood module surface."""
    mod = types.SimpleNamespace()
    mod.login = overrides.get("login", lambda **kw: {"access_token": "tok"})
    mod.build_holdings = overrides.get("build_holdings", lambda: {})
    mod.get_all_stock_orders = overrides.get("get_all_stock_orders", lambda: [])
    mod.get_symbol_by_url = overrides.get("get_symbol_by_url", lambda url: "AAPL")
    mod.load_phoenix_account = overrides.get(
        "load_phoenix_account",
        lambda: {"total_equity": {"amount": "5000.0"},
                 "account_buying_power": {"amount": "1200.0"},
                 "uninvested_cash": {"amount": "300.0"}},
    )
    return mod


def test_authenticate_missing_credentials_raises(monkeypatch):
    monkeypatch.setattr("keyring.get_password", lambda s, k: None)
    from swing_lab.broker import RobinhoodClient
    client = RobinhoodClient()
    with pytest.raises(RuntimeError, match="broker-login"):
        client.authenticate()


def test_authenticate_passes_totp_code(monkeypatch):
    captured = {}

    def fake_login(**kw):
        captured.update(kw)
        return {"access_token": "tok"}

    monkeypatch.setattr("keyring.get_password",
                        lambda s, k: {"username": "u", "password": "p",
                                      "totp_seed": "JBSWY3DPEHPK3PXP"}[k])
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh", _fake_rh(login=fake_login))
    broker.RobinhoodClient().authenticate()
    assert captured["username"] == "u"
    assert captured["password"] == "p"
    assert captured["mfa_code"].isdigit() and len(captured["mfa_code"]) == 6


def test_authenticate_device_approval_when_no_totp(monkeypatch):
    """Blank TOTP seed -> login without mfa_code, letting robin_stocks drive the
    Robinhood mobile-app approval prompt."""
    captured = {}

    def fake_login(**kw):
        captured.update(kw)
        return {"access_token": "tok"}

    monkeypatch.setattr("keyring.get_password",
                        lambda s, k: {"username": "u", "password": "p",
                                      "totp_seed": ""}[k])
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh", _fake_rh(login=fake_login))
    broker.RobinhoodClient().authenticate()
    assert captured["username"] == "u"
    assert captured["password"] == "p"
    assert "mfa_code" not in captured


def test_get_positions_normalizes_holdings(monkeypatch):
    holdings = {
        "AAPL": {"quantity": "10.0000", "average_buy_price": "150.00",
                 "equity": "1600.00", "price": "160.00"},
    }
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh", _fake_rh(build_holdings=lambda: holdings))
    positions = broker.RobinhoodClient().get_positions()
    assert positions == [{"symbol": "AAPL", "quantity": 10.0,
                          "average_buy_price": 150.0, "market_value": 1600.0,
                          "last_price": 160.0}]


def test_get_positions_excludes_zero_quantity_holdings(monkeypatch):
    """build_holdings() returns fully-exited symbols with quantity 0 — not real holdings."""
    holdings = {
        "AAPL": {"quantity": "10.0000", "average_buy_price": "150.00",
                 "equity": "1600.00", "price": "160.00"},
        "SNDK": {"quantity": "0.0000", "average_buy_price": "0.00",
                 "equity": "0.00", "price": "0.00"},
    }
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh", _fake_rh(build_holdings=lambda: holdings))
    positions = broker.RobinhoodClient().get_positions()
    assert [p["symbol"] for p in positions] == ["AAPL"]


def test_get_filled_orders_filters_and_normalizes(monkeypatch):
    orders = [
        {"state": "filled", "side": "buy", "average_price": "150.00",
         "cumulative_quantity": "10.00000", "fees": "0.03",
         "last_transaction_at": "2026-06-01T14:30:00Z",
         "id": "ord-1", "instrument": "https://api.robinhood.com/instruments/abc/"},
        {"state": "cancelled", "side": "buy", "average_price": None,
         "cumulative_quantity": "0", "fees": "0",
         "last_transaction_at": "2026-06-02T14:30:00Z",
         "id": "ord-2", "instrument": "https://api.robinhood.com/instruments/abc/"},
    ]
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh",
                        _fake_rh(get_all_stock_orders=lambda: orders,
                                 get_symbol_by_url=lambda url: "AAPL"))
    fills = broker.RobinhoodClient().get_filled_orders()
    assert len(fills) == 1
    assert fills[0] == {"symbol": "AAPL", "side": "buy", "shares": 10.0,
                        "price": 150.0, "fees": 0.03,
                        "filled_at": "2026-06-01T14:30:00Z", "order_id": "ord-1"}


def test_get_filled_orders_since_filters_old(monkeypatch):
    orders = [
        {"state": "filled", "side": "buy", "average_price": "100.0",
         "cumulative_quantity": "1", "fees": "0",
         "last_transaction_at": "2026-01-01T00:00:00Z",
         "id": "old", "instrument": "x"},
        {"state": "filled", "side": "buy", "average_price": "100.0",
         "cumulative_quantity": "1", "fees": "0",
         "last_transaction_at": "2026-06-01T00:00:00Z",
         "id": "new", "instrument": "x"},
    ]
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh",
                        _fake_rh(get_all_stock_orders=lambda: orders))
    fills = broker.RobinhoodClient().get_filled_orders(since="2026-05-01T00:00:00Z")
    assert [f["order_id"] for f in fills] == ["new"]


def test_get_account_snapshot_normalizes(monkeypatch):
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh", _fake_rh())
    snap = broker.RobinhoodClient().get_account_snapshot()
    assert snap == {"total_equity": 5000.0, "buying_power": 1200.0, "cash": 300.0}
