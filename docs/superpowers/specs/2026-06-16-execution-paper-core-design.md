# Execution Sub-Project — Phase 1: Paper Execution Core

**Date:** 2026-06-16
**Status:** Approved design, ready for implementation planning
**Sub-project:** Trade Execution (paper → live through an approval gate)
**Phase:** 1 of 4 (Paper Execution Core)

---

## Goal

Turn Swing Lab's *recommendations* into *paper trades* through an explicit
`propose → approve → execute` pipeline, with a persisted order queue as the
single source of truth and a guardrail engine enforced at both propose-time and
execute-time. Paper-only in this phase; no live order placement, no Telegram,
no automated exits.

## Why this phasing

The user wants the full lifecycle (opens + rebalance closes + automated
stop/target exits), dual approval surfaces (dashboard + Telegram), and a
criteria-gated unlock from paper to live. That is too large for one spec, so it
decomposes into four phases, each with its own spec/plan:

- **Phase 1 (this spec):** Paper Execution Core — the queue, sizing, guardrails,
  approve/execute pipeline, paper P&L. Dashboard + CLI surfaces. On-demand
  trigger.
- **Phase 2:** Position monitor + Telegram approval surface + automated
  stop/target *proposals* (still approval-gated).
- **Phase 3:** Live unlock — `LiveFill` backend wired to the (currently
  read-only) broker, gated behind paper-performance criteria.
- **Phase 4:** Autonomy — scheduled triggering and auto-firing of stop/target
  exits without manual approval.

Phase 1 is designed so the later phases slot in without rework: the executor's
fill backend is swappable (PaperFill now, LiveFill in Phase 3), and the approval
surfaces are thin readers/writers of the queue (Telegram in Phase 2 is just
another writer).

## Architecture

`propose → queue → approve → execute`. A persisted `orders` table is the single
source of truth. Proposals are generated from the latest saved recommendation
batch (opens) and the latest scan top-picks (closes), sized against a derived
paper account. Guardrails are checked when proposals are created and again at
execution. Approval happens in the dashboard; execution simulates a fill at the
current market quote and writes a paper trade. The paper portfolio is *derived*
from `trades` rows with `mode='paper'` — there is no separate paper-portfolio
table.

## Tech stack

Python 3.11+, SQLite (`data/swing.db`), pandas/numpy, yfinance (quotes),
Streamlit (dashboard). Reuses existing `tradelog`, `recommendation`, `scanner`,
`dashboard/actions`, `db` modules. New code lives in a `src/swing_lab/execution/`
package.

---

## Component Breakdown (Section 1)

New package `src/swing_lab/execution/`:

| File | Responsibility |
|---|---|
| `proposals.py` | `generate_proposals(conn)` — build pending orders: opens from latest rec batch, closes from scan top-picks vs open paper positions; sized; deduped. |
| `paper_account.py` | Derive cash / positions / equity from `trades` where `mode='paper'`, anchored on `PAPER_STARTING_CASH`. |
| `guardrails.py` | `check(proposal, account_state) -> list[Violation]` — all caps; run at propose-time AND execute-time. |
| `executor.py` | `execute_approved(conn)` — simulate fill at current quote, open/close paper trade, mark order filled. Fill backend swappable for Phase 3. |
| `orders.py` | Queue CRUD over the `orders` table; status transitions; expiry. |
| `quotes.py` | `get_quote(symbol) -> float | None` — current market quote (yfinance). |

Touches to existing files:
- `db.py` — add `orders` table + helpers (create/list/update/expire).
- `cli.py` — add `swing-lab propose` command.
- `dashboard/pages/7_Execution.py` — review/approve/reject/execute UI + paper
  portfolio P&L panel.
- `config.py` — new execution constants (below).

---

## Data Model (Section 2)

### `orders` table

| Column | Type / values | Notes |
|---|---|---|
| `order_id` | INTEGER PK | |
| `created_at` | TEXT (ISO) | |
| `mode` | TEXT | `'paper'` in Phase 1 (`'live'` later). |
| `side` | TEXT | `'buy'` \| `'sell'`. |
| `symbol` | TEXT | |
| `shares` | REAL | fractional allowed. |
| `est_price` | REAL | quote at propose-time. |
| `est_notional` | REAL | `shares × est_price`. |
| `reason` | TEXT | `'open_rec'` \| `'rebalance_close'`. |
| `rec_id` | INTEGER NULL | set for opens. |
| `trade_id` | INTEGER NULL | set for closes (the trade being closed); set on fill for opens (the trade created). |
| `status` | TEXT | `'pending'` \| `'approved'` \| `'rejected'` \| `'filled'` \| `'expired'`. |
| `guardrail_json` | TEXT NULL | serialized list of violations from propose-time check. |
| `decided_at` | TEXT NULL | approve/reject timestamp. |
| `filled_at` | TEXT NULL | |
| `fill_price` | REAL NULL | actual quote at execution. |
| `notes` | TEXT NULL | execution skips, late violations, etc. |

