# Paper Execution Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Swing Lab recommendations into paper trades through a `propose → approve → execute` pipeline, with a persisted `orders` queue as the single source of truth and a guardrail engine enforced at both propose-time and execute-time.

**Architecture:** A new `src/swing_lab/execution/` package. Proposals are built from the latest saved recommendation batch (opens) and the latest scan top-picks (closes), sized against a paper account *derived* from `trades` rows where `mode='paper'` (no separate portfolio table). Guardrails are pure checks run twice. Execution simulates a fill at the current yfinance quote and writes a paper trade. Approval/execution surfaces (CLI + Streamlit dashboard) are thin readers/writers of the queue.

**Tech Stack:** Python 3.11+, SQLite (`data/swing.db`), pandas/numpy, yfinance (quotes), Streamlit (dashboard). Reuses existing `tradelog`, `db`, `recommendation`, `scanner` modules. `uv run` for all commands. Tests use the existing `db_conn` pytest fixture (real temp SQLite, quotes faked — no live calls).

**Working directory note:** Per standing directive, work in-place on the current branch (NO feature branch). Commit ONLY the specific named files in each step (never `git add -A`). Every commit ends with the `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.

---

## File Structure

| File | Created/Modified | Responsibility |
|---|---|---|
| `src/swing_lab/config.py` | Modify | Add 7 execution constants. |
| `src/swing_lab/db.py` | Modify | Add `orders` table to `init_db` executescript; add `load_latest_scan_picks`. |
| `src/swing_lab/tradelog.py` | Modify | Add `mode` param to `open_trade`. |
| `src/swing_lab/execution/__init__.py` | Create | Package marker. |
| `src/swing_lab/execution/quotes.py` | Create | `get_quote(symbol) -> float | None`. |
| `src/swing_lab/execution/orders.py` | Create | Queue CRUD + status transitions + expiry + daily stats. |
| `src/swing_lab/execution/paper_account.py` | Create | Derive cash/equity/positions from paper trades. |
| `src/swing_lab/execution/guardrails.py` | Create | `check(proposal, account_state)` — the 7 caps. |
| `src/swing_lab/execution/proposals.py` | Create | `generate_proposals(conn)` — build the pending queue. |
| `src/swing_lab/execution/executor.py` | Create | `execute_approved(conn)` — fill approved orders. |
| `src/swing_lab/cli.py` | Modify | Add `swing-lab propose` command. |
| `src/swing_lab/dashboard/pages/7_Execution.py` | Create | Review/approve/reject/execute UI + paper P&L panel. |
| `tests/test_execution_config.py` | Create | Config constants. |
| `tests/test_db_orders_schema.py` | Create | `orders` table + `load_latest_scan_picks`. |
| `tests/test_tradelog_mode.py` | Create | `open_trade` mode param. |
| `tests/test_execution_quotes.py` | Create | `get_quote`. |
| `tests/test_execution_orders.py` | Create | Queue CRUD. |
| `tests/test_paper_account.py` | Create | Account derivation. |
| `tests/test_guardrails.py` | Create | Each guardrail. |
| `tests/test_proposals.py` | Create | Proposal generation. |
| `tests/test_executor.py` | Create | Execution flow. |

**Proposal dict shape** (the contract passed between proposals → guardrails → orders → executor):
```python
{
    "mode": "paper", "side": "buy" | "sell", "symbol": "AAPL",
    "shares": 5.0, "est_price": 100.0, "est_notional": 500.0,
    "reason": "open_rec" | "rebalance_close",
    "rec_id": 1 | None,        # set for opens
    "trade_id": None | 7,      # set for closes (the trade being closed)
}
```

**`account_state` dict shape** (consumed by `guardrails.check`):
```python
{"cash": float, "equity": float, "open_symbols": set[str],
 "todays_order_count": int, "todays_notional": float}
```

---

### Task 1: Execution config constants

**Files:**
- Modify: `src/swing_lab/config.py` (append after the broker section, ~line 48)
- Test: `tests/test_execution_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_execution_config.py
def test_execution_constants_exist():
    from swing_lab import config
    assert config.PAPER_STARTING_CASH == 10000.0
    assert config.CASH_RESERVE_PCT == 0.10
    assert config.MAX_OPEN_POSITIONS == 8
    assert config.MAX_ORDERS_PER_DAY == 12
    assert config.MAX_NOTIONAL_PER_DAY_PCT == 0.30
    assert config.EXECUTION_KILL_SWITCH is False
    assert config.EXECUTION_MODE == "paper"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_execution_config.py -v`
Expected: FAIL with `AttributeError: module 'swing_lab.config' has no attribute 'PAPER_STARTING_CASH'`

- [ ] **Step 3: Add the constants**

Append to `src/swing_lab/config.py` (after the broker constants):
```python
# --- Execution (paper trading) ---
PAPER_STARTING_CASH = 10000.0       # Paper bankroll, fixed (decoupled from the small real account)
CASH_RESERVE_PCT = 0.10             # Min cash kept as fraction of equity (deploy up to 90%)
MAX_OPEN_POSITIONS = 8              # Cap on concurrent open paper positions
MAX_ORDERS_PER_DAY = 12            # Daily order-count cap (above MAX_OPEN_POSITIONS for rebalance headroom)
MAX_NOTIONAL_PER_DAY_PCT = 0.30    # Daily cumulative notional cap, as fraction of equity
EXECUTION_KILL_SWITCH = False      # Hard stop — blocks all orders when True
EXECUTION_MODE = "paper"           # Active fill backend selector
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_execution_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/config.py tests/test_execution_config.py
git commit -m "$(cat <<'EOF'
feat(execution): add paper-trading config constants

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `orders` table + `load_latest_scan_picks`

