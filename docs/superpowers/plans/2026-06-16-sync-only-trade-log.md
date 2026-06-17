# Sync-Only Trade Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Robinhood sync and the paper engine the only writers of the trade log — remove all manual trade-entry surfaces, scope the postmortem to strategy trades, and clean up the phantom manual trade.

**Architecture:** Two testable behavior changes (postmortem strategy filter; CLI subcommand removal) done TDD-first, followed by UI/code removals verified by `py_compile` + the full suite, then a one-time data cleanup. No new modules; `open_trade`/`close_trade` plumbing is untouched.

**Tech Stack:** Python 3.11, `uv run pytest`, SQLite (`data/swing.db`), Streamlit dashboard, argparse CLI.

**Standing directives (carry through every task):** work in-place on `main` (no feature branch); commit ONLY the named files (never `git add -A`/`.`); never `--no-verify`; never `--amend` (always NEW commits); every commit ends with the trailer `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`.

**Strategy-trade filter (single source of truth for this plan):** a trade is "strategy" iff `rec_id IS NOT NULL OR mode = 'paper'`.

---

## Task 1: Scope the postmortem to strategy trades

**Files:**
- Modify: `src/swing_lab/db.py` (`load_trades_with_context`, ~line 392)
- Modify: `src/swing_lab/dashboard/lib.py` (`load_trade_outcomes`, ~line 172)
- Test: `tests/test_postmortem_scope.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_postmortem_scope.py`:

```python
"""Postmortem data sources must include only strategy trades (rec-linked or paper)."""


def _seed_three_closed(db_conn):
    """One rec-linked live, one paper, one bare live — all closed. Returns nothing."""
    from swing_lab.tradelog import open_trade, close_trade
    t1 = open_trade(db_conn, "SNDK", 1.0, 100.0, rec_id=4)   # strategy: rec-linked
    close_trade(db_conn, t1, 110.0)
    t2 = open_trade(db_conn, "AAPL", 1.0, 100.0, mode="paper")  # strategy: paper
    close_trade(db_conn, t2, 110.0)
    t3 = open_trade(db_conn, "VOO", 1.0, 100.0)             # non-strategy: bare live
    close_trade(db_conn, t3, 110.0)


def test_load_trades_with_context_excludes_non_strategy(db_conn):
    from swing_lab.db import load_trades_with_context
    _seed_three_closed(db_conn)
    symbols = {r["symbol"] for r in load_trades_with_context(db_conn)}
    assert symbols == {"SNDK", "AAPL"}


def test_load_trade_outcomes_excludes_non_strategy(db_conn, tmp_path, monkeypatch):
    # load_trade_outcomes reads via lib.py's own DB_PATH (imported from config),
    # which the db_conn fixture does not patch — point it at the same tmp file.
    monkeypatch.setattr("swing_lab.dashboard.lib.DB_PATH", tmp_path / "swing.db")
    from swing_lab.dashboard.lib import load_trade_outcomes
    _seed_three_closed(db_conn)
    symbols = set(load_trade_outcomes()["symbol"].tolist())
    assert symbols == {"SNDK", "AAPL"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_postmortem_scope.py -v`
Expected: both FAIL — `VOO` is present, so `symbols == {"SNDK","AAPL","VOO"}` ≠ `{"SNDK","AAPL"}`.

- [ ] **Step 3: Add the filter in `db.py`**

In `src/swing_lab/db.py::load_trades_with_context`, change the WHERE clause from:

```python
           WHERE t.exit_price IS NOT NULL
```

to:

```python
           WHERE t.exit_price IS NOT NULL
             AND (t.rec_id IS NOT NULL OR t.mode = 'paper')
```

- [ ] **Step 4: Add the filter in `lib.py`**

In `src/swing_lab/dashboard/lib.py::load_trade_outcomes`, change:

```python
           WHERE t.exit_price IS NOT NULL
```

to:

