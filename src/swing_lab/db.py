"""SQLite schema for swing.db."""
import sqlite3
from datetime import datetime, timezone
from swing_lab.config import DB_PATH


def init_db() -> sqlite3.Connection:
    """Create tables if not exist. Return open connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at  TEXT    NOT NULL,
            gate_score REAL NOT NULL,
            sizing     REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scan_picks (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id  INTEGER NOT NULL REFERENCES scans(scan_id),
            symbol   TEXT    NOT NULL,
            sector   TEXT,
            momentum REAL,
            rank_score REAL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            review_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id        INTEGER NOT NULL REFERENCES scans(scan_id),
            run_at         TEXT    NOT NULL,
            symbol         TEXT    NOT NULL,
            quant_score    REAL,
            claude_score   REAL,
            blended_score  REAL,
            red_flags_json TEXT,
            claude_summary TEXT
        );
        CREATE TABLE IF NOT EXISTS trades (
            trade_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            opened_at   TEXT    NOT NULL,
            closed_at   TEXT,
            symbol      TEXT    NOT NULL,
            side        TEXT    NOT NULL DEFAULT 'long',
            shares      REAL    NOT NULL,
            entry_price REAL    NOT NULL,
            exit_price  REAL,
            scan_id     INTEGER REFERENCES scans(scan_id),
            rec_id      INTEGER REFERENCES recommendations(rec_id),
            thesis_text TEXT,
            exit_reason TEXT,
            pnl         REAL,
            pnl_pct     REAL
        );
        CREATE TABLE IF NOT EXISTS trade_outcomes (
            outcome_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id                    INTEGER NOT NULL UNIQUE REFERENCES trades(trade_id),
            created_at                  TEXT    NOT NULL,
            thesis_validated            TEXT    NOT NULL,
            exit_driver                 TEXT    NOT NULL,
            red_flags_materialized_json TEXT,
            exit_triggers_fired_json    TEXT,
            macro_aligned               TEXT,
            notes                       TEXT
        );
        CREATE TABLE IF NOT EXISTS postmortems (
            postmortem_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at         TEXT    NOT NULL,
            trade_count    INTEGER NOT NULL,
            outcome_count  INTEGER NOT NULL,
            summary_text   TEXT    NOT NULL,
            model          TEXT    NOT NULL,
            cache_hit      INTEGER
        );
        CREATE TABLE IF NOT EXISTS gate_runs (
            gate_id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at             TEXT NOT NULL,
            composite_score    REAL NOT NULL,
            sizing             REAL NOT NULL,
            label              TEXT NOT NULL,
            vix_level          REAL,
            vix_term_structure REAL,
            breadth            REAL,
            credit_spread      REAL,
            put_call           REAL,
            factor_crowding    REAL
        );
        CREATE TABLE IF NOT EXISTS recommendations (
            rec_id              INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id            INTEGER NOT NULL,
            created_at          TEXT    NOT NULL,
            scan_id             INTEGER NOT NULL,
            review_id           INTEGER,
            rank                INTEGER NOT NULL,
            symbol              TEXT    NOT NULL,
            blended_score       REAL,
            sizing_pct          REAL    NOT NULL,
            gate_sizing         REAL    NOT NULL,
            rationale           TEXT,
            risks_json          TEXT,
            exit_triggers_json  TEXT,
            entry_zone          TEXT,
            is_synthesized      INTEGER NOT NULL DEFAULT 0,
            cache_hit           INTEGER,
            price_at_scan       REAL,
            price_session       TEXT,
            entry_low           REAL,
            entry_high          REAL,
            support             REAL,
            stop_price          REAL,
            target              REAL
        );
        CREATE TABLE IF NOT EXISTS analyst_sessions (
            session_id    TEXT PRIMARY KEY,
            saved_at      TEXT NOT NULL,
            title         TEXT NOT NULL,
            messages_json TEXT NOT NULL,
            snapshot_json TEXT
        );
    """)
    # Safe migrations for existing DBs
    for migration in [
        "ALTER TABLE recommendations ADD COLUMN exit_triggers_json TEXT",
        "ALTER TABLE recommendations ADD COLUMN entry_zone TEXT",
        "ALTER TABLE recommendations ADD COLUMN price_at_scan REAL",
        "ALTER TABLE recommendations ADD COLUMN price_session TEXT",
        "ALTER TABLE trades ADD COLUMN rec_id INTEGER",
        "ALTER TABLE recommendations ADD COLUMN entry_low REAL",
        "ALTER TABLE recommendations ADD COLUMN entry_high REAL",
        "ALTER TABLE recommendations ADD COLUMN support REAL",
        "ALTER TABLE recommendations ADD COLUMN stop_price REAL",
        "ALTER TABLE recommendations ADD COLUMN target REAL",
    ]:
        try:
            conn.execute(migration)
            conn.commit()
        except Exception:
            pass  # column already exists
    conn.commit()
    return conn