**Files:**
- Modify: `src/swing_lab/db.py` (add table to `init_db` executescript ~line 137; add helper near `load_positions`)
- Test: `tests/test_db_orders_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_orders_schema.py
from datetime import datetime, timezone


def test_orders_table_exists(db_conn):
    cur = db_conn.execute("PRAGMA table_info(orders)")
    cols = {row[1] for row in cur.fetchall()}
    assert {"order_id", "created_at", "mode", "side", "symbol", "shares",
            "est_price", "est_notional", "reason", "rec_id", "trade_id",
            "status", "guardrail_json", "decided_at", "filled_at",
            "fill_price", "notes"} <= cols


def test_load_latest_scan_picks_orders_by_rank_desc(db_conn):
    from swing_lab.db import load_latest_scan_picks
    cur = db_conn.cursor()
    cur.execute("INSERT INTO scans (run_at, gate_score, sizing) VALUES (?, 1.0, 1.0)",
                (datetime.now(timezone.utc).isoformat(),))
    sid = cur.lastrowid
    cur.execute("INSERT INTO scan_picks (scan_id, symbol, rank_score) VALUES (?, 'AAPL', 5.0)", (sid,))
    cur.execute("INSERT INTO scan_picks (scan_id, symbol, rank_score) VALUES (?, 'MSFT', 9.0)", (sid,))
    db_conn.commit()
    picks = load_latest_scan_picks(db_conn)
    assert [p["symbol"] for p in picks] == ["MSFT", "AAPL"]


def test_load_latest_scan_picks_only_latest_scan(db_conn):
    from swing_lab.db import load_latest_scan_picks
    cur = db_conn.cursor()
    cur.execute("INSERT INTO scans (run_at, gate_score, sizing) VALUES (?, 1.0, 1.0)",
                (datetime.now(timezone.utc).isoformat(),))
    old = cur.lastrowid
    cur.execute("INSERT INTO scan_picks (scan_id, symbol, rank_score) VALUES (?, 'OLD', 1.0)", (old,))
    cur.execute("INSERT INTO scans (run_at, gate_score, sizing) VALUES (?, 1.0, 1.0)",
                (datetime.now(timezone.utc).isoformat(),))
    new = cur.lastrowid
    cur.execute("INSERT INTO scan_picks (scan_id, symbol, rank_score) VALUES (?, 'NEW', 1.0)", (new,))
    db_conn.commit()
    assert [p["symbol"] for p in load_latest_scan_picks(db_conn)] == ["NEW"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db_orders_schema.py -v`
Expected: FAIL — `test_orders_table_exists` fails (no `orders` table); `load_latest_scan_picks` raises `ImportError`.

- [ ] **Step 3: Add the `orders` table to the executescript**

In `src/swing_lab/db.py`, inside the `conn.executescript("""...""")` block in `init_db()`, add this CREATE statement (after the `account_snapshots` table, before the closing `""")`):
```sql
        CREATE TABLE IF NOT EXISTS orders (
            order_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at    TEXT    NOT NULL,
            mode          TEXT    NOT NULL DEFAULT 'paper',
            side          TEXT    NOT NULL,
            symbol        TEXT    NOT NULL,
            shares        REAL    NOT NULL,
            est_price     REAL,
            est_notional  REAL,
            reason        TEXT,
            rec_id        INTEGER,
            trade_id      INTEGER,
            status        TEXT    NOT NULL DEFAULT 'pending',
            guardrail_json TEXT,
            decided_at    TEXT,
            filled_at     TEXT,
            fill_price    REAL,
            notes         TEXT
        );
```

- [ ] **Step 4: Add the `load_latest_scan_picks` helper**

Add to `src/swing_lab/db.py` (next to `load_positions`):
```python
def load_latest_scan_picks(conn) -> list[dict]:
    """Return the most recent scan's picks, highest rank_score first."""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT symbol, sector, momentum, rank_score FROM scan_picks
           WHERE scan_id = (SELECT MAX(scan_id) FROM scan_picks)
           ORDER BY rank_score DESC""")
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_db_orders_schema.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/swing_lab/db.py tests/test_db_orders_schema.py
git commit -m "$(cat <<'EOF'
feat(execution): add orders table and load_latest_scan_picks

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `open_trade` `mode` parameter

**Files:**
- Modify: `src/swing_lab/tradelog.py:7-26`
- Test: `tests/test_tradelog_mode.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tradelog_mode.py
def test_open_trade_defaults_to_live(db_conn):
    from swing_lab.tradelog import open_trade
    tid = open_trade(db_conn, "AAPL", 1.0, 100.0)
    row = db_conn.execute("SELECT mode FROM trades WHERE trade_id = ?", (tid,)).fetchone()
    assert row[0] == "live"