**Status flow:** `pending → approved → filled` (happy path); `pending → rejected`;
`approved → rejected` (late guardrail failure at execute); `pending|approved → expired`
(stale, next propose run).

### Paper portfolio — derived, no new table

- Open paper trades = `trades` where `mode='paper' AND closed_at IS NULL`.
- `cash = PAPER_STARTING_CASH + Σ realized_pnl(closed paper) − Σ cost_basis(open paper)`.
- `unrealized = Σ (open shares × live quote − cost_basis)`.
- `equity = cash + Σ(open shares × live quote)`.
- Realized P&L comes from `trades.pnl` (computed by `tradelog.close_trade`).

### New config constants (`config.py`)

| Constant | Default | Purpose |
|---|---|---|
| `PAPER_STARTING_CASH` | latest synced equity, fallback `10000.0` | Paper bankroll anchor (configurable). |
| `CASH_RESERVE_PCT` | `0.10` | Min cash kept as fraction of equity. |
| `MAX_OPEN_POSITIONS` | `8` | Cap on concurrent open paper positions. |
| `MAX_ORDERS_PER_DAY` | `10` | Daily order-count cap. |
| `MAX_NOTIONAL_PER_DAY_PCT` | `0.30` | Daily cumulative notional cap, as fraction of equity. |
| `EXECUTION_KILL_SWITCH` | `False` | Hard stop — blocks all orders when `True`. |
| `EXECUTION_MODE` | `'paper'` | Active fill backend selector. |

All defaults are tunable in `config.py`; the user may adjust before or after the
first run.

`MAX_POSITION_PCT` (0.08) already exists and is reused.

---

## Proposal Generation & Sizing (Section 3)

`generate_proposals(conn)` builds the pending queue from the latest saved rec
batch (opens) + latest scan (closes), against current paper account state.

**Opens (from latest rec batch):**
- For each rec in the latest `batch_id`: `target_notional = sizing_pct × paper_equity`
  (`sizing_pct` already carries the 8%/position cap from `compute_sizing`).
- `target_shares = round(target_notional / current_quote, 6)` — fractional shares
  allowed (matches RH fractional support). Quote via `quotes.get_quote(symbol)`.
- Skip if `target_shares × quote < $1` (RH fractional minimum) or quote is `None`.
- `side='buy'`, `reason='open_rec'`, carries `rec_id`.

**Closes (from scan top-picks, NOT the rec batch):**
- The rec engine (`select_candidates`) excludes already-held symbols, so a held
  name never reappears in recs — closes cannot be derived from the batch.
- Compare open paper positions against the latest scan's top-`TOP_N_PICKS`.
- Any open paper position whose symbol has fallen out of the top-picks →
  full-position sell. `side='sell'`, `shares = full position qty`,
  `reason='rebalance_close'`, carries `trade_id`.

**Dedup (idempotent):**
- Skip an open proposal if that symbol already has a `pending` order OR an open
  paper trade.
- Skip a close proposal if that symbol already has a `pending` sell.
- Re-running `propose` with no new batch is a no-op.

**Staleness:** `propose` reads the latest saved batch + scan from the DB. If none
exist (or the batch is older than the latest scan), it prints a warning to run
`swing-lab recommend` first, then proceeds with what's saved.

---

## Guardrail Engine (Section 4)

`guardrails.check(proposal, account_state) -> list[Violation]` — pure function,
empty list = passes. Run at **propose-time** (stored in `orders.guardrail_json`,
shown before approval) AND **execute-time** (re-checked against fresh state).

| Guardrail | Config | Check |
|---|---|---|
| Kill switch | `EXECUTION_KILL_SWITCH` | If `True`, block everything. Hard stop. |
| RTH-only | — | Block if outside 9:30–16:00 ET on a trading day. |
| Per-position cap | `MAX_POSITION_PCT` (0.08) | Re-verify `notional ≤ 8% × equity` (belt-and-suspenders; already in sizing). |
| Min cash reserve | `CASH_RESERVE_PCT` | Buys only: block if `cash − notional < CASH_RESERVE_PCT × equity`. |
| Max open positions | `MAX_OPEN_POSITIONS` | Buys only: block if opening a *new* symbol exceeds the cap. |
| Daily order count | `MAX_ORDERS_PER_DAY` | Block if today's filled+approved order count ≥ cap. |
| Daily notional | `MAX_NOTIONAL_PER_DAY_PCT` | Block if today's cumulative notional + this notional > `MAX_NOTIONAL_PER_DAY_PCT × equity`. |

