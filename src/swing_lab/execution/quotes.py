"""Current market quote lookup (yfinance). Module-level `yf` so tests can fake it."""
import yfinance as yf


def get_quote(symbol: str) -> float | None:
    """Return the latest price for a symbol, or None if unavailable."""
    try:
        ticker = yf.Ticker(symbol)
        price = getattr(ticker.fast_info, "last_price", None)
        if price is not None:
            return float(price)
        hist = ticker.history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None
