# Robinhood Broker Foundation + Real Account Visibility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Swing Lab a read-only Robinhood client that imports real fills into the trade log (matched to recommendations) and feeds real positions into rebalance — the data foundation for the learning loop.

**Architecture:** A thin `robin_stocks` I/O wrapper (`broker.py`) is kept strictly separate from three PURE logic modules (`reconstruction.py`, `rec_match.py`, `reconcile.py`) that take plain dicts and are unit-tested with fixtures (no mocking). A `sync.py` orchestrator wires broker → pure logic → `db.py`, owning a single transaction. Credentials live only in Windows Credential Manager via `keyring`. Two new CLI commands: `broker-login` (one-time) and `sync`.

**Tech Stack:** Python 3.11+, `uv`, SQLite, `robin_stocks` (Robinhood API), `keyring` (Windows Credential Manager), `pyotp` (TOTP 2FA), `pytest` (new — no test suite exists yet).

**Spec:** `docs/superpowers/specs/2026-06-15-robinhood-broker-foundation-design.md`

---

## File Structure

| File | Responsibility | New? |
|------|----------------|------|
| `pyproject.toml` | Add `robin_stocks`, `keyring`, `pyotp` deps; `pytest` dev dep; pytest config | modify |
| `tests/conftest.py` | `db_conn` fixture (in-memory-ish temp SQLite seeded by `init_db()`) | create |
| `tests/test_smoke.py` | Confirms pytest + fixture wiring works | create |
| `src/swing_lab/config.py` | `BROKER`, `SYNC_LOOKBACK_DAYS`, `REC_MATCH_WINDOW_DAYS`, `KEYRING_SERVICE`; keyring credential helpers | modify |
| `src/swing_lab/db.py` | New `positions` + `account_snapshots` tables; `trades` migrations; broker sync DB helpers (no internal commit) | modify |
| `src/swing_lab/reconstruction.py` | PURE: collapse fill stream → position-episodes | create |
| `src/swing_lab/rec_match.py` | PURE: trading-day window match episode → rec | create |
| `src/swing_lab/reconcile.py` | PURE: compare open episodes vs positions snapshot → warnings | create |
| `src/swing_lab/broker.py` | `RobinhoodClient` — only place that calls `robin_stocks` | create |
| `src/swing_lab/sync.py` | Orchestrator: pull → reconstruct → match → persist (one transaction) | create |
| `src/swing_lab/cli.py` | `broker-login` + `sync` subcommands; real positions in `_cmd_rebalance` | modify |

**Key design rules locked here:**
- **Episode identity = the opening (first buy) `order_id`.** Reconstruction is deterministic and the opening fill never changes, so this is a stable idempotency key across re-syncs.
- **Broker sync DB helpers do NOT call `conn.commit()`.** The orchestrator wraps the whole sync in `with conn:` so it is atomic and rolls back on error. (Existing helpers like `save_trade_outcome` commit internally; the new ones deliberately do not.)
- **`robin_stocks` is the ONLY dependency touched inside `broker.py`.** Everything else is pure or DB. Tests mock `swing_lab.broker.rh`.

> **⚠️ Knowledge-cutoff note for the engineer:** Exact `robin_stocks` function names (e.g. `build_holdings`, `get_all_stock_orders`, `load_phoenix_account`, `get_symbol_by_url`) are past the plan author's knowledge cutoff and MUST be verified against the installed pinned version during Task 8. They are isolated to `broker.py` and fully mocked in tests, so the rest of the plan is unaffected by their exact spelling.

---

## Task 1: Dependencies + test bootstrap

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Add runtime + dev dependencies and pytest config**

In `pyproject.toml`, add the three runtime deps to the `dependencies` list (after the `tzdata` line, before the closing `]`):

```toml
    "robin_stocks>=3.0",
    "keyring>=24.0",
    "pyotp>=2.9",
```

Replace the empty dev group and add pytest config:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Sync the environment**

Run: `uv sync`
Expected: resolves and installs `robin_stocks`, `keyring`, `pyotp`, `pytest` with no errors.