def save_gate_run(conn, gate: dict) -> int:
    """Persist a gate computation result, one row per UTC date (upsert). Return gate_id."""
    run_at = datetime.now(timezone.utc).isoformat()
    today_utc = datetime.now(timezone.utc).date().isoformat()
    c = gate.get("components", {})
    cursor = conn.cursor()
    cursor.execute("SELECT gate_id FROM gate_runs WHERE date(run_at) = ?", (today_utc,))
    existing = cursor.fetchone()
    values = (
        run_at, gate["score"], gate["sizing"], gate["label"],
        c.get("vix_level"), c.get("vix_term_structure"),
        c.get("breadth"), c.get("credit_spread"),
        c.get("put_call"), c.get("factor_crowding"),
    )
    if existing:
        cursor.execute(
            """UPDATE gate_runs SET
               run_at=?, composite_score=?, sizing=?, label=?,
               vix_level=?, vix_term_structure=?, breadth=?,
               credit_spread=?, put_call=?, factor_crowding=?
               WHERE gate_id=?""",
            (*values, existing[0]),
        )
        conn.commit()
        return existing[0]
    cursor.execute(
        """INSERT INTO gate_runs
           (run_at, composite_score, sizing, label,
            vix_level, vix_term_structure, breadth, credit_spread, put_call, factor_crowding)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        values,
    )
    conn.commit()
    return cursor.lastrowid


def save_reviews(conn, scan_id: int, reviews_df) -> None:
    """Insert Claude review results into the reviews table."""
    run_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    for _, row in reviews_df.iterrows():
        cursor.execute(
            """INSERT INTO reviews
               (scan_id, run_at, symbol, quant_score, claude_score, blended_score,
                red_flags_json, claude_summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scan_id,
                run_at,
                row.get("symbol"),
                row.get("quant_score"),
                row.get("claude_score"),
                row.get("blended_score"),
                row.get("red_flags_json"),
                row.get("claude_summary"),
            ),
        )
    conn.commit()


def save_recommendations(conn, scan_id: int, recs: list[dict]) -> int:
    """Persist recommendation batch; upsert by UTC date + rank. Return batch_id."""
    created_at = datetime.now(timezone.utc).isoformat()
    today_utc = datetime.now(timezone.utc).date().isoformat()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT batch_id FROM recommendations WHERE date(created_at) = ? LIMIT 1",
        (today_utc,),
    )
    existing_batch = cursor.fetchone()
    batch_id = existing_batch[0] if existing_batch else (
        (cursor.execute(
            "SELECT COALESCE(MAX(batch_id), 0) + 1 FROM recommendations"
        ) or cursor) and cursor.fetchone()[0]
    )

    for rec in recs:
        cursor.execute(
            "SELECT rec_id FROM recommendations WHERE date(created_at) = ? AND rank = ?",
            (today_utc, rec["rank"]),
        )
        existing = cursor.fetchone()
        values = (
            batch_id, created_at, scan_id,
            rec.get("review_id"), rec["rank"], rec["symbol"],
            rec.get("blended_score"), rec["sizing_pct"], rec["gate_sizing"],
            rec.get("rationale"), rec.get("risks_json"), rec.get("exit_triggers_json"),
            rec.get("entry_zone"),
            1 if rec.get("is_synthesized") else 0,
            rec.get("cache_hit"),
            rec.get("price_at_scan"),
            rec.get("price_session", ""),
            rec.get("entry_low"),
            rec.get("entry_high"),
            rec.get("support"),
            rec.get("stop_price"),
            rec.get("target"),
        )
        if existing:
            cursor.execute(
                """UPDATE recommendations SET
                   batch_id=?, created_at=?, scan_id=?, review_id=?, rank=?, symbol=?,
                   blended_score=?, sizing_pct=?, gate_sizing=?, rationale=?,
                   risks_json=?, exit_triggers_json=?, entry_zone=?, is_synthesized=?,
                   cache_hit=?, price_at_scan=?, price_session=?,
                   entry_low=?, entry_high=?, support=?, stop_price=?, target=?
                   WHERE rec_id=?""",
                (*values, existing[0]),
            )
        else:
            cursor.execute(
                """INSERT INTO recommendations
                   (batch_id, created_at, scan_id, review_id, rank, symbol,
                    blended_score, sizing_pct, gate_sizing, rationale,
                    risks_json, exit_triggers_json, entry_zone, is_synthesized,
                    cache_hit, price_at_scan, price_session,
                    entry_low, entry_high, support, stop_price, target)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
    conn.commit()
    return batch_id


def load_latest_recommendations(conn) -> list[dict]:
    """Return today's recommendations ordered by rank, or empty list."""
    today_utc = datetime.now(timezone.utc).date().isoformat()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT r.rec_id, r.batch_id, r.created_at, r.scan_id, r.review_id, r.rank, r.symbol,
                  r.blended_score, r.sizing_pct, r.gate_sizing, r.rationale, r.risks_json,
                  r.exit_triggers_json, r.entry_zone, r.is_synthesized, r.cache_hit,
                  r.price_at_scan, r.price_session,
                  r.entry_low, r.entry_high, r.support, r.stop_price, r.target,
                  rv.claude_summary
           FROM recommendations r
           LEFT JOIN reviews rv ON r.review_id = rv.review_id
           WHERE date(r.created_at) = ?
           ORDER BY r.rank""",
        (today_utc,),
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def save_trade_outcome(conn, trade_id: int, outcome: dict) -> int:
    """Upsert a trade outcome row. Returns outcome_id."""
    created_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute("SELECT outcome_id FROM trade_outcomes WHERE trade_id = ?", (trade_id,))
    existing = cursor.fetchone()
    values = (
        trade_id, created_at,
        outcome["thesis_validated"], outcome["exit_driver"],
        outcome.get("red_flags_materialized_json"),
        outcome.get("exit_triggers_fired_json"),
        outcome.get("macro_aligned"),
        outcome.get("notes"),
    )
    if existing:
        cursor.execute(
            """UPDATE trade_outcomes SET
               trade_id=?, created_at=?, thesis_validated=?, exit_driver=?,
               red_flags_materialized_json=?, exit_triggers_fired_json=?,
               macro_aligned=?, notes=?
               WHERE outcome_id=?""",
            (*values, existing[0]),
        )
        conn.commit()
        return existing[0]
    cursor.execute(
        """INSERT INTO trade_outcomes
           (trade_id, created_at, thesis_validated, exit_driver,
            red_flags_materialized_json, exit_triggers_fired_json, macro_aligned, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        values,
    )
    conn.commit()
    return cursor.lastrowid


def load_trade_outcome(conn, trade_id: int) -> dict | None:
    """Return the outcome row for a trade, or None."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trade_outcomes WHERE trade_id = ?", (trade_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def load_trades_with_context(conn, limit: int = 30) -> list[dict]:
    """Return closed trades joined with outcomes and rec metadata, newest first."""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT
               t.trade_id, t.opened_at, t.closed_at, t.symbol, t.shares,
               t.entry_price, t.exit_price, t.pnl, t.pnl_pct, t.exit_reason,
               t.thesis_text, t.rec_id,
               r.batch_id, r.blended_score, r.gate_sizing, r.risks_json,
               r.exit_triggers_json as rec_exit_triggers_json,
               o.thesis_validated, o.exit_driver,
               o.red_flags_materialized_json, o.exit_triggers_fired_json,
               o.macro_aligned, o.notes
           FROM trades t
           LEFT JOIN recommendations r ON t.rec_id = r.rec_id
           LEFT JOIN trade_outcomes o ON t.trade_id = o.trade_id
           WHERE t.exit_price IS NOT NULL
           ORDER BY t.trade_id DESC
           LIMIT ?""",
        (limit,),
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def save_postmortem(conn, trade_count: int, outcome_count: int,
                    summary: str, model: str, cache_hit: int | None) -> int:
    """Insert a postmortem run. Returns postmortem_id."""
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO postmortems
           (run_at, trade_count, outcome_count, summary_text, model, cache_hit)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (datetime.now(timezone.utc).isoformat(), trade_count, outcome_count,
         summary, model, cache_hit),
    )
    conn.commit()
    return cursor.lastrowid


