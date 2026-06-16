import types
import pandas as pd


class _FakeTicker:
    def __init__(self, last_price=None, hist=None):
        self.fast_info = types.SimpleNamespace(last_price=last_price)
        self._hist = hist if hist is not None else pd.DataFrame()

    def history(self, period="2d"):
        return self._hist


def test_get_quote_uses_fast_info(monkeypatch):
    from swing_lab.execution import quotes
    monkeypatch.setattr(quotes, "yf",
                        types.SimpleNamespace(Ticker=lambda s: _FakeTicker(last_price=123.45)))
    assert quotes.get_quote("AAPL") == 123.45


def test_get_quote_falls_back_to_history(monkeypatch):
    from swing_lab.execution import quotes
    df = pd.DataFrame({"Close": [100.0, 150.0]})
    monkeypatch.setattr(quotes, "yf",
                        types.SimpleNamespace(Ticker=lambda s: _FakeTicker(last_price=None, hist=df)))
    assert quotes.get_quote("AAPL") == 150.0


def test_get_quote_returns_none_on_error(monkeypatch):
    from swing_lab.execution import quotes

    def boom(symbol):
        raise RuntimeError("network down")

    monkeypatch.setattr(quotes, "yf", types.SimpleNamespace(Ticker=boom))
    assert quotes.get_quote("AAPL") is None