- [ ] **Step 3: Write the shared DB fixture**

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures for Swing Lab tests."""
import pytest


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    """An isolated swing.db seeded by the real init_db() schema."""
    db_file = tmp_path / "swing.db"
    # init_db() binds DB_PATH at import time into the swing_lab.db namespace,
    # so patch it there (patching config.DB_PATH would not take effect).
    monkeypatch.setattr("swing_lab.db.DB_PATH", db_file)
    from swing_lab.db import init_db
    conn = init_db()
    yield conn
    conn.close()
```

- [ ] **Step 4: Write a smoke test**

Create `tests/test_smoke.py`:

```python
def test_db_fixture_creates_trades_table(db_conn):
    cur = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='trades'"
    )
    assert cur.fetchone() is not None
```

- [ ] **Step 5: Run the smoke test**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/conftest.py tests/test_smoke.py
git commit -m "build: add robin_stocks/keyring/pyotp + bootstrap pytest suite"
```

---

## Task 2: Config — broker constants + keyring credential helpers

**Files:**
- Modify: `src/swing_lab/config.py`
- Test: `tests/test_config_credentials.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_credentials.py`:

```python
import pytest


def test_store_then_get_round_trips(monkeypatch):
    store = {}
    monkeypatch.setattr(
        "keyring.set_password",
        lambda service, key, val: store.__setitem__((service, key), val),
    )
    monkeypatch.setattr(
        "keyring.get_password",
        lambda service, key: store.get((service, key)),
    )
    from swing_lab import config
    config.store_broker_credentials("user@example.com", "pw123", "SEED456")
    creds = config.get_broker_credentials()
    assert creds == {
        "username": "user@example.com",
        "password": "pw123",
        "totp_seed": "SEED456",
    }


def test_get_missing_credentials_raises_actionable_error(monkeypatch):
    monkeypatch.setattr("keyring.get_password", lambda service, key: None)
    from swing_lab import config
    with pytest.raises(RuntimeError, match="broker-login"):
        config.get_broker_credentials()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_config_credentials.py -v`
Expected: FAIL with `AttributeError: module 'swing_lab.config' has no attribute 'store_broker_credentials'`.

- [ ] **Step 3: Add constants + credential helpers**

In `src/swing_lab/config.py`, add after the `POSTMORTEM_TRADE_LIMIT = 30` block (around line 42):

```python
# Broker integration (Robinhood)
BROKER = "robinhood"
KEYRING_SERVICE = "swing_lab_robinhood"
SYNC_LOOKBACK_DAYS = 90        # how far back `sync` pulls filled orders
REC_MATCH_WINDOW_DAYS = 5      # trading-day window to link a trade to a recommendation
```

Add at the end of the file, after `get_api_key()`:

```python
_CRED_KEYS = ("username", "password", "totp_seed")


def store_broker_credentials(username: str, password: str, totp_seed: str) -> None:
    """Persist Robinhood credentials to the OS keyring (Windows Credential Manager)."""
    import keyring
    values = {"username": username, "password": password, "totp_seed": totp_seed}
    for key in _CRED_KEYS:
        keyring.set_password(KEYRING_SERVICE, key, values[key])


def get_broker_credentials() -> dict:
    """Return {username, password, totp_seed} from the keyring, or raise if unset."""
    import keyring
    creds = {key: keyring.get_password(KEYRING_SERVICE, key) for key in _CRED_KEYS}
    if not all(creds.values()):
        raise RuntimeError(
            "Robinhood credentials not found. Run `swing-lab broker-login` first."
        )
    return creds
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_config_credentials.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/config.py tests/test_config_credentials.py
git commit -m "feat: broker config constants + keyring credential helpers"
```

---

## Task 3: Schema — new tables + `trades` migrations

**Files:**
- Modify: `src/swing_lab/db.py:11-118` (the `executescript` block) and `db.py:120-136` (the migration list)
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_schema.py`:

```python
def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_trades_has_broker_columns(db_conn):
    cols = _columns(db_conn, "trades")
    assert {"broker", "broker_order_ids_json", "source", "mode", "fees"} <= cols


def test_trades_mode_defaults_to_live(db_conn):
    db_conn.execute(
        "INSERT INTO trades (opened_at, symbol, side, shares, entry_price) "
        "VALUES ('2026-06-01T00:00:00+00:00', 'AAPL', 'long', 10, 150.0)"
    )
    row = db_conn.execute("SELECT mode FROM trades").fetchone()
    assert row[0] == "live"


def test_positions_table_exists_with_unique_constraint(db_conn):
    cols = _columns(db_conn, "positions")
    assert {"symbol", "quantity", "average_buy_price", "market_value",
            "last_price", "broker", "synced_at"} <= cols
    db_conn.execute(
        "INSERT INTO positions (synced_at, broker, symbol, quantity) "
        "VALUES ('t', 'robinhood', 'AAPL', 5)"
    )
    # UNIQUE(broker, symbol) — second insert of same pair must fail
    import sqlite3
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            "INSERT INTO positions (synced_at, broker, symbol, quantity) "
            "VALUES ('t2', 'robinhood', 'AAPL', 7)"
        )


def test_account_snapshots_table_exists(db_conn):
    cols = _columns(db_conn, "account_snapshots")
    assert {"snapshot_id", "synced_at", "broker", "total_equity",
            "buying_power", "cash"} <= cols
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL (`positions` / `account_snapshots` tables and `trades` broker columns do not exist).

- [ ] **Step 3: Add the two new tables to the `executescript` block**

In `src/swing_lab/db.py`, inside the `conn.executescript("""...""")` call, add these two `CREATE TABLE` statements immediately before the closing `"""` (after the `analyst_sessions` table, around line 117):

```sql
        CREATE TABLE IF NOT EXISTS positions (
            position_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            synced_at          TEXT    NOT NULL,
            broker             TEXT    NOT NULL,
            symbol             TEXT    NOT NULL,
            quantity           REAL    NOT NULL,
            average_buy_price  REAL,
            market_value       REAL,
            last_price         REAL,
            UNIQUE(broker, symbol)
        );
        CREATE TABLE IF NOT EXISTS account_snapshots (
            snapshot_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            synced_at     TEXT    NOT NULL,
            broker        TEXT    NOT NULL,
            total_equity  REAL,
            buying_power  REAL,
            cash          REAL
        );
```

- [ ] **Step 4: Add the `trades` column migrations**

In `src/swing_lab/db.py`, append these entries to the migration list (the `for migration in [ ... ]:` block, after the last `target REAL` entry around line 130):

```python
        "ALTER TABLE trades ADD COLUMN broker TEXT",
        "ALTER TABLE trades ADD COLUMN broker_order_ids_json TEXT",
        "ALTER TABLE trades ADD COLUMN source TEXT",
        "ALTER TABLE trades ADD COLUMN mode TEXT DEFAULT 'live'",
        "ALTER TABLE trades ADD COLUMN fees REAL",
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/swing_lab/db.py tests/test_schema.py
git commit -m "feat: positions/account_snapshots tables + trades broker columns"
```

---

## Task 4: DB helpers — positions + account snapshot (no internal commit)

**Files:**
- Modify: `src/swing_lab/db.py` (append functions)
- Test: `tests/test_db_positions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_positions.py`:

```python
def test_replace_positions_upserts_and_removes_sold(db_conn):
    from swing_lab.db import replace_positions, load_positions
    first = [
        {"symbol": "AAPL", "quantity": 10, "average_buy_price": 150.0,
         "market_value": 1600.0, "last_price": 160.0},
        {"symbol": "MSFT", "quantity": 5, "average_buy_price": 300.0,
         "market_value": 1550.0, "last_price": 310.0},
    ]
    replace_positions(db_conn, "robinhood", first)
    db_conn.commit()
    held = {p["symbol"]: p["quantity"] for p in load_positions(db_conn, "robinhood")}
    assert held == {"AAPL": 10, "MSFT": 5}

    # Second sync: MSFT sold out, AAPL changed -> snapshot fully replaced
    second = [{"symbol": "AAPL", "quantity": 8, "average_buy_price": 150.0,
               "market_value": 1280.0, "last_price": 160.0}]
    replace_positions(db_conn, "robinhood", second)
    db_conn.commit()
    held = {p["symbol"]: p["quantity"] for p in load_positions(db_conn, "robinhood")}
    assert held == {"AAPL": 8}


def test_replace_positions_does_not_commit(db_conn):
    from swing_lab.db import replace_positions
    replace_positions(db_conn, "robinhood",
                      [{"symbol": "AAPL", "quantity": 1, "average_buy_price": 1.0,
                        "market_value": 1.0, "last_price": 1.0}])
    db_conn.rollback()  # uncommitted -> rollback must wipe it
    rows = db_conn.execute("SELECT COUNT(*) FROM positions").fetchone()
    assert rows[0] == 0


