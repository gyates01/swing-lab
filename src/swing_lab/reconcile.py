"""Pure logic: compare reconstructed open episodes against the broker positions
snapshot. The snapshot is authoritative; mismatches are returned as warnings for a
human to review — never silently rewritten.
"""
TOLERANCE = 1e-4


def reconcile(open_episodes: list[dict], snapshot_positions: list[dict]) -> list[str]:
    """Return a list of human-readable discrepancy warnings (empty = consistent)."""
    snap = {p["symbol"]: p["quantity"] for p in snapshot_positions}
    episode_symbols = set()
    warnings: list[str] = []

    for ep in open_episodes:
        sym = ep["symbol"]
        episode_symbols.add(sym)
        snap_qty = snap.get(sym)
        if snap_qty is None:
            warnings.append(
                f"{sym}: reconstructed open position ({ep['shares']}) not in broker snapshot"
            )
        elif abs(snap_qty - ep["shares"]) > TOLERANCE:
            warnings.append(
                f"{sym}: broker snapshot ({snap_qty}) != reconstructed ({ep['shares']})"
            )

    for sym, qty in snap.items():
        if sym not in episode_symbols:
            warnings.append(
                f"{sym}: held in broker snapshot ({qty}) but no reconstructed open episode"
            )
    return warnings
