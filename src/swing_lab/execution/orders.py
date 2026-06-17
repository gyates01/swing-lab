"""Queue CRUD over the `orders` table — the single source of truth."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_SETTABLE = {"status", "decided_at", "filled_at", "fill_price",
             "trade_id", "notes", "guardrail_json"}

_ET = ZoneInfo("America/New_York")


def create_order(conn, proposal: dict, guardrail: list | None = None) -> int:
    """Insert a pending order from a proposal dict. Return order_id."""
    created_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO orders
           (created_at, mode, side, symbol, shares, est_price, est_notional,
            reason, rec_id, trade_id, status, guardrail_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
        (created_at, proposal["mode"], proposal["side"], proposal["symbol"],
         proposal["shares"], proposal.get("est_price"), proposal.get("est_notional"),
         proposal.get("reason"), proposal.get("rec_id"), proposal.get("trade_id"),
         json.dumps(guardrail or [])),
    )
    conn.commit()
    return cursor.lastrowid


def get_order(conn, order_id: int) -> dict | None:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def list_orders(conn, status: str | None = None) -> list[dict]:
    cursor = conn.cursor()
    if status is None:
        cursor.execute("SELECT * FROM orders ORDER BY order_id")
    else:
        cursor.execute("SELECT * FROM orders WHERE status = ? ORDER BY order_id", (status,))
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def set_status(conn, order_id: int, status: str, **fields) -> None:
    """Set status plus any whitelisted extra columns. Column names are whitelisted."""
    updates = {"status": status}
    for k, v in fields.items():
        if k in _SETTABLE:
            updates[k] = v
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [order_id]
    conn.execute(f"UPDATE orders SET {set_clause} WHERE order_id = ?", values)
    conn.commit()


def pending_symbols(conn, side: str | None = None) -> set:
    cursor = conn.cursor()
    if side is None:
        cursor.execute("SELECT symbol FROM orders WHERE status = 'pending'")
    else:
        cursor.execute("SELECT symbol FROM orders WHERE status = 'pending' AND side = ?", (side,))
    return {row[0] for row in cursor.fetchall()}


def todays_stats(conn) -> dict:
    """Today's FILLED order count + notional (filled-only avoids execute-time double-count)."""
    today_utc = datetime.now(timezone.utc).date().isoformat()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT COUNT(*), COALESCE(SUM(est_notional), 0.0)
           FROM orders WHERE status = 'filled' AND date(created_at) = ?""",
        (today_utc,),
    )
    count, notional = cursor.fetchone()
    return {"order_count": count, "notional": notional}


def expire_stale(conn, now_et: datetime | None = None) -> int:
    """Mark pending/approved orders from a prior ET trading day as expired. Return count.

    Cutoff is midnight of the current ET day (not the UTC day) so an after-hours proposal
    doesn't survive into the next session just because they share a UTC calendar date.
    """
    now = now_et if now_et is not None else datetime.now(_ET)
    session_start_utc = now.replace(
        hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE orders SET status = 'expired'
           WHERE status IN ('pending', 'approved') AND datetime(created_at) < datetime(?)""",
        (session_start_utc,),
    )
    conn.commit()
    return cursor.rowcount