```python
           WHERE t.exit_price IS NOT NULL
             AND (t.rec_id IS NOT NULL OR t.mode = 'paper')
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_postmortem_scope.py -v`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_postmortem_scope.py src/swing_lab/db.py src/swing_lab/dashboard/lib.py
git commit -m "$(cat <<'EOF'
feat: scope postmortem to strategy trades

Postmortem analysis + outcomes table now include only rec-linked or paper
trades, excluding non-strategy account holdings (e.g. a VOO index hold)
swept in by the full-account Robinhood sync.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Remove manual `log open` / `log close` from the CLI

**Files:**
- Modify: `src/swing_lab/cli.py` (subparsers ~557-578, dispatch ~650-662, helpers `_cmd_log_open` ~137, `_cmd_log_close` ~148)
- Test: `tests/test_cli_no_manual_log.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_no_manual_log.py`:

```python
"""Manual trade-entry subcommands are removed; the CLI rejects them."""
import sys
import pytest


def _run_cli(monkeypatch, tmp_path, argv):
    # Point the DB at a tmp file so that, before removal, a parsed `log open`
    # would write to a throwaway DB instead of the real data/swing.db.
    monkeypatch.setattr("swing_lab.db.DB_PATH", tmp_path / "swing.db")
    monkeypatch.setattr(sys, "argv", ["swing-lab"] + argv)
    from swing_lab.cli import main
    main()


def test_log_open_subcommand_removed(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, tmp_path, ["log", "open", "AAPL", "1", "100"])


def test_log_close_subcommand_removed(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, tmp_path, ["log", "close", "1", "100"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_cli_no_manual_log.py -v`
Expected: both FAIL — `log open`/`log close` still parse and dispatch (no `SystemExit` raised). (They write to the tmp DB, not real data.)

- [ ] **Step 3: Remove the subparsers**

In `src/swing_lab/cli.py`, delete the `# log open` and `# log close` blocks (the `log_open_p = ...` block and the `log_close_p = ...` block, ~lines 557-578). Keep the `# log list` block. The result:

```python
    # log subcommand group
    log_p = sub.add_parser("log", help="Trade log operations")
    log_sub = log_p.add_subparsers(dest="log_command", required=True)

    # log list
    log_list_p = log_sub.add_parser("list", help="List recent trades")
    log_list_p.add_argument("--limit", type=int, default=20)
```

- [ ] **Step 4: Remove the dispatch branches**

In the `elif args.command == "log":` block (~650-662), delete the `open`/`close` branches. The result:

```python
    elif args.command == "log":
        if args.log_command == "list":
            _cmd_log_list(args.limit)
```

- [ ] **Step 5: Remove the now-dead helper functions**

Delete `_cmd_log_open` (~lines 137-146) and `_cmd_log_close` (~lines 148-175) entirely. Keep `_cmd_log_list`.

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_cli_no_manual_log.py -v`
Expected: both PASS (argparse raises `SystemExit` on the unknown `open`/`close` choice).

- [ ] **Step 7: Verify `log list` still works**

Run: `uv run swing-lab log list --limit 5`
Expected: prints recent trades (no error). This confirms the kept read-only path is intact.

- [ ] **Step 8: Commit**

```bash
git add tests/test_cli_no_manual_log.py src/swing_lab/cli.py
git commit -m "$(cat <<'EOF'
feat: drop manual log open/close CLI subcommands

Fills are imported via the Robinhood sync, so hand-logging is removed.
`swing-lab log list` (read-only) is retained.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Make the Trade Log page read-only + drop the Recommendation hand-off

**Files:**
- Modify: `src/swing_lab/dashboard/pages/4_Trade_Log.py`
- Modify: `src/swing_lab/dashboard/pages/5_Recommendation.py` (button block ~353-364)

