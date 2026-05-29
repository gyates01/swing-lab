"""Trade log CRUD — open/close/list trades in swing.db."""
import sqlite3
from datetime import datetime, timezone
from swing_lab.db import save_trade_outcome


def open_trade(
    conn: sqlite3.Connection,
    symbol: str,
    shares: float,
    entry_price: float,
    scan_id: int | None = None,
    thesis: str = "",
    rec_id: int | None = None,
) -> int:
    """Insert a new open trade. Return trade_id."""
    opened_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO trades
           (opened_at, symbol, side, shares, entry_price, scan_id, rec_id, thesis_text)
           VALUES (?, ?, 'long', ?, ?, ?, ?, ?)""",
        (opened_at, symbol, shares, entry_price, scan_id, rec_id, thesis),
    )
    conn.commit()
    return cursor.lastrowid


def close_trade(
    conn: sqlite3.Connection,
    trade_id: int,
    exit_price: float,
    exit_reason: str = "",
    outcome: dict | None = None,
) -> dict | None:
    """Close an open trade. Compute and store P&L. Optionally save structured outcome. Return updated trade dict."""
    cursor = conn.cursor()

    cursor.execute(
        "SELECT trade_id, shares, entry_price FROM trades WHERE trade_id = ? AND exit_price IS NULL",
        (trade_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None

    trade_id_db, shares, entry_price = row
    pnl = (exit_price - entry_price) * shares
    pnl_pct = (exit_price - entry_price) / entry_price
    closed_at = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """UPDATE trades
           SET closed_at = ?, exit_price = ?, exit_reason = ?, pnl = ?, pnl_pct = ?
           WHERE trade_id = ?""",
        (closed_at, exit_price, exit_reason, pnl, pnl_pct, trade_id),
    )
    conn.commit()

    if outcome:
        save_trade_outcome(conn, trade_id, outcome)

    cursor.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
    updated_row = cursor.fetchone()
    col_names = [desc[0] for desc in cursor.description]
    return dict(zip(col_names, updated_row))


def recent_trades(conn: sqlite3.Connection, n: int = 20) -> list[dict]:
    """Return last n trades as list of dicts (newest first)."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM trades ORDER BY trade_id DESC LIMIT ?",
        (n,),
    )
    rows = cursor.fetchall()
    col_names = [desc[0] for desc in cursor.description]
    return [dict(zip(col_names, row)) for row in rows]


def edit_trade(conn: sqlite3.Connection, trade_id: int, **fields) -> dict | None:
    """Update editable fields on a trade. Recomputes P&L if prices change. Return updated dict."""
    editable = {"symbol", "shares", "entry_price", "exit_price", "thesis_text", "exit_reason"}
    to_set = {k: v for k, v in fields.items() if k in editable and v is not None}
    if not to_set:
        return None

    # Recompute P&L when prices are involved
    if "entry_price" in to_set or "exit_price" in to_set or "shares" in to_set:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT shares, entry_price, exit_price FROM trades WHERE trade_id = ?",
            (trade_id,),
        )
        row = cursor.fetchone()
        if row:
            shares = to_set.get("shares", row[0])
            entry = to_set.get("entry_price", row[1])
            exit_p = to_set.get("exit_price", row[2])
            if entry is not None and exit_p is not None:
                to_set["pnl"] = (exit_p - entry) * shares
                to_set["pnl_pct"] = (exit_p - entry) / entry

    # Column names are whitelisted above — safe to interpolate
    set_clause = ", ".join(f"{k} = ?" for k in to_set)
    values = list(to_set.values()) + [trade_id]
    cursor = conn.cursor()
    cursor.execute(f"UPDATE trades SET {set_clause} WHERE trade_id = ?", values)
    conn.commit()

    cursor.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
    updated = cursor.fetchone()
    if updated is None:
        return None
    col_names = [desc[0] for desc in cursor.description]
    return dict(zip(col_names, updated))


def delete_trade(conn: sqlite3.Connection, trade_id: int) -> bool:
    """Delete a trade by ID. Returns True if a row was deleted."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE trade_id = ?", (trade_id,))
    conn.commit()
    return cursor.rowcount > 0


def open_trades(conn: sqlite3.Connection) -> list[dict]:
    """Return all currently open trades (exit_price IS NULL), newest first."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM trades WHERE exit_price IS NULL ORDER BY trade_id DESC",
    )
    rows = cursor.fetchall()
    col_names = [desc[0] for desc in cursor.description]
    return [dict(zip(col_names, row)) for row in rows]
