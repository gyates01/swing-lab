"""Sync orchestrator: pull Robinhood data -> reconstruct -> match -> persist.

Owns a single DB transaction (`with conn:`); the broker DB helpers do not commit,
so the whole sync is atomic and rolls back on any error. Idempotent: episodes are
keyed by their opening order id, so re-running never duplicates trades.
"""
from datetime import datetime, timedelta, timezone

from swing_lab.config import BROKER
from swing_lab.db import (
    replace_positions, save_account_snapshot, insert_broker_episode,
    update_trade_close_from_broker, find_trade_by_opening_order,
    load_recent_recs_for_symbol,
)
from swing_lab.reconstruction import reconstruct_episodes
from swing_lab.rec_match import find_matching_rec
from swing_lab.reconcile import reconcile


def sync_account(conn, client, lookback_days: int, match_window_days: int) -> dict:
    """Run a full read-only sync. Returns a summary dict."""
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

    positions = client.get_positions()
    snapshot = client.get_account_snapshot()
    fills = client.get_filled_orders(since=since)
    episodes = reconstruct_episodes(fills)

    inserted = updated = skipped = 0

    with conn:  # atomic: commits on success, rolls back on exception
        replace_positions(conn, BROKER, positions)
        save_account_snapshot(conn, BROKER, snapshot)

        for ep in episodes:
            existing = find_trade_by_opening_order(conn, BROKER, ep["opening_order_id"])
            if existing is None:
                recs = load_recent_recs_for_symbol(conn, ep["symbol"])
                rec_id = find_matching_rec(ep["opened_at"], recs, match_window_days)
                insert_broker_episode(conn, BROKER, ep, rec_id)
                inserted += 1
            elif existing["exit_price"] is None and ep["exit_price"] is not None:
                update_trade_close_from_broker(conn, existing["trade_id"], ep)
                updated += 1
            else:
                skipped += 1

        open_eps = [e for e in episodes if e["exit_price"] is None]
        warnings = reconcile(open_eps, positions)

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "positions": len(positions),
        "warnings": warnings,
    }
