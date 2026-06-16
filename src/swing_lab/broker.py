"""Read-only Robinhood client. The ONLY module that calls robin_stocks.

All methods return plain data structures (no DB, no robin_stocks objects leak out),
so the rest of Swing Lab is decoupled from the unofficial API. Tests replace the
module-level `rh` with a fake — no live calls in the suite.
"""
import robin_stocks.robinhood as rh

from swing_lab.config import get_broker_credentials


def _f(value) -> float | None:
    """Coerce robin_stocks' string/None numerics to float|None."""
    if value is None or value == "":
        return None
    return float(value)


class RobinhoodClient:
    """Thin read-only wrapper over robin_stocks."""

    def __init__(self) -> None:
        self._authenticated = False

    def authenticate(self) -> None:
        """Log in using keyring credentials.

        If a TOTP seed is stored, a 6-digit code is generated and passed for
        fully-headless login. If the seed is blank, no code is passed: robin_stocks
        falls back to Robinhood's device-approval challenge (a push to the mobile
        app), prompting you to approve the login on your phone.

        robin_stocks caches the session token on disk, so 2FA is not re-triggered
        on every run. Raises an actionable error if credentials are missing.
        """
        creds = get_broker_credentials()  # raises RuntimeError -> "run broker-login"
        if creds["totp_seed"]:
            import pyotp
            rh.login(
                username=creds["username"],
                password=creds["password"],
                mfa_code=pyotp.TOTP(creds["totp_seed"]).now(),
                store_session=True,
            )
        else:
            rh.login(
                username=creds["username"],
                password=creds["password"],
                store_session=True,
            )
        self._authenticated = True

    def get_positions(self) -> list[dict]:
        """Current holdings -> [{symbol, quantity, average_buy_price, market_value, last_price}]."""
        holdings = rh.build_holdings()
        positions = []
        for symbol, h in holdings.items():
            quantity = _f(h.get("quantity"))
            if quantity is None or quantity <= 0:
                continue  # fully-exited symbols come back with quantity 0
            positions.append({
                "symbol": symbol,
                "quantity": quantity,
                "average_buy_price": _f(h.get("average_buy_price")),
                "market_value": _f(h.get("equity")),
                "last_price": _f(h.get("price")),
            })
        return positions

    def get_filled_orders(self, since: str | None = None) -> list[dict]:
        """Filled stock orders -> fill dicts (one per order) in reconstruction's contract.

        Only `state == 'filled'` orders are returned. `since` is an ISO timestamp;
        orders transacted before it are dropped.
        """
        orders = rh.get_all_stock_orders()
        fills = []
        for o in orders:
            if o.get("state") != "filled":
                continue
            transacted = o.get("last_transaction_at")
            if since is not None and transacted is not None and transacted < since:
                continue
            fills.append({
                "symbol": rh.get_symbol_by_url(o["instrument"]),
                "side": o["side"],
                "shares": _f(o.get("cumulative_quantity")),
                "price": _f(o.get("average_price")),
                "fees": _f(o.get("fees")) or 0.0,
                "filled_at": transacted,
                "order_id": o["id"],
            })
        return fills

    def get_account_snapshot(self) -> dict:
        """Account equity/buying-power/cash -> {total_equity, buying_power, cash}.

        Sourced from api.robinhood.com (portfolio + account profiles). The phoenix
        unified endpoint exposes the same data but sits behind a TLS-fingerprinting
        WAF that refuses non-browser clients, so it is unreachable from here.
        """
        portfolio = rh.load_portfolio_profile() or {}
        account = rh.load_account_profile() or {}
        return {
            "total_equity": _f(portfolio.get("equity")),
            "buying_power": _f(account.get("buying_power")),
            "cash": _f(account.get("cash")),
        }