def test_save_account_snapshot(db_conn):
    from swing_lab.db import save_account_snapshot
    save_account_snapshot(db_conn, "robinhood",
                          {"total_equity": 5000.0, "buying_power": 1200.0, "cash": 300.0})
    db_conn.commit()
    row = db_conn.execute(
        "SELECT total_equity, buying_power, cash FROM account_snapshots"
    ).fetchone()
    assert row == (5000.0, 1200.0, 300.0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_db_positions.py -v`
Expected: FAIL (`ImportError: cannot import name 'replace_positions'`).

- [ ] **Step 3: Implement the helpers**

Append to `src/swing_lab/db.py`:

```python
def replace_positions(conn, broker: str, positions: list[dict]) -> None:
    """Replace the entire positions snapshot for a broker. Does NOT commit."""
    synced_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM positions WHERE broker = ?", (broker,))
    for p in positions:
        cursor.execute(
            """INSERT INTO positions
               (synced_at, broker, symbol, quantity, average_buy_price,
                market_value, last_price)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (synced_at, broker, p["symbol"], p["quantity"],
             p.get("average_buy_price"), p.get("market_value"), p.get("last_price")),
        )


def load_positions(conn, broker: str) -> list[dict]:
    """Return the current positions snapshot for a broker."""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT symbol, quantity, average_buy_price, market_value, last_price
           FROM positions WHERE broker = ? ORDER BY symbol""",
        (broker,),
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def save_account_snapshot(conn, broker: str, snap: dict) -> None:
    """Append an account snapshot row. Does NOT commit."""
    synced_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO account_snapshots
           (synced_at, broker, total_equity, buying_power, cash)
           VALUES (?, ?, ?, ?, ?)""",
        (synced_at, broker, snap.get("total_equity"),
         snap.get("buying_power"), snap.get("cash")),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_db_positions.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/db.py tests/test_db_positions.py
git commit -m "feat: positions snapshot + account snapshot DB helpers"
```

---

## Task 5: DB helpers — broker trade episodes + rec lookup (no internal commit)

**Files:**
- Modify: `src/swing_lab/db.py` (append functions)
- Test: `tests/test_db_trades_broker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_trades_broker.py`:

```python
import json

OPEN_EPISODE = {
    "symbol": "AAPL", "opened_at": "2026-06-01T14:30:00+00:00",
    "closed_at": None, "shares": 10.0, "entry_price": 150.0,
    "exit_price": None, "fees": 0.05, "pnl": None, "pnl_pct": None,
    "broker_order_ids": ["ord-open-1"], "opening_order_id": "ord-open-1",
}
CLOSED_EPISODE = {
    "symbol": "AAPL", "opened_at": "2026-06-01T14:30:00+00:00",
    "closed_at": "2026-06-05T18:00:00+00:00", "shares": 10.0, "entry_price": 150.0,
    "exit_price": 165.0, "fees": 0.10, "pnl": 149.90, "pnl_pct": 0.0999,
    "broker_order_ids": ["ord-open-1", "ord-close-1"], "opening_order_id": "ord-open-1",
}


def test_insert_broker_episode_open(db_conn):
    from swing_lab.db import insert_broker_episode
    trade_id = insert_broker_episode(db_conn, "robinhood", OPEN_EPISODE, rec_id=None)
    db_conn.commit()
    row = db_conn.execute(
        "SELECT symbol, shares, entry_price, exit_price, source, broker, mode, "
        "broker_order_ids_json FROM trades WHERE trade_id = ?", (trade_id,)
    ).fetchone()
    assert row[0] == "AAPL" and row[3] is None  # exit_price NULL -> open
    assert row[4] == "broker" and row[5] == "robinhood" and row[6] == "live"
    assert json.loads(row[7]) == ["ord-open-1"]


def test_find_trade_by_opening_order(db_conn):
    from swing_lab.db import insert_broker_episode, find_trade_by_opening_order
    tid = insert_broker_episode(db_conn, "robinhood", OPEN_EPISODE, rec_id=None)
    db_conn.commit()
    found = find_trade_by_opening_order(db_conn, "robinhood", "ord-open-1")
    assert found["trade_id"] == tid and found["exit_price"] is None
    assert find_trade_by_opening_order(db_conn, "robinhood", "nope") is None


def test_update_trade_close_from_broker(db_conn):
    from swing_lab.db import insert_broker_episode, update_trade_close_from_broker
    tid = insert_broker_episode(db_conn, "robinhood", OPEN_EPISODE, rec_id=None)
    update_trade_close_from_broker(db_conn, tid, CLOSED_EPISODE)
    db_conn.commit()
    row = db_conn.execute(
        "SELECT exit_price, closed_at, pnl, fees, broker_order_ids_json "
        "FROM trades WHERE trade_id = ?", (tid,)
    ).fetchone()
    assert row[0] == 165.0 and row[1] is not None
    assert json.loads(row[4]) == ["ord-open-1", "ord-close-1"]


def test_load_recent_recs_for_symbol(db_conn):
    from swing_lab.db import load_recent_recs_for_symbol
    db_conn.execute(
        "INSERT INTO recommendations (rec_id, batch_id, created_at, scan_id, rank, "
        "symbol, sizing_pct, gate_sizing) VALUES "
        "(1, 1, '2026-06-01T00:00:00+00:00', 1, 1, 'AAPL', 5.0, 1.0)"
    )
    db_conn.execute(
        "INSERT INTO recommendations (rec_id, batch_id, created_at, scan_id, rank, "
        "symbol, sizing_pct, gate_sizing) VALUES "
        "(2, 2, '2026-06-03T00:00:00+00:00', 2, 1, 'MSFT', 5.0, 1.0)"
    )
    db_conn.commit()
    recs = load_recent_recs_for_symbol(db_conn, "AAPL")
    assert [r["rec_id"] for r in recs] == [1]
    assert recs[0]["created_at"] == "2026-06-01T00:00:00+00:00"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_db_trades_broker.py -v`
Expected: FAIL (`ImportError: cannot import name 'insert_broker_episode'`).

- [ ] **Step 3: Implement the helpers**

Append to `src/swing_lab/db.py` (add `import json` near the existing imports at the top if not already present — it is currently imported lazily inside functions, so add a module-level `import json` after `import sqlite3`):

```python
def insert_broker_episode(conn, broker: str, episode: dict, rec_id: int | None) -> int:
    """Insert a reconstructed position-episode as a trades row. Does NOT commit.
    Returns trade_id. Open episodes leave exit_price/closed_at/pnl NULL.
    """
    import json
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO trades
           (opened_at, closed_at, symbol, side, shares, entry_price, exit_price,
            rec_id, thesis_text, exit_reason, pnl, pnl_pct,
            broker, broker_order_ids_json, source, mode, fees)
           VALUES (?, ?, ?, 'long', ?, ?, ?, ?, NULL, NULL, ?, ?,
                   ?, ?, 'broker', 'live', ?)""",
        (episode["opened_at"], episode["closed_at"], episode["symbol"],
         episode["shares"], episode["entry_price"], episode["exit_price"],
         rec_id, episode["pnl"], episode["pnl_pct"],
         broker, json.dumps(episode["broker_order_ids"]), episode["fees"]),
    )
    return cursor.lastrowid


def update_trade_close_from_broker(conn, trade_id: int, episode: dict) -> None:
    """Update a previously-open broker trade with its close data. Does NOT commit."""
    import json
    conn.execute(
        """UPDATE trades SET
           closed_at = ?, exit_price = ?, pnl = ?, pnl_pct = ?, fees = ?,
           broker_order_ids_json = ?
           WHERE trade_id = ?""",
        (episode["closed_at"], episode["exit_price"], episode["pnl"],
         episode["pnl_pct"], episode["fees"],
         json.dumps(episode["broker_order_ids"]), trade_id),
    )


def find_trade_by_opening_order(conn, broker: str, opening_order_id: str) -> dict | None:
    """Find the trade whose episode opened with this order_id, or None."""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT trade_id, exit_price FROM trades
           WHERE broker = ? AND broker_order_ids_json LIKE ?""",
        (broker, f'%"{opening_order_id}"%'),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {"trade_id": row[0], "exit_price": row[1]}


def load_recent_recs_for_symbol(conn, symbol: str, lookback_days: int = 60) -> list[dict]:
    """Return recent recommendations for a symbol (newest first) for trade matching."""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT rec_id, created_at FROM recommendations
           WHERE symbol = ?
           ORDER BY created_at DESC
           LIMIT 50""",
        (symbol,),
    )
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]
```

> Note: `lookback_days` is accepted for forward-compatibility but the query simply returns the 50 most recent recs for the symbol; the trading-day window is enforced purely in `rec_match.find_matching_rec` (Task 7), keeping the date math testable without DB.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_db_trades_broker.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/db.py tests/test_db_trades_broker.py
git commit -m "feat: broker episode insert/update + opening-order lookup + rec lookup"
```

