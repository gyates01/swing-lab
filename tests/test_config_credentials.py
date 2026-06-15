import pytest


def test_store_then_get_round_trips(monkeypatch):
    store = {}
    monkeypatch.setattr(
        "keyring.set_password",
        lambda service, key, val: store.__setitem__((service, key), val),
    )
    monkeypatch.setattr(
        "keyring.get_password",
        lambda service, key: store.get((service, key)),
    )
    from swing_lab import config
    config.store_broker_credentials("user@example.com", "pw123", "SEED456")
    creds = config.get_broker_credentials()
    assert creds == {
        "username": "user@example.com",
        "password": "pw123",
        "totp_seed": "SEED456",
    }


def test_get_missing_credentials_raises_actionable_error(monkeypatch):
    monkeypatch.setattr("keyring.get_password", lambda service, key: None)
    from swing_lab import config
    with pytest.raises(RuntimeError, match="broker-login"):
        config.get_broker_credentials()