def test_open_trade_accepts_paper_mode(db_conn):
    from swing_lab.tradelog import open_trade
    tid = open_trade(db_conn, "AAPL", 1.0, 100.0, mode="paper")
    row = db_conn.execute("SELECT mode FROM trades WHERE trade_id = ?", (tid,)).fetchone()
    assert row[0] == "paper"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tradelog_mode.py -v`
Expected: FAIL — `test_open_trade_accepts_paper_mode` fails (`open_trade() got an unexpected keyword argument 'mode'`).

- [ ] **Step 3: Add the `mode` param and include it in the INSERT**

Replace `open_trade` in `src/swing_lab/tradelog.py`:
```python
def open_trade(
    conn: sqlite3.Connection,
    symbol: str,
    shares: float,
    entry_price: float,
    scan_id: int | None = None,
    thesis: str = "",
    rec_id: int | None = None,
    mode: str = "live",
) -> int:
    """Insert a new open trade. Return trade_id."""
    opened_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO trades
           (opened_at, symbol, side, shares, entry_price, scan_id, rec_id, thesis_text, mode)
           VALUES (?, ?, 'long', ?, ?, ?, ?, ?, ?)""",
        (opened_at, symbol, shares, entry_price, scan_id, rec_id, thesis, mode),
    )
    conn.commit()
    return cursor.lastrowid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tradelog_mode.py tests/test_tradelog.py -v`
Expected: PASS (new tests + existing tradelog tests still green)

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/tradelog.py tests/test_tradelog_mode.py
git commit -m "$(cat <<'EOF'
feat(execution): add mode param to open_trade for paper trades

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Execution package + `quotes.get_quote`

**Files:**
- Create: `src/swing_lab/execution/__init__.py` (empty)
- Create: `src/swing_lab/execution/quotes.py`
- Test: `tests/test_execution_quotes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_execution_quotes.py
import types
import pandas as pd


class _FakeTicker:
    def __init__(self, last_price=None, hist=None):
        self.fast_info = types.SimpleNamespace(last_price=last_price)
        self._hist = hist if hist is not None else pd.DataFrame()

    def history(self, period="2d"):
        return self._hist


def test_get_quote_uses_fast_info(monkeypatch):
    from swing_lab.execution import quotes
    monkeypatch.setattr(quotes, "yf",
                        types.SimpleNamespace(Ticker=lambda s: _FakeTicker(last_price=123.45)))
    assert quotes.get_quote("AAPL") == 123.45


def test_get_quote_falls_back_to_history(monkeypatch):
    from swing_lab.execution import quotes
    df = pd.DataFrame({"Close": [100.0, 150.0]})
    monkeypatch.setattr(quotes, "yf",
                        types.SimpleNamespace(Ticker=lambda s: _FakeTicker(last_price=None, hist=df)))
    assert quotes.get_quote("AAPL") == 150.0


def test_get_quote_returns_none_on_error(monkeypatch):
    from swing_lab.execution import quotes

    def boom(symbol):
        raise RuntimeError("network down")

    monkeypatch.setattr(quotes, "yf", types.SimpleNamespace(Ticker=boom))
    assert quotes.get_quote("AAPL") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_execution_quotes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swing_lab.execution'`

- [ ] **Step 3: Create the package and quotes module**

Create `src/swing_lab/execution/__init__.py`:
```python
"""Paper trade execution pipeline: propose -> approve -> execute."""
```

Create `src/swing_lab/execution/quotes.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_execution_quotes.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/execution/__init__.py src/swing_lab/execution/quotes.py tests/test_execution_quotes.py
git commit -m "$(cat <<'EOF'
feat(execution): add execution package and quote lookup

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Order queue CRUD (`orders.py`)

**Files:**
- Create: `src/swing_lab/execution/orders.py`
- Test: `tests/test_execution_orders.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_execution_orders.py
def _prop(**kw):
    base = {"mode": "paper", "side": "buy", "symbol": "AAPL", "shares": 10.0,
            "est_price": 100.0, "est_notional": 1000.0, "reason": "open_rec",
            "rec_id": 1, "trade_id": None}
    base.update(kw)
    return base


def test_create_and_get_order(db_conn):
    from swing_lab.execution import orders
    oid = orders.create_order(db_conn, _prop(), guardrail=[])
    o = orders.get_order(db_conn, oid)
    assert o["symbol"] == "AAPL"
    assert o["status"] == "pending"
    assert o["guardrail_json"] == "[]"


def test_create_order_serializes_violations(db_conn):
    from swing_lab.execution import orders
    oid = orders.create_order(db_conn, _prop(), guardrail=["kill switch engaged"])
    assert orders.get_order(db_conn, oid)["guardrail_json"] == '["kill switch engaged"]'


def test_list_orders_filters_by_status(db_conn):
    from swing_lab.execution import orders
    orders.create_order(db_conn, _prop(symbol="AAPL"))
    oid2 = orders.create_order(db_conn, _prop(symbol="MSFT"))
    orders.set_status(db_conn, oid2, "approved", decided_at="2026-06-16T12:00:00Z")
    assert [o["symbol"] for o in orders.list_orders(db_conn, status="pending")] == ["AAPL"]
    assert len(orders.list_orders(db_conn)) == 2


def test_set_status_whitelists_fields(db_conn):
    from swing_lab.execution import orders
    oid = orders.create_order(db_conn, _prop())
    orders.set_status(db_conn, oid, "filled", filled_at="2026-06-16T12:00:00Z",
                      fill_price=101.0, trade_id=7, bogus="ignored")
    o = orders.get_order(db_conn, oid)
    assert o["status"] == "filled"
    assert o["fill_price"] == 101.0
    assert o["trade_id"] == 7
    assert "bogus" not in o


def test_pending_symbols(db_conn):
    from swing_lab.execution import orders
    orders.create_order(db_conn, _prop(symbol="AAPL", side="buy"))
    orders.create_order(db_conn, _prop(symbol="TSLA", side="sell"))
    assert orders.pending_symbols(db_conn) == {"AAPL", "TSLA"}
    assert orders.pending_symbols(db_conn, side="buy") == {"AAPL"}


def test_todays_stats_counts_filled_only(db_conn):
    from swing_lab.execution import orders
    o1 = orders.create_order(db_conn, _prop(est_notional=1000.0))
    orders.create_order(db_conn, _prop(symbol="MSFT", est_notional=500.0))  # stays pending
    orders.set_status(db_conn, o1, "filled")
    stats = orders.todays_stats(db_conn)
    assert stats["order_count"] == 1
    assert stats["notional"] == 1000.0


def test_expire_stale_marks_old_pending_and_approved(db_conn):
    from swing_lab.execution import orders
    db_conn.execute(
        """INSERT INTO orders (created_at, mode, side, symbol, shares, est_notional, status)
           VALUES ('2020-01-01T00:00:00Z', 'paper', 'buy', 'AAPL', 1.0, 100.0, 'pending')""")
    db_conn.execute(
        """INSERT INTO orders (created_at, mode, side, symbol, shares, est_notional, status)
           VALUES ('2020-01-01T00:00:00Z', 'paper', 'sell', 'MSFT', 1.0, 100.0, 'approved')""")
    db_conn.commit()
    assert orders.expire_stale(db_conn) == 2
    assert {o["symbol"] for o in orders.list_orders(db_conn, status="expired")} == {"AAPL", "MSFT"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_execution_orders.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swing_lab.execution.orders'`

- [ ] **Step 3: Write `orders.py`**

Create `src/swing_lab/execution/orders.py`:
```python
"""Queue CRUD over the `orders` table — the single source of truth."""
import json
from datetime import datetime, timezone

_SETTABLE = {"status", "decided_at", "filled_at", "fill_price",
             "trade_id", "notes", "guardrail_json"}


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


def expire_stale(conn) -> int:
    """Mark pending/approved orders created before today as expired. Return count."""
    today_utc = datetime.now(timezone.utc).date().isoformat()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE orders SET status = 'expired'
           WHERE status IN ('pending', 'approved') AND date(created_at) < ?""",
        (today_utc,),
    )
    conn.commit()
    return cursor.rowcount
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_execution_orders.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/execution/orders.py tests/test_execution_orders.py
git commit -m "$(cat <<'EOF'
feat(execution): add order queue CRUD over orders table

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Paper account derivation (`paper_account.py`)