No unit tests (Streamlit pages render at import and can't be unit-tested cleanly). Verification is `py_compile` + browser smoke (user action).

- [ ] **Step 1: Replace the import header of `4_Trade_Log.py`**

Replace the top import block (current lines 1-18) with exactly:

```python
"""Trade Log — read-only view of synced positions and trade history."""
import streamlit as st
import pandas as pd
from swing_lab.dashboard.lib import load_trades, load_open_trades, fmt_local_time
from swing_lab.dashboard.theme import (
    inject, render_topbar, section_header_html,
    GREEN, RED, AMBER, BORDER, CARD, TEXT, TEXT_DIM,
)
from swing_lab.dashboard import sidebar_chat
from swing_lab.dashboard.charts import fetch_history as _fetch_history, candle_chart as _candle_chart
```

(Removes `json`, `init_db`, `load_scans`, `get_conn`, `load_trade_outcome_context`, the four `tradelog` functions, `OUTCOME_*`, and unused theme names. The helper functions `_position_data`, `_market_status`, `_status_badge_html`, `_fmt_metric`, `_METRIC_OPTIONS` are kept as-is and reference only the imports above.)

- [ ] **Step 2: Delete the action-tabs section**

Delete the entire contiguous block that begins at the `# ── Action tabs ──` comment (current line 163) and ends immediately before the `# ── Positions tables ──` comment (current line 431). This removes `tab_open`, `tab_close`, `tab_edit` and all three `with tab_*:` bodies (the Open, Close, and Edit/Delete forms). Nothing after line 431 references those variables.

- [ ] **Step 3: Remove the inline per-row Close/Delete button**

In the open-positions loop, delete this block exactly (current lines 608-628):

```python
        if r_cols[8].button("Close", key=f"rm_{tid}", help=f"Close or remove trade #{tid}"):
            st.session_state[f"confirm_rm_{tid}"] = True

        # Inline removal confirmation
        if st.session_state.get(f"confirm_rm_{tid}"):
            c_msg, c_yes, c_no = st.columns([4, 0.8, 0.6])
            c_msg.warning(
                f"Remove #{tid}: {row.symbol} {row.shares:g} sh @ ${row.entry_price:.2f}? "
                f"This deletes the trade record — use Close Position tab to log an exit instead."
            )
            if c_yes.button("Delete", key=f"yes_{tid}", type="primary"):
                conn = init_db()
                try:
                    delete_trade(conn, tid)
                    st.session_state.pop(f"confirm_rm_{tid}", None)
                    st.rerun()
                finally:
                    conn.close()
            if c_no.button("Cancel", key=f"no_{tid}"):
                st.session_state.pop(f"confirm_rm_{tid}", None)
                st.rerun()
```

- [ ] **Step 4: Drop the now-unused trailing table column**

The removed Close button occupied the last (`r_cols[8]`) column. Shrink the table to 8 columns.

Replace (current lines 526-527):

```python
    h_cols = st.columns([0.4, 0.9, 0.8, 1.0, 1.1, 1.4, 0.6, 3.5, 0.7])
    _headers = ["ID", "Symbol", "Shares", "Entry $", None, "Opened", "", "Chart", ""]
```

with:

```python
    h_cols = st.columns([0.4, 0.9, 0.8, 1.0, 1.1, 1.4, 0.6, 3.5])
    _headers = ["ID", "Symbol", "Shares", "Entry $", None, "Opened", "", "Chart"]
```

Replace (current line 552):

```python
        r_cols = st.columns([0.4, 0.9, 0.8, 1.0, 1.1, 1.4, 0.6, 3.5, 0.7])
```

with:

```python
        r_cols = st.columns([0.4, 0.9, 0.8, 1.0, 1.1, 1.4, 0.6, 3.5])
```

(Chart stays at `r_cols[7]`; no other row indices change.)

- [ ] **Step 5: Update the page subtitle copy**

Replace the line (current ~159):

```python
    Open positions are tracked live against your entry price. Changes write directly to swing.db.
```

with:

```python
    Open positions are tracked live against your entry price. Synced read-only from your broker account.
```

- [ ] **Step 6: Remove the Recommendation page's "Open trade from this pick" button**

In `src/swing_lab/dashboard/pages/5_Recommendation.py`, delete this block exactly (current lines 353-364):

```python
        if top.get("rec_id"):
            if st.button(
                f"Open trade from this pick — {symbol}",
                type="primary",
                key="open_from_rec_btn",
            ):
                st.session_state["open_from_rec"] = {
                    "symbol": symbol,
                    "sizing_pct": top["sizing_pct"],
                    "rec_id": top["rec_id"],
                }
                st.switch_page("pages/4_Trade_Log.py")
```

- [ ] **Step 7: Verify both pages compile**

Run: `uv run python -m py_compile "src/swing_lab/dashboard/pages/4_Trade_Log.py" "src/swing_lab/dashboard/pages/5_Recommendation.py"`
Expected: no output, exit 0.

- [ ] **Step 8: Grep for leftover references**

Run: `uv run python -c "import pathlib,re; t=pathlib.Path('src/swing_lab/dashboard/pages/4_Trade_Log.py').read_text(); assert 'open_trade' not in t and 'close_trade' not in t and 'edit_trade' not in t and 'delete_trade' not in t and 'open_from_rec' not in t, 'leftover manual-entry reference'; print('clean')"`
Expected: prints `clean`.

- [ ] **Step 9: Commit**

```bash
git add src/swing_lab/dashboard/pages/4_Trade_Log.py src/swing_lab/dashboard/pages/5_Recommendation.py
git commit -m "$(cat <<'EOF'
feat: make Trade Log page read-only

Remove manual open/close/edit/delete forms and the per-row delete button;
the page now mirrors synced positions and history. Drop the Recommendation
page's "Open trade from this pick" hand-off into the manual form.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Delete the dead `edit_trade` / `delete_trade` functions

**Files:**
- Modify: `src/swing_lab/tradelog.py` (`edit_trade` ~82-120, `delete_trade` ~123-130)

After Task 3, nothing references these. (Verified: their only callers were the Trade Log page.)

> Note: `tradelog.py` may carry pre-existing uncommitted edits inside `edit_trade`/`delete_trade` from an earlier session. Deleting both functions supersedes those edits. Stage only `src/swing_lab/tradelog.py`.

- [ ] **Step 1: Confirm there are no remaining references**

Run: `uv run python -c "import subprocess,sys; import pathlib; root=pathlib.Path('src'); hits=[str(p) for p in root.rglob('*.py') for ln in p.read_text().splitlines() if ('edit_trade' in ln or 'delete_trade' in ln) and 'def ' not in ln]; print(hits); sys.exit(1 if hits else 0)"`
Expected: prints `[]` and exit 0. (If any file other than `tradelog.py` definitions appears, stop — Task 3 missed a reference.)

- [ ] **Step 2: Delete the functions**

In `src/swing_lab/tradelog.py`, delete the entire `def edit_trade(...)` function (~82-120) and the entire `def delete_trade(...)` function (~123-130). Keep `open_trade`, `close_trade`, `recent_trades`, `open_trades`.

- [ ] **Step 3: Verify the module imports and the full suite is green**

Run: `uv run python -c "import swing_lab.tradelog as t; assert not hasattr(t,'edit_trade') and not hasattr(t,'delete_trade'); print('ok')"`
Expected: prints `ok`.

Run: `uv run pytest -q`
Expected: all tests pass (the previously-green suite plus Task 1 & 2 additions; no collection/import errors).

- [ ] **Step 4: Commit**

```bash
git add src/swing_lab/tradelog.py
git commit -m "$(cat <<'EOF'
refactor: remove dead edit_trade/delete_trade helpers

These were only used by the now read-only Trade Log page.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: One-time cleanup of the phantom manual trade #3

**Files:**
- Data only: `data/swing.db` (not a code change; not committed — `data/swing.db` is runtime data)

Trade #3 is a hand-logged SNDK *open* with no broker link (`source IS NULL`) that duplicates the real synced SNDK round-trip and shows as a false open position. The delete is guarded so it can only remove a non-broker SNDK open.

- [ ] **Step 1: Inspect before**

Run:
```bash
uv run python -c "
import sqlite3; c=sqlite3.connect('data/swing.db')
print(c.execute('SELECT trade_id,symbol,exit_price,source FROM trades WHERE trade_id=3').fetchone())
"
```
Expected: `(3, 'SNDK', None, None)`. If it does not match (not SNDK, or `source` set, or already gone), STOP and do not delete.

- [ ] **Step 2: Delete the phantom row (guarded)**

Run:
```bash
uv run python -c "
import sqlite3; c=sqlite3.connect('data/swing.db')
n=c.execute(\"DELETE FROM trades WHERE trade_id=3 AND symbol='SNDK' AND source IS NULL AND exit_price IS NULL\").rowcount
c.execute('DELETE FROM trade_outcomes WHERE trade_id=3'); c.commit()
print('deleted rows:', n)
"
```
Expected: `deleted rows: 1`.

- [ ] **Step 3: Verify after**

Run:
```bash
uv run python -c "
import sqlite3; c=sqlite3.connect('data/swing.db')
print('trade 3 exists:', c.execute('SELECT 1 FROM trades WHERE trade_id=3').fetchone() is not None)
print('remaining ids:', [r[0] for r in c.execute('SELECT trade_id FROM trades ORDER BY trade_id')])
"
```
Expected: `trade 3 exists: False` and remaining ids `[4, 5, 6, 7]`.

(No commit — `data/swing.db` is runtime state, not source.)

---

## Task 6: Update PLANNING.md and run the final gate

**Files:**
- Modify: `PLANNING.md`

- [ ] **Step 1: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 2: Add a milestone row to the Milestone Status table**

In `PLANNING.md`, add this row to the **Milestone Status** table (after the Paper Execution Core row):

```markdown
| Sync-Only Trade Log (manual entry removed, postmortem scoped) | ✅ Complete | 2026-06-16 |
```

- [ ] **Step 3: Append a short sub-project section**

At the end of `PLANNING.md`, append:

```markdown
---

# Sub-project #3 — Sync-Only Trade Log

The Robinhood sync + paper engine are now the only writers of the trade log.
Manual entry removed (CLI `log open`/`close`, dashboard Open/Close/Edit/Delete,
Recommendation "Open trade from this pick"). Postmortem scoped to strategy
trades (`rec_id IS NOT NULL OR mode='paper'`) so non-strategy account holdings
(e.g. a VOO index hold) no longer pollute the analysis. Phantom manual trade #3
cleaned up. `open_trade`/`close_trade` plumbing retained for sync + paper engine.

- Spec: `docs/superpowers/specs/2026-06-16-sync-only-trade-log-design.md`
- Plan: `docs/superpowers/plans/2026-06-16-sync-only-trade-log.md`

### Verification
- ✅ Full suite green (Task 1 & 2 added postmortem-scope + CLI-removal tests).
- ⏳ Dashboard browser smoke (user action): Trade Log page renders read-only
  (no Open/Close/Edit/Delete); Recommendation page has no "Open trade" button.
```

- [ ] **Step 4: Commit**

```bash
git add PLANNING.md
git commit -m "$(cat <<'EOF'
docs: record sync-only trade log milestone

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- Manual CLI removal → Task 2. ✓
- Dashboard manual UI removal → Task 3 (steps 1-5). ✓
- Recommendation button removal → Task 3 (step 6). ✓
- `edit_trade`/`delete_trade` deletion → Task 4. ✓
- Postmortem scope (db.py + lib.py) → Task 1. ✓
- Phantom trade #3 cleanup → Task 5. ✓
- Accepted consequence (no structured outcome capture) → no code needed; postmortem already degrades gracefully. ✓
- Not-changing list (sync, paper engine, plumbing, chat agent) → untouched by all tasks. ✓

**Placeholder scan:** none — every code step shows exact strings/commands.

**Type/identifier consistency:** filter clause `(t.rec_id IS NOT NULL OR t.mode = 'paper')` identical in Tasks 1.3/1.4; `open_trade`/`close_trade` signatures match `tradelog.py`; column lists reduced from 9→8 consistently in header and rows.