---

## Task 6: Reconstruction (PURE) — fills → position-episodes

This is the only genuinely new algorithm. No DB, no `robin_stocks`, no mocking — just dicts in, dicts out.

**Fill dict contract** (what `broker.py` produces and this module consumes):
```python
{"symbol": "AAPL", "side": "buy"|"sell", "shares": 10.0, "price": 150.0,
 "fees": 0.03, "filled_at": "2026-06-01T14:30:00+00:00", "order_id": "ord-1"}
```

**Episode dict contract** (what this module produces — matches the DB helpers in Task 5):
```python
{"symbol", "opened_at", "closed_at"(None if open), "shares", "entry_price",
 "exit_price"(None if open), "fees", "pnl"(None if open), "pnl_pct"(None if open),
 "broker_order_ids"(list), "opening_order_id"(str)}
```

**Assumptions (long-only):** positions only go from flat → long → flat; net share count never goes negative. An episode spans from the first buy that lifts net shares above zero until the net returns to zero (within `EPSILON = 1e-6`). A subsequent buy starts a new episode.

**Files:**
- Create: `src/swing_lab/reconstruction.py`
- Test: `tests/test_reconstruction.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reconstruction.py`:

```python
from swing_lab.reconstruction import reconstruct_episodes


def _fill(symbol, side, shares, price, day, order_id, fees=0.0):
    return {"symbol": symbol, "side": side, "shares": shares, "price": price,
            "fees": fees, "filled_at": f"2026-06-{day:02d}T14:30:00+00:00",
            "order_id": order_id}


def test_simple_round_trip():
    fills = [
        _fill("AAPL", "buy", 10, 150.0, 1, "o1", fees=0.01),
        _fill("AAPL", "sell", 10, 165.0, 5, "o2", fees=0.02),
    ]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 1
    ep = eps[0]
    assert ep["symbol"] == "AAPL"
    assert ep["shares"] == 10
    assert ep["entry_price"] == 150.0
    assert ep["exit_price"] == 165.0
    assert ep["opening_order_id"] == "o1"
    assert ep["broker_order_ids"] == ["o1", "o2"]
    assert round(ep["fees"], 4) == 0.03
    # pnl = 10*165 - 10*150 - fees(0.03) = 149.97
    assert round(ep["pnl"], 2) == 149.97
    assert round(ep["pnl_pct"], 5) == round(149.97 / 1500.0, 5)
    assert ep["opened_at"].startswith("2026-06-01")
    assert ep["closed_at"].startswith("2026-06-05")


def test_scale_in_averages_entry():
    fills = [
        _fill("AAPL", "buy", 10, 100.0, 1, "o1"),
        _fill("AAPL", "buy", 30, 120.0, 2, "o2"),  # weighted avg = 115
        _fill("AAPL", "sell", 40, 130.0, 5, "o3"),
    ]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 1
    assert eps[0]["shares"] == 40
    assert eps[0]["entry_price"] == 115.0
    assert eps[0]["opening_order_id"] == "o1"


def test_partial_then_full_close_is_one_episode():
    fills = [
        _fill("AAPL", "buy", 10, 100.0, 1, "o1"),
        _fill("AAPL", "sell", 4, 110.0, 3, "o2"),   # partial, still net 6
        _fill("AAPL", "sell", 6, 120.0, 5, "o3"),   # flat -> closes
    ]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 1
    ep = eps[0]
    assert ep["shares"] == 10
    # exit avg = (4*110 + 6*120) / 10 = 116
    assert ep["exit_price"] == 116.0
    assert ep["closed_at"] is not None


def test_still_open_position():
    fills = [_fill("AAPL", "buy", 10, 150.0, 1, "o1")]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 1
    ep = eps[0]
    assert ep["exit_price"] is None
    assert ep["closed_at"] is None
    assert ep["pnl"] is None
    assert ep["pnl_pct"] is None
    assert ep["shares"] == 10
    assert ep["entry_price"] == 150.0


def test_back_to_back_episodes_same_symbol():
    fills = [
        _fill("AAPL", "buy", 10, 100.0, 1, "o1"),
        _fill("AAPL", "sell", 10, 110.0, 3, "o2"),   # closes episode 1
        _fill("AAPL", "buy", 5, 120.0, 6, "o3"),     # opens episode 2
        _fill("AAPL", "sell", 5, 130.0, 8, "o4"),    # closes episode 2
    ]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 2
    assert eps[0]["opening_order_id"] == "o1"
    assert eps[1]["opening_order_id"] == "o3"
    assert eps[1]["entry_price"] == 120.0


def test_multiple_symbols_independent():
    fills = [
        _fill("AAPL", "buy", 10, 100.0, 1, "a1"),
        _fill("MSFT", "buy", 5, 200.0, 1, "m1"),
        _fill("AAPL", "sell", 10, 110.0, 3, "a2"),
    ]
    eps = reconstruct_episodes(fills)
    by_symbol = {e["symbol"]: e for e in eps}
    assert by_symbol["AAPL"]["closed_at"] is not None
    assert by_symbol["MSFT"]["closed_at"] is None


def test_fills_sorted_by_time_regardless_of_input_order():
    fills = [
        _fill("AAPL", "sell", 10, 165.0, 5, "o2"),
        _fill("AAPL", "buy", 10, 150.0, 1, "o1"),
    ]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 1
    assert eps[0]["opening_order_id"] == "o1"
    assert eps[0]["entry_price"] == 150.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_reconstruction.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'swing_lab.reconstruction'`).

- [ ] **Step 3: Implement `reconstruct_episodes`**

Create `src/swing_lab/reconstruction.py`:

```python
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
                if net <= EPSILON and buys:
                    # defensive: should not happen (closed episodes are flushed below)
                    pass
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_reconstruction.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/reconstruction.py tests/test_reconstruction.py
git commit -m "feat: pure fill-stream to position-episode reconstruction"
```

---

## Task 7: Rec matching (PURE) — trading-day window