**Files:**
- Create: `src/swing_lab/execution/paper_account.py`
- Test: `tests/test_paper_account.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_account.py
from swing_lab.config import PAPER_STARTING_CASH


def _open_paper(conn, symbol, shares, entry):
    from swing_lab.tradelog import open_trade
    return open_trade(conn, symbol, shares, entry, mode="paper")


def test_empty_account_is_starting_cash(db_conn):
    from swing_lab.execution.paper_account import paper_account_state
    state = paper_account_state(db_conn, quote_fn=lambda s: None)
    assert state["cash"] == PAPER_STARTING_CASH
    assert state["equity"] == PAPER_STARTING_CASH
    assert state["open_positions"] == []
    assert state["open_symbols"] == set()


def test_open_position_reduces_cash_and_marks_to_market(db_conn):
    from swing_lab.execution.paper_account import paper_account_state
    _open_paper(db_conn, "AAPL", 10.0, 100.0)  # $1000 cost basis
    state = paper_account_state(db_conn, quote_fn=lambda s: 120.0)
    assert state["cash"] == PAPER_STARTING_CASH - 1000.0
    assert state["equity"] == PAPER_STARTING_CASH - 1000.0 + 1200.0
    assert state["unrealized"] == 200.0
    assert state["open_symbols"] == {"AAPL"}


def test_quote_none_falls_back_to_entry_price(db_conn):
    from swing_lab.execution.paper_account import paper_account_state
    _open_paper(db_conn, "AAPL", 10.0, 100.0)
    state = paper_account_state(db_conn, quote_fn=lambda s: None)
    assert state["unrealized"] == 0.0
    assert state["equity"] == PAPER_STARTING_CASH


def test_realized_pnl_returns_to_cash(db_conn):
    from swing_lab.tradelog import open_trade, close_trade
    from swing_lab.execution.paper_account import paper_account_state
    tid = open_trade(db_conn, "AAPL", 10.0, 100.0, mode="paper")
    close_trade(db_conn, tid, 110.0, exit_reason="test")  # +$100 realized
    state = paper_account_state(db_conn, quote_fn=lambda s: None)
    assert state["cash"] == PAPER_STARTING_CASH + 100.0
    assert state["open_positions"] == []


def test_live_trades_excluded(db_conn):
    from swing_lab.tradelog import open_trade
    from swing_lab.execution.paper_account import paper_account_state
    open_trade(db_conn, "LIVE", 10.0, 100.0)  # mode defaults to 'live'
    state = paper_account_state(db_conn, quote_fn=lambda s: 999.0)
    assert state["cash"] == PAPER_STARTING_CASH
    assert state["open_symbols"] == set()


def test_account_state_for_guardrails_includes_daily_stats(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.paper_account import account_state_for_guardrails
    oid = orders.create_order(db_conn, {"mode": "paper", "side": "buy", "symbol": "AAPL",
                                        "shares": 1.0, "est_price": 100.0,
                                        "est_notional": 100.0, "reason": "open_rec"})
    orders.set_status(db_conn, oid, "filled")
    state = account_state_for_guardrails(db_conn, quote_fn=lambda s: None)
    assert state["todays_order_count"] == 1
    assert state["todays_notional"] == 100.0
    assert state["equity"] == PAPER_STARTING_CASH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paper_account.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swing_lab.execution.paper_account'`

- [ ] **Step 3: Write `paper_account.py`**

Create `src/swing_lab/execution/paper_account.py`:
```python
"""Derive the paper portfolio from `trades` where mode='paper'. No separate table."""
from swing_lab.config import PAPER_STARTING_CASH
from swing_lab.execution.quotes import get_quote


def _open_paper_trades(conn) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM trades WHERE mode = 'paper' AND exit_price IS NULL ORDER BY trade_id")
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _realized_pnl(conn) -> float:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(SUM(pnl), 0.0) FROM trades WHERE mode = 'paper' AND exit_price IS NOT NULL")
    return cursor.fetchone()[0]


def paper_account_state(conn, quote_fn=get_quote) -> dict:
    """{cash, equity, unrealized, open_positions, open_symbols}, marked to market."""
    opens = _open_paper_trades(conn)
    cost_basis = sum(t["shares"] * t["entry_price"] for t in opens)
    cash = PAPER_STARTING_CASH + _realized_pnl(conn) - cost_basis

    positions, market_value, unrealized = [], 0.0, 0.0
    for t in opens:
        quote = quote_fn(t["symbol"])
        mark = quote if quote is not None else t["entry_price"]
        value = t["shares"] * mark
        basis = t["shares"] * t["entry_price"]
        market_value += value
        unrealized += value - basis
        positions.append({
            "trade_id": t["trade_id"], "symbol": t["symbol"], "shares": t["shares"],
            "entry_price": t["entry_price"], "quote": quote,
            "market_value": value, "unrealized": value - basis,
        })

    return {
        "cash": cash,
        "equity": cash + market_value,
        "unrealized": unrealized,
        "open_positions": positions,
        "open_symbols": {p["symbol"] for p in positions},
    }


def account_state_for_guardrails(conn, quote_fn=get_quote) -> dict:
    """The slimmer state guardrails need, plus today's filled-order stats."""
    from swing_lab.execution import orders
    state = paper_account_state(conn, quote_fn=quote_fn)
    stats = orders.todays_stats(conn)
    return {
        "cash": state["cash"],
        "equity": state["equity"],
        "open_symbols": state["open_symbols"],
        "todays_order_count": stats["order_count"],
        "todays_notional": stats["notional"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paper_account.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/execution/paper_account.py tests/test_paper_account.py
git commit -m "$(cat <<'EOF'
feat(execution): derive paper account state from paper trades

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Guardrail engine (`guardrails.py`)

**Files:**
- Create: `src/swing_lab/execution/guardrails.py`
- Test: `tests/test_guardrails.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_guardrails.py
from datetime import datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_RTH = datetime(2026, 6, 17, 12, 0, tzinfo=_ET)       # Wednesday noon ET
_WEEKEND = datetime(2026, 6, 20, 12, 0, tzinfo=_ET)   # Saturday noon ET


def _state(**kw):
    base = {"cash": 9000.0, "equity": 10000.0, "open_symbols": set(),
            "todays_order_count": 0, "todays_notional": 0.0}
    base.update(kw)
    return base


