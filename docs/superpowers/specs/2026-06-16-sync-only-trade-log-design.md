# Sync-Only Trade Log — Design Spec

**Date:** 2026-06-16
**Status:** Approved

## Goal

Make the Robinhood sync and the paper-execution engine the *only* writers of the
trade log. Remove every manual trade-entry surface, scope the postmortem to
strategy trades, and clean up the one leftover phantom manual trade.

## Motivation

With fills now auto-imported from Robinhood (read-only sync) and paper trades
created by the execution engine, hand-logging trades is redundant and creates
divergence from the broker truth (e.g. phantom trade #3 — a manual SNDK *open*
with no broker link that duplicates the real synced SNDK round-trip).

The postmortem is a *learning* tool ("which rec signals were predictive?").
The full-account sync pulls in non-strategy holdings (a buy-and-hold VOO index
position with no recommendation), which pollute the analysis. The postmortem
should analyze only trades the strategy actually drove.

## Principle

Broker is the source of truth for *fills*; the strategy layer (recs / paper)
defines what is worth *analyzing*.

## Scope decisions (settled)

- **Option B** for postmortem scope: the trade-log *history view* keeps mirroring
  the full account; only the *postmortem analysis* filters to strategy trades.
- **Strategy-trade filter:** `rec_id IS NOT NULL OR mode='paper'`.
  - Verified: SNDK trade → rec #4 (real pick, score 98.8). HST trade → rec #13
    (real pick, score 88, bought next day — a legitimate strategy trade). VOO →
    no rec (drops out). So the filter yields SNDK + HST, drops VOO.
- **Option A** for manual removal: full read-only mirror. Remove Open / Close /
  Edit / Delete from CLI and dashboard. One-time cleanup of phantom trade #3.

## Changes by file

### 1. `src/swing_lab/cli.py`
- Remove `log open` and `log close` subparsers and the `_cmd_log_open` /
  `_cmd_log_close` functions, plus their dispatch branches.
- Keep `log list` (read-only) and `_cmd_log_list`.
- `swing-lab log list` continues to work.

### 2. `src/swing_lab/dashboard/pages/4_Trade_Log.py`
- Remove all mutation UI: the "Open Position", "Close Position", and
  "Edit / Delete" tabs, plus the inline per-row Close/Delete buttons and their
  confirmation flow.
- Keep read-only sections: market-status header, portfolio summary bar, Open
  Positions table, Trade History table.
- Drop now-unused imports: `open_trade`, `close_trade`, `edit_trade`,
  `delete_trade`, `init_db`, `load_scans`, `load_trade_outcome_context`,
  `OUTCOME_THESIS_OPTIONS`, `OUTCOME_DRIVER_OPTIONS`, and any helpers used solely
  by removed forms.

### 3. `src/swing_lab/dashboard/pages/5_Recommendation.py`
- Remove the "Open trade from this pick" button and the `open_from_rec`
  session-state handoff (its only consumer was the manual Open tab).

### 4. `src/swing_lab/tradelog.py`
- Delete `edit_trade` and `delete_trade` (dead once the UI is gone — verified no
  other callers).
- Keep `open_trade`, `close_trade` (used by the paper executor + sync),
  `recent_trades` (used by `log list`), `open_trades` (used by dashboard/actions).

### 5. Postmortem scope (option B)
- `src/swing_lab/db.py::load_trades_with_context` — add
  `AND (t.rec_id IS NOT NULL OR t.mode = 'paper')` to the WHERE clause.
- `src/swing_lab/dashboard/lib.py::load_trade_outcomes` — add the same filter.

### 6. One-time data cleanup
- `DELETE FROM trades WHERE trade_id = 3` (phantom manual SNDK open;
  no `trade_outcomes` row exists for it). Will not reappear — the sync only
  recreates broker-sourced episodes (idempotent on broker opening order id).

## Accepted consequence

Structured outcome capture (thesis-validated / exit-driver /
red-flags-materialized) lived only in the manual Close form. Removing it means
new (synced) closes carry no such annotations. The postmortem already handles
"no structured data captured at close" and falls back to P&L + rec context. The
`trade_outcomes` table is currently empty, so nothing is lost today.

## Testing

- `load_trades_with_context`: excludes a non-rec live trade; includes a
  rec-linked live trade and a paper trade.
- `load_trade_outcomes`: same filter behavior.
- CLI: `log open` / `log close` no longer parse (argparse error); `log list`
  still parses.
- Dashboard pages are Streamlit — browser smoke is a user action.

## Not changing

Robinhood sync, paper-execution engine, `open_trade` / `close_trade` plumbing,
the chat/analyst agent (already read-only on trades).