- Sells are exempt from cash-reserve / max-positions / per-position checks
  (closing reduces risk). Sells still respect kill switch, RTH, daily limits.
- Violations are non-fatal at propose-time — the order still lands as `pending`
  with violations attached, so the reason is visible. The UI blocks approval for
  any order carrying a violation; the user must clear the guardrail (e.g. flip
  the kill switch) and re-run.
- `account_state` = derived paper account:
  `{cash, equity, open_symbols, todays_order_count, todays_notional}`.

---

## Approval & Execution Flow + Paper P&L (Section 5)

Pipeline: `propose → review → approve/reject → execute`. The `orders` table is
the single source of truth; surfaces are thin readers/writers.

**Approval surfaces (Phase 1):**
- **CLI:** `swing-lab propose` generates the queue and prints pending orders +
  guardrail flags. Approve/reject is dashboard-only in Phase 1 (one approval path
  to maintain).
- **Dashboard** `dashboard/pages/7_Execution.py`:
  - *Pending queue* table — symbol, side, shares, est_notional, reason, guardrail
    flags. Per-row **Approve** / **Reject**. Approve disabled if the row carries
    any violation.
  - **Execute Approved** button — runs `executor.execute_approved(conn)` for all
    `approved` orders.
  - *Paper portfolio* panel — derived holdings with live mark-to-market,
    unrealized P&L per position, realized P&L to date, cash, total equity.

**Execution (`executor.execute_approved`):**
1. Load all `approved` orders.
2. Re-run `guardrails.check` against fresh paper state. If it now fails →
   `status='rejected'`, note the late violation, skip.
3. `fill_price = quotes.get_quote(symbol)` (current market quote = paper fill
   model). If `None` → leave `approved`, note failure, skip (retry next run).
4. **Buy:** `tradelog.open_trade(conn, symbol, shares, fill_price, scan_id,
   thesis, rec_id)` with `mode='paper'`. **Sell:** `tradelog.close_trade(conn,
   trade_id, fill_price, exit_reason='rebalance', outcome)`.
5. Mark order `status='filled'`, set `filled_at`, `fill_price`, link `trade_id`.

**Paper P&L** — derived per Section 2 (no new table).

---

## Error Handling, Edge Cases & Testing (Section 6)

**Edge cases:**
- **Quote unavailable** at propose → skip that proposal (logged). At execute →
  leave `approved`, retry next run. Never fill at a stale/guessed price.
- **Insufficient paper cash** → caught by cash-reserve guardrail, not a crash.
- **Partial batch execution** — each order independent; one failure doesn't roll
  back others. Re-run is safe (filled orders skipped).
- **Re-running `propose`** — idempotent via dedup. No duplicate pending orders.
- **Stale batch/scan** — warn, proceed with latest saved.
- **Close with no matching open trade** — skip + note, don't crash.
- **Expired orders** — `pending`/`approved` orders older than today are marked
  `expired` at the next `propose` run (prices go stale; re-propose fresh).

**Error handling philosophy:** guardrails block bad orders; execution failures
are non-fatal per-order; the queue is the recovery log; kill switch is the hard
stop.

**Testing (TDD, real SQLite temp DB; quotes + RH faked, no live calls):**
- `test_paper_account.py` — cash/equity/unrealized derivation; starting-cash
  default.
- `test_proposals.py` — opens from rec batch, closes from scan dropout, sizing
  math, dedup idempotency, $1 minimum skip, no-batch warning.
- `test_guardrails.py` — each of the 7 checks in isolation (pass + fail), sells
  exempt from buy-only checks, kill switch blocks all.
- `test_executor.py` — buy opens paper trade, sell closes it, re-check rejection
  on state change, quote-None retry, status transitions, partial-batch
  independence.
- `test_orders.py` — queue CRUD, status flow, expiry.
- Dashboard page — smoke-tested manually (Streamlit), per project UI norm.

---

## Out of scope (Phase 1)

- Live order placement (Phase 3).
- Telegram approval surface (Phase 2).
- Automated stop/target exit proposals (Phase 2) and auto-firing (Phase 4).
- Scheduled / autonomous triggering (Phase 4).
- Position monitoring loop (Phase 2).

## Open items to confirm at plan time

- The guardrail defaults above (`CASH_RESERVE_PCT=0.10`, `MAX_OPEN_POSITIONS=8`,
  `MAX_ORDERS_PER_DAY=10`, `MAX_NOTIONAL_PER_DAY_PCT=0.30`) are starting points —
  confirm or adjust the concrete numbers.
- `PAPER_STARTING_CASH` reads the latest `account_snapshots.total_equity` at
  first run; confirm the `10000.0` fallback when no snapshot exists.