**Files:**
- Create: `src/swing_lab/rec_match.py`
- Test: `tests/test_rec_match.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rec_match.py`:

```python
from swing_lab.rec_match import trading_days_between, find_matching_rec
from datetime import date


def test_trading_days_between_skips_weekends():
    # Mon 2026-06-01 -> Fri 2026-06-05 = 4 trading days
    assert trading_days_between(date(2026, 6, 1), date(2026, 6, 5)) == 4
    # Fri -> next Mon = 1 trading day (Sat/Sun skipped)
    assert trading_days_between(date(2026, 6, 5), date(2026, 6, 8)) == 1
    # same day = 0
    assert trading_days_between(date(2026, 6, 1), date(2026, 6, 1)) == 0


def test_matches_most_recent_rec_in_window():
    recs = [
        {"rec_id": 1, "created_at": "2026-06-01T00:00:00+00:00"},
        {"rec_id": 2, "created_at": "2026-06-03T00:00:00+00:00"},
    ]
    # opened Fri 2026-06-05; both within 5 trading days -> pick most recent (rec 2)
    assert find_matching_rec("2026-06-05T14:30:00+00:00", recs, 5) == 2


def test_rec_outside_window_not_matched():
    recs = [{"rec_id": 1, "created_at": "2026-06-01T00:00:00+00:00"}]
    # opened 2026-06-12 (Fri) -> 9 trading days after rec -> no match
    assert find_matching_rec("2026-06-12T14:30:00+00:00", recs, 5) is None


def test_rec_created_after_open_not_matched():
    recs = [{"rec_id": 1, "created_at": "2026-06-10T00:00:00+00:00"}]
    assert find_matching_rec("2026-06-05T14:30:00+00:00", recs, 5) is None


def test_no_candidates_returns_none():
    assert find_matching_rec("2026-06-05T14:30:00+00:00", [], 5) is None


def test_handles_z_suffix_timestamps():
    recs = [{"rec_id": 7, "created_at": "2026-06-04T00:00:00Z"}]
    assert find_matching_rec("2026-06-05T14:30:00Z", recs, 5) == 7
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rec_match.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'swing_lab.rec_match'`).

- [ ] **Step 3: Implement the matcher**

Create `src/swing_lab/rec_match.py`:

```python
"""Pure logic: link a trade episode to the recommendation that predicted it.

Trading days are approximated as weekdays (Mon-Fri); market holidays are not
modeled (acceptable for a 5-day matching window). No DB access here.
"""
from datetime import date, datetime, timedelta


def _parse_date(iso: str) -> date:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()


def trading_days_between(start: date, end: date) -> int:
    """Count weekdays strictly after `start` up to and including `end`. 0 if end <= start."""
    if end <= start:
        return 0
    days = 0
    d = start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def find_matching_rec(opened_at_iso: str, candidate_recs: list[dict],
                      window_trading_days: int) -> int | None:
    """Return rec_id of the most recent rec created within the window before the
    episode opened (and not after it), or None."""
    opened = _parse_date(opened_at_iso)
    best = None
    best_created = None
    for rec in candidate_recs:
        created = _parse_date(rec["created_at"])
        if created > opened:
            continue
        if trading_days_between(created, opened) <= window_trading_days:
            if best_created is None or created > best_created:
                best, best_created = rec, created
    return best["rec_id"] if best else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rec_match.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/rec_match.py tests/test_rec_match.py
git commit -m "feat: pure trading-day-window trade-to-recommendation matching"
```

---

## Task 8: Reconciliation (PURE) — open episodes vs snapshot

**Files:**
- Create: `src/swing_lab/reconcile.py`
- Test: `tests/test_reconcile.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reconcile.py`:

```python
from swing_lab.reconcile import reconcile


def test_no_warnings_when_consistent():
    open_eps = [{"symbol": "AAPL", "shares": 10.0}]
    snapshot = [{"symbol": "AAPL", "quantity": 10.0}]
    assert reconcile(open_eps, snapshot) == []


def test_quantity_mismatch_warns():
    open_eps = [{"symbol": "AAPL", "shares": 10.0}]
    snapshot = [{"symbol": "AAPL", "quantity": 8.0}]
    warnings = reconcile(open_eps, snapshot)
    assert len(warnings) == 1 and "AAPL" in warnings[0]


def test_reconstructed_open_missing_from_snapshot_warns():
    open_eps = [{"symbol": "AAPL", "shares": 10.0}]
    warnings = reconcile(open_eps, [])
    assert len(warnings) == 1 and "AAPL" in warnings[0]


def test_snapshot_holding_without_episode_warns():
    snapshot = [{"symbol": "TSLA", "quantity": 3.0}]
    warnings = reconcile([], snapshot)
    assert len(warnings) == 1 and "TSLA" in warnings[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_reconcile.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'swing_lab.reconcile'`).

- [ ] **Step 3: Implement reconcile**

Create `src/swing_lab/reconcile.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_reconcile.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/reconcile.py tests/test_reconcile.py
git commit -m "feat: pure positions-vs-reconstruction reconciliation warnings"
```

---

## Task 9: `broker.py` — `RobinhoodClient` (the only `robin_stocks` caller)

This is the I/O boundary. `robin_stocks` is imported as the module attribute `rh` so tests can replace `swing_lab.broker.rh` with a fake. Every method returns plain data in the contracts the pure modules expect.

> **⚠️ VERIFY FUNCTION NAMES:** During this task, do a one-off interactive login in a Python REPL and confirm the exact `robin_stocks.robinhood` function names and return shapes for your installed version. The names below (`login`, `build_holdings`, `get_all_stock_orders`, `get_symbol_by_url`, `load_phoenix_account`) are the expected ones but MUST be checked. If a name differs, fix it only inside `broker.py` — nothing else depends on it.

**Files:**
- Create: `src/swing_lab/broker.py`
- Test: `tests/test_broker.py`

- [ ] **Step 1: Write the failing tests** (with `rh` fully faked — zero network)

Create `tests/test_broker.py`:

```python
import types
import pytest


def _fake_rh(**overrides):
    """Build a fake robin_stocks.robinhood module surface."""
    mod = types.SimpleNamespace()
    mod.login = overrides.get("login", lambda **kw: {"access_token": "tok"})
    mod.build_holdings = overrides.get("build_holdings", lambda: {})
    mod.get_all_stock_orders = overrides.get("get_all_stock_orders", lambda: [])
    mod.get_symbol_by_url = overrides.get("get_symbol_by_url", lambda url: "AAPL")
    mod.load_phoenix_account = overrides.get(
        "load_phoenix_account",
        lambda: {"total_equity": {"amount": "5000.0"},
                 "account_buying_power": {"amount": "1200.0"},
                 "uninvested_cash": {"amount": "300.0"}},
    )
    return mod


def test_authenticate_missing_credentials_raises(monkeypatch):
    monkeypatch.setattr("keyring.get_password", lambda s, k: None)
    from swing_lab.broker import RobinhoodClient
    client = RobinhoodClient()
    with pytest.raises(RuntimeError, match="broker-login"):
        client.authenticate()


def test_authenticate_passes_totp_code(monkeypatch):
    captured = {}

    def fake_login(**kw):
        captured.update(kw)
        return {"access_token": "tok"}

    monkeypatch.setattr("keyring.get_password",
                        lambda s, k: {"username": "u", "password": "p",
                                      "totp_seed": "JBSWY3DPEHPK3PXP"}[k])
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh", _fake_rh(login=fake_login))
    broker.RobinhoodClient().authenticate()
    assert captured["username"] == "u"
    assert captured["password"] == "p"
    assert captured["mfa_code"].isdigit() and len(captured["mfa_code"]) == 6


def test_get_positions_normalizes_holdings(monkeypatch):
    holdings = {
        "AAPL": {"quantity": "10.0000", "average_buy_price": "150.00",
                 "equity": "1600.00", "price": "160.00"},
    }
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh", _fake_rh(build_holdings=lambda: holdings))
    positions = broker.RobinhoodClient().get_positions()
    assert positions == [{"symbol": "AAPL", "quantity": 10.0,
                          "average_buy_price": 150.0, "market_value": 1600.0,
                          "last_price": 160.0}]


def test_get_filled_orders_filters_and_normalizes(monkeypatch):
    orders = [
        {"state": "filled", "side": "buy", "average_price": "150.00",
         "cumulative_quantity": "10.00000", "fees": "0.03",
         "last_transaction_at": "2026-06-01T14:30:00Z",
         "id": "ord-1", "instrument": "https://api.robinhood.com/instruments/abc/"},
        {"state": "cancelled", "side": "buy", "average_price": None,
         "cumulative_quantity": "0", "fees": "0",
         "last_transaction_at": "2026-06-02T14:30:00Z",
         "id": "ord-2", "instrument": "https://api.robinhood.com/instruments/abc/"},
    ]
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh",
                        _fake_rh(get_all_stock_orders=lambda: orders,
                                 get_symbol_by_url=lambda url: "AAPL"))
    fills = broker.RobinhoodClient().get_filled_orders()
    assert len(fills) == 1
    assert fills[0] == {"symbol": "AAPL", "side": "buy", "shares": 10.0,
                        "price": 150.0, "fees": 0.03,
                        "filled_at": "2026-06-01T14:30:00Z", "order_id": "ord-1"}


def test_get_filled_orders_since_filters_old(monkeypatch):
    orders = [
        {"state": "filled", "side": "buy", "average_price": "100.0",
         "cumulative_quantity": "1", "fees": "0",
         "last_transaction_at": "2026-01-01T00:00:00Z",
         "id": "old", "instrument": "x"},
        {"state": "filled", "side": "buy", "average_price": "100.0",
         "cumulative_quantity": "1", "fees": "0",
         "last_transaction_at": "2026-06-01T00:00:00Z",
         "id": "new", "instrument": "x"},
    ]
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh",
                        _fake_rh(get_all_stock_orders=lambda: orders))
    fills = broker.RobinhoodClient().get_filled_orders(since="2026-05-01T00:00:00Z")
    assert [f["order_id"] for f in fills] == ["new"]


def test_get_account_snapshot_normalizes(monkeypatch):
    from swing_lab import broker
    monkeypatch.setattr(broker, "rh", _fake_rh())
    snap = broker.RobinhoodClient().get_account_snapshot()
    assert snap == {"total_equity": 5000.0, "buying_power": 1200.0, "cash": 300.0}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_broker.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'swing_lab.broker'`).

- [ ] **Step 3: Implement `RobinhoodClient`**

Create `src/swing_lab/broker.py`:

```python
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
        """Log in using keyring credentials + a generated TOTP code.

        robin_stocks caches the session token on disk, so MFA is not re-triggered
        on every run. Raises an actionable error if credentials are missing.
        """
        import pyotp
        creds = get_broker_credentials()  # raises RuntimeError -> "run broker-login"
        mfa_code = pyotp.TOTP(creds["totp_seed"]).now()
        rh.login(
            username=creds["username"],
            password=creds["password"],
            mfa_code=mfa_code,
            store_session=True,
        )
        self._authenticated = True

    def get_positions(self) -> list[dict]:
        """Current holdings -> [{symbol, quantity, average_buy_price, market_value, last_price}]."""
        holdings = rh.build_holdings()
        positions = []
        for symbol, h in holdings.items():
            positions.append({
                "symbol": symbol,
                "quantity": _f(h.get("quantity")),
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
        """Account equity/buying-power/cash -> {total_equity, buying_power, cash}."""
        acct = rh.load_phoenix_account()
        return {
            "total_equity": _f((acct.get("total_equity") or {}).get("amount")),
            "buying_power": _f((acct.get("account_buying_power") or {}).get("amount")),
            "cash": _f((acct.get("uninvested_cash") or {}).get("amount")),
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_broker.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/broker.py tests/test_broker.py
git commit -m "feat: read-only RobinhoodClient wrapping robin_stocks"
```

---

## Task 10: `sync.py` — orchestrator (one transaction, idempotent)

Ties broker → pure logic → DB. Owns the transaction via `with conn:` (the broker DB helpers from Tasks 4–5 deliberately do not commit). Idempotency comes from `find_trade_by_opening_order` keyed on the opening order id.

**Files:**
- Create: `src/swing_lab/sync.py`
- Test: `tests/test_sync.py`

- [ ] **Step 1: Write the failing tests** (with a fake client — no broker, no network)

Create `tests/test_sync.py`:

```python
from swing_lab.sync import sync_account


class FakeClient:
    def __init__(self, positions=None, fills=None, snapshot=None):
        self._positions = positions or []
        self._fills = fills or []
        self._snapshot = snapshot or {"total_equity": 1000.0,
                                      "buying_power": 500.0, "cash": 100.0}

    def get_positions(self):
        return self._positions

    def get_filled_orders(self, since=None):
        return self._fills

    def get_account_snapshot(self):
        return self._snapshot


def _fill(symbol, side, shares, price, day, order_id, fees=0.0):
    return {"symbol": symbol, "side": side, "shares": shares, "price": price,
            "fees": fees, "filled_at": f"2026-06-{day:02d}T14:30:00+00:00",
            "order_id": order_id}


def test_sync_imports_closed_episode(db_conn):
    client = FakeClient(
        positions=[],
        fills=[_fill("AAPL", "buy", 10, 150.0, 1, "o1"),
               _fill("AAPL", "sell", 10, 165.0, 5, "o2")],
    )
    summary = sync_account(db_conn, client, lookback_days=90, match_window_days=5)
    assert summary["inserted"] == 1
    row = db_conn.execute(
        "SELECT symbol, exit_price, source, broker FROM trades"
    ).fetchone()
    assert row == ("AAPL", 165.0, "broker", "robinhood")


def test_sync_is_idempotent(db_conn):
    fills = [_fill("AAPL", "buy", 10, 150.0, 1, "o1"),
             _fill("AAPL", "sell", 10, 165.0, 5, "o2")]
    client = FakeClient(fills=fills)
    sync_account(db_conn, client, 90, 5)
    summary2 = sync_account(db_conn, client, 90, 5)
    assert summary2["inserted"] == 0
    assert summary2["skipped"] == 1
    count = db_conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    assert count == 1


def test_sync_updates_open_then_closed(db_conn):
    # First sync: only a buy -> open trade
    client1 = FakeClient(
        positions=[{"symbol": "AAPL", "quantity": 10.0, "average_buy_price": 150.0,
                    "market_value": 1500.0, "last_price": 150.0}],
        fills=[_fill("AAPL", "buy", 10, 150.0, 1, "o1")],
    )
    sync_account(db_conn, client1, 90, 5)
    assert db_conn.execute(
        "SELECT exit_price FROM trades").fetchone()[0] is None

    # Second sync: the sell appears -> same trade closes
    client2 = FakeClient(
        positions=[],
        fills=[_fill("AAPL", "buy", 10, 150.0, 1, "o1"),
               _fill("AAPL", "sell", 10, 165.0, 5, "o2")],
    )
    summary = sync_account(db_conn, client2, 90, 5)
    assert summary["updated"] == 1
    count = db_conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    assert count == 1
    assert db_conn.execute("SELECT exit_price FROM trades").fetchone()[0] == 165.0


def test_sync_matches_recommendation(db_conn):
    db_conn.execute(
        "INSERT INTO recommendations (rec_id, batch_id, created_at, scan_id, rank, "
        "symbol, sizing_pct, gate_sizing) VALUES "
        "(42, 1, '2026-06-01T00:00:00+00:00', 1, 1, 'AAPL', 5.0, 1.0)"
    )
    db_conn.commit()
    client = FakeClient(
        fills=[_fill("AAPL", "buy", 10, 150.0, 3, "o1"),   # opened within 5 td of rec
               _fill("AAPL", "sell", 10, 165.0, 5, "o2")],
    )
    sync_account(db_conn, client, 90, 5)
    assert db_conn.execute("SELECT rec_id FROM trades").fetchone()[0] == 42


def test_sync_discretionary_trade_has_null_rec(db_conn):
    client = FakeClient(
        fills=[_fill("TSLA", "buy", 1, 200.0, 1, "o1"),
               _fill("TSLA", "sell", 1, 210.0, 3, "o2")],
    )
    sync_account(db_conn, client, 90, 5)
    assert db_conn.execute("SELECT rec_id FROM trades").fetchone()[0] is None


def test_sync_populates_positions_snapshot(db_conn):
    client = FakeClient(
        positions=[{"symbol": "AAPL", "quantity": 10.0, "average_buy_price": 150.0,
                    "market_value": 1600.0, "last_price": 160.0}],
        fills=[_fill("AAPL", "buy", 10, 150.0, 1, "o1")],
    )
    summary = sync_account(db_conn, client, 90, 5)
    from swing_lab.db import load_positions
    held = load_positions(db_conn, "robinhood")
    assert len(held) == 1 and held[0]["symbol"] == "AAPL"
    assert summary["positions"] == 1


def test_sync_reconciliation_warns_on_mismatch(db_conn):
    # Reconstruction says 10 open; snapshot says 8 -> warning
    client = FakeClient(
        positions=[{"symbol": "AAPL", "quantity": 8.0, "average_buy_price": 150.0,
                    "market_value": 1280.0, "last_price": 160.0}],
        fills=[_fill("AAPL", "buy", 10, 150.0, 1, "o1")],
    )
    summary = sync_account(db_conn, client, 90, 5)
    assert any("AAPL" in w for w in summary["warnings"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_sync.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'swing_lab.sync'`).

- [ ] **Step 3: Implement the orchestrator**

Create `src/swing_lab/sync.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_sync.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all tests pass (Tasks 1–10), no live API calls.

- [ ] **Step 6: Commit**

```bash
git add src/swing_lab/sync.py tests/test_sync.py
git commit -m "feat: idempotent transactional broker sync orchestrator"
```

---

## Task 11: CLI — `broker-login` and `sync` commands

Follows the existing `cli.py` pattern: a `_cmd_*` function with lazy imports, a subparser in `main()`, and an `elif` dispatch branch.

**Files:**
- Modify: `src/swing_lab/cli.py` (add two `_cmd_*` functions; add two subparsers in `main()`; add two dispatch branches)

- [ ] **Step 1: Add the `_cmd_broker_login` function**

In `src/swing_lab/cli.py`, add this function next to the other `_cmd_*` functions (e.g. after `_cmd_rebalance`, around line 332):

```python
def _cmd_broker_login():
    """One-time interactive setup: store Robinhood credentials and validate login."""
    import getpass
    from swing_lab.config import store_broker_credentials
    from swing_lab.broker import RobinhoodClient

    print("Robinhood login setup — credentials are stored in Windows Credential Manager.")
    username = input("Robinhood email/username: ").strip()
    password = getpass.getpass("Robinhood password: ")
    totp_seed = getpass.getpass(
        "TOTP seed (the base32 secret shown when you enabled 2FA, no spaces): "
    ).strip()

    store_broker_credentials(username, password, totp_seed)
    print("Credentials stored. Validating login...")
    try:
        RobinhoodClient().authenticate()
    except Exception as exc:
        print(f"Login FAILED: {exc}")
        print("Credentials were saved but could not be validated. "
              "Re-run `swing-lab broker-login` to correct them.")
        return
    print("Login successful — session token cached. You can now run `swing-lab sync`.")
```

- [ ] **Step 2: Add the `_cmd_sync` function**

In `src/swing_lab/cli.py`, add immediately after `_cmd_broker_login`:

```python
def _cmd_sync(lookback_days=None):
    """Pull positions + filled orders from Robinhood into swing.db."""
    from swing_lab.config import SYNC_LOOKBACK_DAYS, REC_MATCH_WINDOW_DAYS
    from swing_lab.db import init_db
    from swing_lab.broker import RobinhoodClient
    from swing_lab.sync import sync_account

    lookback = lookback_days if lookback_days is not None else SYNC_LOOKBACK_DAYS

    client = RobinhoodClient()
    try:
        client.authenticate()
    except RuntimeError as exc:
        print(str(exc))
        return

    conn = init_db()
    try:
        summary = sync_account(conn, client, lookback, REC_MATCH_WINDOW_DAYS)
    finally:
        conn.close()

    print(f"\nSYNC COMPLETE (lookback {lookback}d)")
    print(f"  Trades imported (new):   {summary['inserted']}")
    print(f"  Trades closed (updated): {summary['updated']}")
    print(f"  Already up to date:      {summary['skipped']}")
    print(f"  Positions snapshot:      {summary['positions']} symbol(s)")
    if summary["warnings"]:
        print("\n  RECONCILIATION WARNINGS (snapshot is authoritative):")
        for w in summary["warnings"]:
            print(f"    - {w}")