def _prop(**kw):
    base = {"mode": "paper", "side": "buy", "symbol": "AAPL", "shares": 5.0,
            "est_price": 100.0, "est_notional": 500.0, "reason": "open_rec"}
    base.update(kw)
    return base


def test_clean_buy_passes():
    from swing_lab.execution import guardrails
    assert guardrails.check(_prop(), _state(), now_et=_RTH) == []


def test_kill_switch_blocks_everything(monkeypatch):
    from swing_lab.execution import guardrails
    monkeypatch.setattr(guardrails.config, "EXECUTION_KILL_SWITCH", True)
    assert guardrails.check(_prop(), _state(), now_et=_RTH) == ["kill switch engaged"]


def test_outside_rth_blocks():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(), _state(), now_et=_WEEKEND)
    assert "outside regular trading hours" in v


def test_per_position_cap():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(est_notional=900.0), _state(), now_et=_RTH)  # >8% of 10000
    assert "position exceeds max position size" in v


def test_cash_reserve():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(est_notional=500.0), _state(cash=1000.0), now_et=_RTH)
    assert "insufficient cash reserve" in v  # 1000-500=500 < 0.10*10000=1000


def test_max_open_positions():
    from swing_lab.execution import guardrails
    state = _state(open_symbols={f"S{i}" for i in range(8)})
    v = guardrails.check(_prop(symbol="ZZZZ"), state, now_et=_RTH)
    assert "max open positions reached" in v


def test_adding_to_existing_position_ignores_max_open():
    from swing_lab.execution import guardrails
    state = _state(open_symbols={f"S{i}" for i in range(8)})
    v = guardrails.check(_prop(symbol="S0"), state, now_et=_RTH)  # already held
    assert "max open positions reached" not in v


def test_daily_order_count():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(), _state(todays_order_count=12), now_et=_RTH)
    assert any("daily order count" in x for x in v)


def test_daily_notional():
    from swing_lab.execution import guardrails
    v = guardrails.check(_prop(est_notional=500.0), _state(todays_notional=2800.0), now_et=_RTH)
    assert "daily notional cap exceeded" in v  # 2800+500=3300 > 0.30*10000=3000


def test_sells_exempt_from_buy_only_checks():
    from swing_lab.execution import guardrails
    state = _state(cash=0.0, open_symbols={f"S{i}" for i in range(8)})
    v = guardrails.check(_prop(side="sell", symbol="ZZZZ", est_notional=500.0),
                         state, now_et=_RTH)
    assert v == []  # no cash-reserve / max-positions / per-position for sells
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_guardrails.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swing_lab.execution.guardrails'`

- [ ] **Step 3: Write `guardrails.py`**

Create `src/swing_lab/execution/guardrails.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_guardrails.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/execution/guardrails.py tests/test_guardrails.py
git commit -m "$(cat <<'EOF'
feat(execution): add guardrail engine with 7 caps

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Proposal generation (`proposals.py`)

**Files:**
- Create: `src/swing_lab/execution/proposals.py`
- Test: `tests/test_proposals.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_proposals.py
from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _rth(monkeypatch):
    """Pin guardrail clock to a weekday noon so propose-time checks are deterministic."""
    from zoneinfo import ZoneInfo
    monkeypatch.setattr("swing_lab.execution.guardrails._now_et",
                        lambda: datetime(2026, 6, 17, 12, 0, tzinfo=ZoneInfo("America/New_York")))


def _seed_scan(conn, symbols):
    cur = conn.cursor()
    cur.execute("INSERT INTO scans (run_at, gate_score, sizing) VALUES (?, 1.0, 1.0)",
                (datetime.now(timezone.utc).isoformat(),))
    sid = cur.lastrowid
    for i, s in enumerate(symbols):
        cur.execute("INSERT INTO scan_picks (scan_id, symbol, rank_score) VALUES (?, ?, ?)",
                    (sid, s, float(len(symbols) - i)))
    conn.commit()
    return sid


def _seed_recs(conn, scan_id, recs):
    """recs: list of (rank, symbol, sizing_pct)."""
    created_at = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    for rank, symbol, sizing_pct in recs:
        cur.execute(
            """INSERT INTO recommendations
               (batch_id, created_at, scan_id, rank, symbol, sizing_pct, gate_sizing)
               VALUES (1, ?, ?, ?, ?, ?, 1.0)""",
            (created_at, scan_id, rank, symbol, sizing_pct))
    conn.commit()


