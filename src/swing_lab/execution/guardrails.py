"""Guardrail engine — pure checks run at propose-time AND execute-time.

Thresholds are read via `config.X` attribute access so tests can monkeypatch them.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from swing_lab import config

_ET = ZoneInfo("America/New_York")


def _now_et() -> datetime:
    return datetime.now(_ET)


def _is_rth(now_et: datetime) -> bool:
    """True on weekdays between 09:30 and 16:00 ET."""
    if now_et.weekday() >= 5:
        return False
    minutes = now_et.hour * 60 + now_et.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def check(proposal: dict, account_state: dict, now_et: datetime | None = None) -> list[str]:
    """Return a list of violation strings. Empty list = passes."""
    if config.EXECUTION_KILL_SWITCH:
        return ["kill switch engaged"]  # hard stop, nothing else matters

    violations: list[str] = []
    now = now_et if now_et is not None else _now_et()
    if not _is_rth(now):
        violations.append("outside regular trading hours")

    equity = account_state["equity"]
    notional = proposal["est_notional"]

    # Daily caps apply to both sides
    if account_state["todays_order_count"] >= config.MAX_ORDERS_PER_DAY:
        violations.append(
            f"daily order count {account_state['todays_order_count']} >= {config.MAX_ORDERS_PER_DAY}")
    if account_state["todays_notional"] + notional > config.MAX_NOTIONAL_PER_DAY_PCT * equity:
        violations.append("daily notional cap exceeded")

    # Buy-only checks (closing reduces risk, so sells are exempt)
    if proposal["side"] == "buy":
        if notional > config.MAX_POSITION_PCT * equity + 1e-6:
            violations.append("position exceeds max position size")
        if account_state["cash"] - notional < config.CASH_RESERVE_PCT * equity:
            violations.append("insufficient cash reserve")
        is_new = proposal["symbol"] not in account_state["open_symbols"]
        if is_new and len(account_state["open_symbols"]) >= config.MAX_OPEN_POSITIONS:
            violations.append("max open positions reached")

    return violations