```

- [ ] **Step 3: Register the subparsers in `main()`**

In `src/swing_lab/cli.py`, inside `main()`, add after the `filter` subparser block (after line 527, before `args = parser.parse_args()`):

```python
    # broker-login subcommand
    broker_login_p = sub.add_parser(
        "broker-login", help="Store Robinhood credentials and validate login (one-time)")

    # sync subcommand
    sync_p = sub.add_parser(
        "sync", help="Import Robinhood positions + filled orders into swing.db")
    sync_p.add_argument("--lookback-days", type=int, default=None, dest="lookback_days",
                        help="How far back to pull filled orders (default: config)")
```

- [ ] **Step 4: Register the dispatch branches**

In `src/swing_lab/cli.py`, inside `main()`, add after the `filter` dispatch branch (after line 566, before the closing `else:`):

```python
    elif args.command == "broker-login":
        _cmd_broker_login()
    elif args.command == "sync":
        _cmd_sync(args.lookback_days)
```

- [ ] **Step 5: Verify the commands are wired (no network)**

Run: `uv run swing-lab --help`
Expected: `broker-login` and `sync` both appear in the subcommand list.

Run: `uv run swing-lab sync --help`
Expected: shows the `--lookback-days` option, exits 0.

- [ ] **Step 6: Commit**

```bash
git add src/swing_lab/cli.py
git commit -m "feat: broker-login and sync CLI commands"
```

---

## Task 12: Wire real positions into `rebalance`

`_cmd_rebalance` currently derives current positions from `open_trades(conn)` (hand-typed trades). Switch it to the real Robinhood positions snapshot so rebalance filters held symbols from ground truth.

**Files:**
- Modify: `src/swing_lab/cli.py:290-331` (`_cmd_rebalance`)

- [ ] **Step 1: Update the imports and position source in `_cmd_rebalance`**

In `src/swing_lab/cli.py`, in `_cmd_rebalance`, replace the import line and the open-trades block.

Replace:

```python
    from swing_lab.db import init_db
    from swing_lab.tradelog import open_trades
```

with:

```python
    from swing_lab.db import init_db, load_positions
    from swing_lab.config import BROKER
```

Then replace:

```python
    # Get open trades from DB
    conn = init_db()
    try:
        current_open = open_trades(conn)
    finally:
        conn.close()
    open_positions = {t["symbol"] for t in current_open}
```

with:

```python
    # Get real held positions from the latest Robinhood sync snapshot
    conn = init_db()
    try:
        held = load_positions(conn, BROKER)
    finally:
        conn.close()
    open_positions = {p["symbol"] for p in held}
    if not held:
        print("\n(No synced positions found — run `swing-lab sync` first. "
              "Treating account as flat.)")
```

- [ ] **Step 2: Verify rebalance still runs against a flat (un-synced) DB**

Run: `uv run swing-lab rebalance`
Expected: runs to completion; with no synced positions, prints the "No synced positions found" note and `Open positions: none` (it will still fetch the gate/scanner — this hits yfinance, which is acceptable for a manual smoke check). If you want to avoid network during verification, instead confirm the function imports cleanly:
Run: `uv run python -c "from swing_lab.cli import _cmd_rebalance; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/swing_lab/cli.py
git commit -m "feat: rebalance reads real held symbols from positions snapshot"
```

---

## Task 13: Full-suite gate + manual end-to-end validation

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest -v`
Expected: all tests pass; zero live API calls (everything broker-facing is mocked/faked).

- [ ] **Step 2: Manual live validation (requires a real Robinhood account)**

> This is the only step that touches the live API. It is read-only — no orders are placed.

1. `uv run swing-lab broker-login` → enter username, password, TOTP seed → expect "Login successful".
2. `uv run swing-lab sync` → expect a summary with imported trades / positions count, and any reconciliation warnings.
3. Inspect the DB:
   - `uv run swing-lab log list` → imported trades appear with real fills.
   - `uv run swing-lab rebalance` → "Open positions" reflects your real Robinhood holdings.
4. Re-run `uv run swing-lab sync` → summary shows `inserted: 0`, all `skipped` (idempotent).
5. (Optional) `uv run swing-lab postmortem` → confirm the existing learning loop runs unchanged over the imported real trades.

- [ ] **Step 3: Update milestone tracking (project CLAUDE.md rule)**

Per the project "Plan File Rule," copy this plan to `PLANNING.md` (or update the existing milestone table in `Swing Lab/PLANNING.md`) marking the Robinhood Broker Foundation milestone ✅ Complete with today's date.

- [ ] **Step 4: Final commit**

```bash
git add PLANNING.md
git commit -m "docs: mark Robinhood broker foundation milestone complete"
```

---

## Self-Review (completed by plan author)

**1. Spec coverage** — every spec section maps to a task:
- §3 scope (`broker.py`, `broker-login`, `sync`, rebalance reads real positions) → Tasks 9, 11, 10/12.
- §4 architecture (client surface, sync orchestrator, CLI, config constants, keyring) → Tasks 2, 9, 10, 11.
- §5 data flow (positions upsert/replace; fills→episodes; 5-day rec match; idempotency; reconciliation snapshot-wins) → Tasks 4, 6, 7, 8, 10.
- §6 schema (trades columns; `positions`; `account_snapshots`) → Task 3.
- §7 error handling (missing-creds actionable error, atomic transaction, only `filled` orders) → Tasks 2, 9, 10.
- §8 testing (robin_stocks mocked; reconstruction cases; idempotency; reconciliation; keyring-missing) → Tasks 6, 8, 9, 10, 2.
- §10 success criteria → Task 13 manual validation maps 1:1.
- Optional `get_quote`/`get_historicals` (§4) correctly **omitted** — not required by #1.

**2. Placeholder scan** — no TBD/TODO/"handle edge cases"; every code step shows complete code. The one external unknown (exact `robin_stocks` names) is explicitly flagged, isolated to `broker.py`, and mocked in tests.

**3. Type consistency** — the episode dict keys produced by `reconstruct_episodes` (Task 6) exactly match what `insert_broker_episode`/`update_trade_close_from_broker` consume (Task 5): `opened_at, closed_at, shares, entry_price, exit_price, fees, pnl, pnl_pct, broker_order_ids, opening_order_id, symbol`. The fill dict from `broker.get_filled_orders` (Task 9) matches `reconstruct_episodes`' input contract (Task 6): `symbol, side, shares, price, fees, filled_at, order_id`. The positions dict from `broker.get_positions` (Task 9) matches `replace_positions` (Task 4) and `reconcile` (Task 8): `symbol, quantity, average_buy_price, market_value, last_price`. `find_matching_rec` returns `rec_id|None` consumed by `insert_broker_episode`. Function names are consistent across tasks (`sync_account`, `find_trade_by_opening_order`, `update_trade_close_from_broker`, `load_recent_recs_for_symbol`).

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-15-robinhood-broker-foundation.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