def test_generates_buy_from_rec(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.proposals import generate_proposals
    sid = _seed_scan(db_conn, ["AAPL"])
    _seed_recs(db_conn, sid, [(1, "AAPL", 0.05)])
    result = generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    assert len(result["created"]) == 1
    o = result["created"][0]
    assert o["side"] == "buy" and o["symbol"] == "AAPL"
    assert o["shares"] == 5.0 and o["est_notional"] == 500.0
    assert orders.list_orders(db_conn, status="pending")[0]["symbol"] == "AAPL"


def test_skips_held_symbol(db_conn):
    from swing_lab.tradelog import open_trade
    from swing_lab.execution.proposals import generate_proposals
    open_trade(db_conn, "AAPL", 5.0, 100.0, mode="paper")
    sid = _seed_scan(db_conn, ["AAPL"])
    _seed_recs(db_conn, sid, [(1, "AAPL", 0.05)])
    result = generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    assert result["created"] == []  # held -> no buy; still a top-pick -> no close


def test_dedup_idempotent(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.proposals import generate_proposals
    sid = _seed_scan(db_conn, ["AAPL"])
    _seed_recs(db_conn, sid, [(1, "AAPL", 0.05)])
    generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    generate_proposals(db_conn, quote_fn=lambda s: 100.0)  # re-run
    assert len(orders.list_orders(db_conn, status="pending")) == 1


def test_below_min_notional_skipped(db_conn):
    from swing_lab.execution.proposals import generate_proposals
    sid = _seed_scan(db_conn, ["AAPL"])
    _seed_recs(db_conn, sid, [(1, "AAPL", 0.00001)])  # 0.00001*10000 = $0.10 notional
    result = generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    assert result["created"] == []
    assert any("minimum" in w for w in result["warnings"])


def test_close_on_scan_dropout(db_conn):
    from swing_lab.tradelog import open_trade
    from swing_lab.execution.proposals import generate_proposals
    open_trade(db_conn, "OLD", 10.0, 100.0, mode="paper")  # held, not in scan
    sid = _seed_scan(db_conn, ["NEW"])                     # OLD has dropped out
    _seed_recs(db_conn, sid, [(1, "NEW", 0.05)])
    result = generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    sells = [o for o in result["created"] if o["side"] == "sell"]
    assert len(sells) == 1
    assert sells[0]["symbol"] == "OLD" and sells[0]["shares"] == 10.0
    assert sells[0]["trade_id"] is not None


def test_no_recs_warns(db_conn):
    from swing_lab.execution.proposals import generate_proposals
    _seed_scan(db_conn, ["AAPL"])  # scan but no recs today
    result = generate_proposals(db_conn, quote_fn=lambda s: 100.0)
    assert result["created"] == []
    assert any("recommend" in w for w in result["warnings"])


def test_quote_none_skips_open(db_conn):
    from swing_lab.execution.proposals import generate_proposals
    sid = _seed_scan(db_conn, ["AAPL"])
    _seed_recs(db_conn, sid, [(1, "AAPL", 0.05)])
    result = generate_proposals(db_conn, quote_fn=lambda s: None)
    assert result["created"] == []
    assert any("no quote" in w for w in result["warnings"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_proposals.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swing_lab.execution.proposals'`

- [ ] **Step 3: Write `proposals.py`**

Create `src/swing_lab/execution/proposals.py`:
```python
"""Build the pending order queue: opens from latest recs, closes from scan dropout."""
from swing_lab import config
from swing_lab.db import load_latest_recommendations, load_latest_scan_picks
from swing_lab.execution import guardrails, orders
from swing_lab.execution.paper_account import (
    account_state_for_guardrails,
    paper_account_state,
)
from swing_lab.execution.quotes import get_quote

_MIN_NOTIONAL = 1.0  # RH fractional-share minimum


def generate_proposals(conn, quote_fn=get_quote) -> dict:
    """Return {created: [order dicts], warnings: [str]}. Idempotent via dedup."""
    warnings: list[str] = []
    orders.expire_stale(conn)

    recs = load_latest_recommendations(conn)
    picks = load_latest_scan_picks(conn)
    if not recs:
        warnings.append("no saved recommendations today — run `swing-lab recommend` first")

    account = paper_account_state(conn, quote_fn=quote_fn)
    guard_state = account_state_for_guardrails(conn, quote_fn=quote_fn)
    held = account["open_symbols"]
    pending_buys = orders.pending_symbols(conn, side="buy")
    pending_sells = orders.pending_symbols(conn, side="sell")

    created = []

    # Opens — from the latest rec batch
    for rec in recs:
        symbol = rec["symbol"]
        if symbol in held or symbol in pending_buys:
            continue
        quote = quote_fn(symbol)
        if quote is None:
            warnings.append(f"{symbol}: no quote, skipped open")
            continue
        shares = round(rec["sizing_pct"] * account["equity"] / quote, 6)
        notional = shares * quote
        if notional < _MIN_NOTIONAL:
            warnings.append(f"{symbol}: below ${_MIN_NOTIONAL:.0f} minimum, skipped")
            continue
        proposal = {
            "mode": config.EXECUTION_MODE, "side": "buy", "symbol": symbol,
            "shares": shares, "est_price": quote, "est_notional": notional,
            "reason": "open_rec", "rec_id": rec["rec_id"], "trade_id": None,
        }
        oid = orders.create_order(conn, proposal,
                                  guardrail=guardrails.check(proposal, guard_state))
        created.append(orders.get_order(conn, oid))

    # Closes — open positions that dropped out of the scan top-picks
    top_symbols = {p["symbol"] for p in picks[:config.TOP_N_PICKS]}
    for pos in account["open_positions"]:
        symbol = pos["symbol"]
        if symbol in top_symbols or symbol in pending_sells:
            continue
        quote = quote_fn(symbol)
        if quote is None:
            warnings.append(f"{symbol}: no quote, skipped close")
            continue
        notional = pos["shares"] * quote
        proposal = {
            "mode": config.EXECUTION_MODE, "side": "sell", "symbol": symbol,
            "shares": pos["shares"], "est_price": quote, "est_notional": notional,
            "reason": "rebalance_close", "rec_id": None, "trade_id": pos["trade_id"],
        }
        oid = orders.create_order(conn, proposal,
                                  guardrail=guardrails.check(proposal, guard_state))
        created.append(orders.get_order(conn, oid))

    return {"created": created, "warnings": warnings}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_proposals.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/execution/proposals.py tests/test_proposals.py
git commit -m "$(cat <<'EOF'
feat(execution): generate buy/sell proposals into the queue

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Executor (`executor.py`)

**Files:**
- Create: `src/swing_lab/execution/executor.py`
- Test: `tests/test_executor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_executor.py
from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _rth(monkeypatch):
    from zoneinfo import ZoneInfo
    monkeypatch.setattr("swing_lab.execution.guardrails._now_et",
                        lambda: datetime(2026, 6, 17, 12, 0, tzinfo=ZoneInfo("America/New_York")))


def _approved(conn, **kw):
    """Create an order and move it to 'approved'. Return order_id."""
    from swing_lab.execution import orders
    base = {"mode": "paper", "side": "buy", "symbol": "AAPL", "shares": 5.0,
            "est_price": 100.0, "est_notional": 500.0, "reason": "open_rec",
            "rec_id": 1, "trade_id": None}
    base.update(kw)
    oid = orders.create_order(conn, base)
    orders.set_status(conn, oid, "approved", decided_at=datetime.now(timezone.utc).isoformat())
    return oid


def test_buy_fills_and_opens_paper_trade(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.executor import execute_approved
    from swing_lab.tradelog import open_trades
    oid = _approved(db_conn)
    result = execute_approved(db_conn, quote_fn=lambda s: 100.0)
    assert result["filled"] == [oid]
    o = orders.get_order(db_conn, oid)
    assert o["status"] == "filled" and o["fill_price"] == 100.0 and o["trade_id"] is not None
    opens = open_trades(db_conn)
    assert len(opens) == 1 and opens[0]["symbol"] == "AAPL" and opens[0]["mode"] == "paper"


def test_sell_closes_paper_trade(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.executor import execute_approved
    from swing_lab.tradelog import open_trade
    tid = open_trade(db_conn, "AAPL", 10.0, 100.0, mode="paper")
    oid = _approved(db_conn, side="sell", symbol="AAPL", shares=10.0,
                    est_notional=1000.0, reason="rebalance_close", rec_id=None, trade_id=tid)
    result = execute_approved(db_conn, quote_fn=lambda s: 110.0)
    assert result["filled"] == [oid]
    closed = db_conn.execute("SELECT exit_price, pnl FROM trades WHERE trade_id = ?", (tid,)).fetchone()
    assert closed[0] == 110.0 and closed[1] == 100.0  # (110-100)*10


def test_quote_none_keeps_approved(db_conn):
    from swing_lab.execution import orders
    from swing_lab.execution.executor import execute_approved
    oid = _approved(db_conn)
    result = execute_approved(db_conn, quote_fn=lambda s: None)
    assert result["skipped"] == [oid] and result["filled"] == []
    assert orders.get_order(db_conn, oid)["status"] == "approved"


def test_late_guardrail_rejection(db_conn, monkeypatch):
    from swing_lab.execution import guardrails, orders
    from swing_lab.execution.executor import execute_approved
    oid = _approved(db_conn)
    monkeypatch.setattr(guardrails.config, "EXECUTION_KILL_SWITCH", True)
    result = execute_approved(db_conn, quote_fn=lambda s: 100.0)
    assert result["rejected"] == [oid]
    o = orders.get_order(db_conn, oid)
    assert o["status"] == "rejected" and "kill switch" in o["notes"]


def test_partial_batch_independence(db_conn):
    from swing_lab.execution.executor import execute_approved
    good = _approved(db_conn, symbol="AAPL")
    bad = _approved(db_conn, symbol="MSFT")
    result = execute_approved(db_conn, quote_fn=lambda s: 100.0 if s == "AAPL" else None)
    assert result["filled"] == [good] and result["skipped"] == [bad]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swing_lab.execution.executor'`

- [ ] **Step 3: Write `executor.py`**

Create `src/swing_lab/execution/executor.py`:
```python
"""Execute approved orders: re-check guardrails, fill at current quote, write paper trades.

The fill model (current market quote) is the only thing Phase 3 swaps for live fills.
"""
from datetime import datetime, timezone

from swing_lab.execution import guardrails, orders
from swing_lab.execution.paper_account import account_state_for_guardrails
from swing_lab.execution.quotes import get_quote
from swing_lab.tradelog import close_trade, open_trade


def _proposal_from_order(o: dict) -> dict:
    return {
        "mode": o["mode"], "side": o["side"], "symbol": o["symbol"],
        "shares": o["shares"], "est_price": o["est_price"],
        "est_notional": o["est_notional"], "reason": o["reason"],
        "rec_id": o["rec_id"], "trade_id": o["trade_id"],
    }


def execute_approved(conn, quote_fn=get_quote) -> dict:
    """Fill all approved orders. Return {filled, rejected, skipped} order-id lists."""
    filled, rejected, skipped = [], [], []
    for o in orders.list_orders(conn, status="approved"):
        oid = o["order_id"]
        proposal = _proposal_from_order(o)

        # Re-check against fresh state — state may have changed since approval
        state = account_state_for_guardrails(conn, quote_fn=quote_fn)
        violations = guardrails.check(proposal, state)
        if violations:
            orders.set_status(conn, oid, "rejected",
                              decided_at=datetime.now(timezone.utc).isoformat(),
                              notes="; ".join(violations))
            rejected.append(oid)
            continue

        quote = quote_fn(o["symbol"])
        if quote is None:
            orders.set_status(conn, oid, "approved", notes="no quote at execute")
            skipped.append(oid)
            continue

        filled_at = datetime.now(timezone.utc).isoformat()
        if o["side"] == "buy":
            trade_id = open_trade(conn, o["symbol"], o["shares"], quote,
                                  rec_id=o["rec_id"], mode="paper")
            orders.set_status(conn, oid, "filled", filled_at=filled_at,
                              fill_price=quote, trade_id=trade_id)
        else:
            close_trade(conn, o["trade_id"], quote, exit_reason="rebalance")
            orders.set_status(conn, oid, "filled", filled_at=filled_at, fill_price=quote)
        filled.append(oid)

    return {"filled": filled, "rejected": rejected, "skipped": skipped}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_executor.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/execution/executor.py tests/test_executor.py
git commit -m "$(cat <<'EOF'
feat(execution): execute approved orders into paper trades

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: CLI `propose` command

**Files:**
- Modify: `src/swing_lab/cli.py` (add `_cmd_propose`; register subparser ~line 600; dispatch ~line 644)

This task has no unit test (matches the project norm — CLI commands are thin wrappers, verified manually). Follow the existing `_cmd_*` pattern: `init_db()` in a try/finally.

- [ ] **Step 1: Add the command function**

Add near the other `_cmd_*` functions in `src/swing_lab/cli.py`:
```python
def _cmd_propose():
    from swing_lab.db import init_db
    from swing_lab.execution.proposals import generate_proposals
    from tabulate import tabulate

    conn = init_db()
    try:
        result = generate_proposals(conn)
    finally:
        conn.close()

    for w in result["warnings"]:
        print(f"  ! {w}")

    created = result["created"]
    if not created:
        print("\nNo new proposals. (Nothing changed since the last run, or no recs/scan saved.)")
        return

    rows = []
    for o in created:
        flags = "; ".join(json.loads(o["guardrail_json"])) or "ok"
        rows.append([o["order_id"], o["side"], o["symbol"],
                     f"{o['shares']:.4f}", f"${o['est_notional']:.2f}", o["reason"], flags])
    print(f"\n{len(created)} proposal(s) queued as pending:\n")
    print(tabulate(rows, headers=["id", "side", "symbol", "shares", "notional", "reason", "guardrails"]))
    print("\nApprove/reject and execute from the dashboard (page 7 — Execution).")
```

Add `import json` at the top of `cli.py` if not already present (it is used by the new function).

- [ ] **Step 2: Register the subparser**

After the `sync` subparser block (~line 602), add:
```python
    # propose subcommand
    propose_p = sub.add_parser(
        "propose", help="Generate paper-trade proposals into the order queue")
```

- [ ] **Step 3: Add the dispatch branch**

After the `elif args.command == "sync":` branch (~line 644), add:
```python
    elif args.command == "propose":
        _cmd_propose()
```

- [ ] **Step 4: Manually verify the command runs**

Run: `uv run swing-lab propose`
Expected: Prints warnings (likely "no saved recommendations today" if none) and either a proposals table or the "No new proposals" message — and exits 0 without a traceback.

Also confirm help registers: `uv run swing-lab --help` lists `propose`.

- [ ] **Step 5: Confirm the full suite is still green**

Run: `uv run pytest -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/swing_lab/cli.py
git commit -m "$(cat <<'EOF'
feat(execution): add `swing-lab propose` CLI command

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Dashboard Execution page

**Files:**
- Create: `src/swing_lab/dashboard/pages/7_Execution.py`

No unit test — Streamlit pages are smoke-tested manually per the project UI norm. Use `init_db()` (not `get_conn()`) so the `orders` table is guaranteed to exist. Keep it simple: `st.dataframe` / `st.button` / `st.metric`.

- [ ] **Step 1: Create the page**

Create `src/swing_lab/dashboard/pages/7_Execution.py`:
```python
"""Page 7 — Paper Execution: review/approve/reject/execute the order queue."""
import json
from datetime import datetime, timezone

import streamlit as st

from swing_lab.dashboard import sidebar_chat
from swing_lab.dashboard.theme import inject, render_topbar
from swing_lab.db import init_db
from swing_lab.execution import orders
from swing_lab.execution.executor import execute_approved
from swing_lab.execution.paper_account import paper_account_state
from swing_lab.execution.proposals import generate_proposals

st.set_page_config(page_title="Execution — Swing Lab", layout="wide")
inject()
sidebar_chat.render()
render_topbar()

conn = init_db()

st.header("Paper Execution")

col_a, col_b = st.columns(2)
if col_a.button("Generate proposals", use_container_width=True):
    result = generate_proposals(conn)
    for w in result["warnings"]:
        st.warning(w)
    st.success(f"{len(result['created'])} new proposal(s) queued.")
if col_b.button("Execute approved", use_container_width=True):
    result = execute_approved(conn)
    st.success(f"Filled {len(result['filled'])}, rejected {len(result['rejected'])}, "
               f"skipped {len(result['skipped'])}.")

# --- Pending queue ---
st.subheader("Pending queue")
pending = orders.list_orders(conn, status="pending")
if not pending:
    st.caption("No pending orders. Click 'Generate proposals' to build the queue.")
for o in pending:
    flags = json.loads(o["guardrail_json"])
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    c1.write(f"**{o['side'].upper()} {o['symbol']}** — {o['shares']:.4f} sh "
             f"(~${o['est_notional']:.2f}) · {o['reason']}")
    if flags:
        c2.error("; ".join(flags))
    else:
        c2.success("guardrails ok")
    if c3.button("Approve", key=f"approve_{o['order_id']}", disabled=bool(flags)):
        orders.set_status(conn, o["order_id"], "approved",
                          decided_at=datetime.now(timezone.utc).isoformat())
        st.rerun()
    if c4.button("Reject", key=f"reject_{o['order_id']}"):
        orders.set_status(conn, o["order_id"], "rejected",
                          decided_at=datetime.now(timezone.utc).isoformat())
        st.rerun()

# --- Approved (awaiting execution) ---
approved = orders.list_orders(conn, status="approved")
if approved:
    st.subheader("Approved — awaiting execution")
    st.dataframe([{"id": o["order_id"], "side": o["side"], "symbol": o["symbol"],
                   "shares": o["shares"], "est_notional": o["est_notional"]} for o in approved],
                 use_container_width=True)

# --- Paper portfolio ---
st.subheader("Paper portfolio")
state = paper_account_state(conn)
m1, m2, m3 = st.columns(3)
m1.metric("Equity", f"${state['equity']:,.2f}")
m2.metric("Cash", f"${state['cash']:,.2f}")
m3.metric("Unrealized P&L", f"${state['unrealized']:,.2f}")
if state["open_positions"]:
    st.dataframe([{"symbol": p["symbol"], "shares": p["shares"],
                   "entry": p["entry_price"], "quote": p["quote"],
                   "market_value": p["market_value"], "unrealized": p["unrealized"]}
                  for p in state["open_positions"]], use_container_width=True)
else:
    st.caption("No open paper positions.")
```

- [ ] **Step 2: Manually smoke-test the page**

Run: `uv run swing-lab dashboard` and open the "Execution" page (page 7) in the browser.
Verify, in order:
1. Page loads with no traceback; "Paper portfolio" shows Equity = $10,000.00, Cash = $10,000.00 (empty paper book).
2. "Generate proposals" runs without error (warns about missing recs if none saved).
3. If proposals appear, an order with a guardrail flag has **Approve disabled**; a clean order can be approved → moves to the "Approved" table.
4. "Execute approved" fills approved orders and the paper portfolio updates (cash drops, position appears).

- [ ] **Step 3: Commit**

```bash
git add src/swing_lab/dashboard/pages/7_Execution.py
git commit -m "$(cat <<'EOF'
feat(execution): add dashboard Execution page (queue + paper P&L)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Full-suite verification + final review

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -q`
Expected: All tests pass (existing + the 8 new execution test files), no warnings introduced.

- [ ] **Step 2: End-to-end manual smoke (paper round-trip)**

With a saved scan + recommendations present (run `uv run swing-lab recommend` if needed):
```bash
uv run swing-lab propose
```
Then in the dashboard: approve one clean buy → Execute approved → confirm a paper trade opened and the portfolio panel reflects it. Re-run `uv run swing-lab propose` and confirm it does NOT re-propose the now-held symbol (dedup).

- [ ] **Step 3: Final code review**

Dispatch the final code-reviewer over the whole branch diff (per subagent-driven-development) or self-review against the spec at `docs/superpowers/specs/2026-06-16-execution-paper-core-design.md`. Confirm: queue is the single source of truth, guardrails run at both propose and execute, paper account is derived (no new portfolio table), and the integration stayed read-only with respect to the real broker (no robin_stocks order calls anywhere in `execution/`).

- [ ] **Step 4: Update PLANNING.md milestone status**

Per project CLAUDE.md, mark this phase complete in `PLANNING.md`'s Milestone Status table with today's date.