def load_latest_postmortem(conn) -> dict | None:
    """Return the most recent postmortem row, or None."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM postmortems ORDER BY postmortem_id DESC LIMIT 1"
    )
    row = cursor.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def save_analyst_session(conn, session_id: str, title: str,
                          messages: list, snapshot: dict | None = None) -> None:
    """Upsert a chat session. messages and snapshot are stored as JSON."""
    import json as _json
    saved_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO analyst_sessions
           (session_id, saved_at, title, messages_json, snapshot_json)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, saved_at, title,
         _json.dumps(messages),
         _json.dumps(snapshot) if snapshot is not None else None),
    )
    conn.commit()


def load_analyst_sessions(conn) -> list[dict]:
    """Return all saved sessions ordered newest-first, without messages/snapshot."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT session_id, saved_at, title FROM analyst_sessions ORDER BY saved_at DESC"
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def delete_analyst_session(conn, session_id: str) -> None:
    """Remove a saved analyst session by ID."""
    conn.execute("DELETE FROM analyst_sessions WHERE session_id = ?", (session_id,))
    conn.commit()


def load_analyst_session(conn, session_id: str) -> dict | None:
    """Return full session row (including messages_json) or None."""
    import json as _json
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analyst_sessions WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    result = dict(zip(cols, row))
    result["messages"] = _json.loads(result["messages_json"])
    result["snapshot"] = _json.loads(result["snapshot_json"]) if result["snapshot_json"] else None
    return result


def save_scan(conn, gate_score, sizing, picks_df) -> int:
    """Insert scan + picks. Return scan_id."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO scans (run_at, gate_score, sizing) VALUES (?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), gate_score, sizing),
    )
    scan_id = cursor.lastrowid

    for _, row in picks_df.iterrows():
        cursor.execute(
            """INSERT INTO scan_picks (scan_id, symbol, sector, momentum, rank_score)
               VALUES (?, ?, ?, ?, ?)""",
            (
                scan_id,
                row.get("symbol"),
                row.get("sector"),
                row.get("momentum"),
                row.get("score"),
            ),
        )

    conn.commit()
    return scan_id
