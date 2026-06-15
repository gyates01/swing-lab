"""Pure logic: collapse a stream of broker fills into round-trip position-episodes.

No DB, no broker SDK, no I/O. Long-only assumption: net shares never go negative.
"""
from collections import defaultdict

EPSILON = 1e-6


def _weighted_avg(fills: list[dict]) -> float:
    total_shares = sum(f["shares"] for f in fills)
    if total_shares <= EPSILON:
        return 0.0
    return sum(f["shares"] * f["price"] for f in fills) / total_shares


def _finalize(symbol: str, buys: list[dict], sells: list[dict], closed: bool) -> dict:
    bought = sum(f["shares"] for f in buys)
    sold = sum(f["shares"] for f in sells)
    entry_price = _weighted_avg(buys)
    order_ids = [f["order_id"] for f in (buys + sells)]
    fees = sum(f["fees"] for f in (buys + sells))
    opened_at = min(f["filled_at"] for f in buys)

    if closed:
        exit_price = _weighted_avg(sells)
        closed_at = max(f["filled_at"] for f in sells)
        buy_cost = sum(f["shares"] * f["price"] for f in buys)
        sell_proceeds = sum(f["shares"] * f["price"] for f in sells)
        pnl = sell_proceeds - buy_cost - fees
        pnl_pct = pnl / buy_cost if buy_cost > EPSILON else None
        shares = bought
    else:
        exit_price = None
        closed_at = None
        pnl = None
        pnl_pct = None
        shares = bought - sold  # net still held

    return {
        "symbol": symbol,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "shares": shares,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "fees": fees,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "broker_order_ids": order_ids,
        "opening_order_id": buys[0]["order_id"],
    }


def reconstruct_episodes(fills: list[dict]) -> list[dict]:
    """Group fills by symbol and collapse each flat->long->flat cycle into one episode."""
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for f in fills:
        by_symbol[f["symbol"]].append(f)

    episodes: list[dict] = []
    for symbol, symbol_fills in by_symbol.items():
        ordered = sorted(symbol_fills, key=lambda f: f["filled_at"])
        net = 0.0
        buys: list[dict] = []
        sells: list[dict] = []
        for f in ordered:
            if f["side"] == "buy":
                buys.append(f)
                net += f["shares"]
            else:  # sell
                sells.append(f)
                net -= f["shares"]
                if net <= EPSILON and buys:
                    episodes.append(_finalize(symbol, buys, sells, closed=True))
                    buys, sells, net = [], [], 0.0
        if buys:  # leftover open position
            episodes.append(_finalize(symbol, buys, sells, closed=False))
    return episodes
