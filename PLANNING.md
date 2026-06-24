# Swing Lab — Robinhood Broker Foundation

Sub-project #1 of the automated/learning trading system: a **strictly read-only**
Robinhood broker integration. Imports real fills into the trade log (matched to
recommendations) and feeds real positions into `rebalance`. **No order placement
of any kind.**

- Full plan: `docs/superpowers/plans/2026-06-15-robinhood-broker-foundation.md`
- Design spec: `docs/superpowers/specs/2026-06-15-robinhood-broker-foundation-design.md`

## Milestone Status

| Milestone | Status | Date |
|---|---|---|
| Robinhood Broker Foundation (read-only sync) | ✅ Complete | 2026-06-15 |
| Paper Execution Core (propose → approve → execute) | ✅ Complete | 2026-06-16 |
| Sync-Only Trade Log (manual entry removed, postmortem scoped) | ✅ Complete | 2026-06-16 |
| Execution Price Levels & Charts (display entry/stop/target + lazy chart) | ✅ Complete | 2026-06-17 |
| Forward-Projected Exit Targets (ATR projection + 2:1 reward:risk gate) | ⏳ Pending | — |

> Plan: `docs/superpowers/plans/2026-06-17-execution-price-levels.md`

### Task breakdown (all complete 2026-06-15)

| # | Task | Commit |
|---|---|---|
| 1 | Dependencies + pytest bootstrap | 48b70f5 |
| 2 | Config constants + keyring credential helpers | bc2a5ae |
| 3 | Schema — new tables + trades migrations | 79e46aa |
| 4 | DB helpers — positions + account snapshot | 30405d0 |
| 5 | DB helpers — broker episodes + rec lookup | 08c7bc8 |
| 6 | Reconstruction (pure) — fills → episodes | 264c8e5, 0dbb863 |
| 7 | Rec matching (pure) — trading-day window | 4c42cad |
| 8 | Reconciliation (pure) | 0d5d9a1 |
| 9 | `broker.py` RobinhoodClient (read-only) | b98a434 |
| 10 | `sync.py` orchestrator (idempotent, atomic) | 0d5b8ea |
| 11 | CLI `broker-login` + `sync` commands | 43912dc |
| 12 | Wire real positions into `rebalance` | cd72ec0 |
| 13 | Full-suite gate + final review | (this commit) |

## What shipped

- **`broker.py`** — `RobinhoodClient` wrapping `robin_stocks` (TOTP 2FA via
  `pyotp`, cached session). Read-only surface: `get_positions`,
  `get_filled_orders`, `get_account_snapshot`. No order-placement methods exist.
- **Position-episode reconstruction** (`reconstruction.py`) — collapses the fill
  stream into round-trip trades (flat→long→flat = one episode; weighted-average
  entry/exit, net P&L). Long-only.
- **Rec matching** (`rec_match.py`) — matches an episode's open to the most-recent
  recommendation within a 5-trading-day window.
- **Reconciliation** (`reconcile.py`) — warns on snapshot-vs-reconstruction
  drift; snapshot is authoritative.
- **`sync.py`** — `sync_account` orchestrates one atomic transaction: replace
  positions, save account snapshot, insert/update/skip episodes (idempotent on
  the opening order_id), then reconcile.
- **CLI** — `swing-lab broker-login` (one-time credential setup) and
  `swing-lab sync` (import). `swing-lab rebalance` now reads real held symbols
  from the synced positions snapshot.
- **Credentials** — stored in Windows Credential Manager via `keyring`.

## Verification status

- ✅ Full test suite: 45 passed, zero live API calls (all broker-facing code
  faked via `monkeypatch`).
- ⏳ **Manual live validation (user action — requires real Robinhood account + MFA):**
  1. `uv run swing-lab broker-login` → enter username, password, TOTP seed → "Login successful".
  2. `uv run swing-lab sync` → summary of imported trades / positions + any reconciliation warnings.
  3. `uv run swing-lab log list` → imported trades appear with real fills.
  4. `uv run swing-lab rebalance` → "Open positions" reflects real Robinhood holdings.
  5. Re-run `uv run swing-lab sync` → `inserted: 0`, all `skipped` (idempotent).

## Follow-ups (deferred, not blocking)

- **Task 10 idempotency key** — `find_trade_by_opening_order` uses a
  `broker_order_ids_json LIKE '%"order_id"%'` substring scan. Safe in practice
  (Robinhood order ids are globally-unique UUIDs) but a dedicated indexed column
  + a rollback-on-failure test would be more robust.
- **Task 6 reconstruction** — no overshoot guard if net shares ever go negative
  (deliberately silent: crashing a read-only sync on corporate-action/split data
  is worse than tolerating it). Add interleaved-rebuy edge-case coverage.
- **Task 7 rec matching** — add window-boundary and same-day tie-break tests.
- **Task 8 reconciliation** — add within-tolerance and multi-discrepancy tests.
- **Task 9 broker** — harden ISO-timestamp comparison in `get_filled_orders`;
  add a sell-side fill normalization test.

---

# Sub-project #2 — Paper Execution Core

A `propose → approve → execute` pipeline for **paper** trading. The persisted
`orders` table is the single source of truth; the paper portfolio is **derived**
from `trades` where `mode='paper'` (no separate portfolio table). A 7-check
guardrail engine runs at both propose-time and execute-time. Fully decoupled
from the small real Robinhood account (fixed $10,000 paper bankroll).

- Full plan: `docs/superpowers/plans/2026-06-16-execution-paper-core.md`
- Design spec: `docs/superpowers/specs/2026-06-16-execution-paper-core-design.md`

### Task breakdown (all complete 2026-06-16)

| # | Task | Commit |
|---|---|---|
| 1 | Execution config constants | 4fbbad0 |
| 2 | `orders` table DDL + `load_latest_scan_picks` | 9c31049 |
| 3 | `open_trade` `mode` parameter | 29c7f4e |
| 4 | Execution package + `quotes.get_quote` | efed4a6 |
| 5 | Order queue CRUD (`orders.py`) | 9c7d05a |
| 6 | Paper account derivation (`paper_account.py`) | ad266a0 |
| 7 | Guardrail engine (`guardrails.py`) | 0097e6b |
| 8 | Proposal generation (`proposals.py`) | 4f9e3bb |
| 9 | Executor (`executor.py`) | 34f96fb |
| 10 | CLI `propose` command | 60fd3fa |
| 11 | Dashboard Execution page (page 7) | 9880e65 |
| 12 | Full-suite verification + final review | (this commit) |

### Verification status

- ✅ Full test suite: 93 passed (40 new execution-engine tests across 7 new
  test files), zero live API calls.
- ✅ End-to-end paper round-trip (propose → approve → execute → dedup) verified
  programmatically against a temp DB.
- ✅ Read-only invariant: `src/swing_lab/execution/` contains no `robin_stocks`
  or order-placement calls.
- ⏳ **Dashboard browser smoke (user action):** open page 7 (Execution), confirm
  the queue/approve/reject/execute flow and the paper-portfolio panel render.

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

---

# Sub-project #6 — Forward-Projected Exit Targets

The recommendation engine's exit target no longer anchors to the nearest swing
high / 52-week high (which collapses onto the entry for momentum leaders already
at new highs). A new pure `validate_target()` owns the final number: it
recomputes degenerate targets (≤ 5% above entry) to a forward `entry_high +
3.5×ATR` projection and flags sub-2:1 reward:risk (surfaced in `key_risks`, not
filtered). The analyst prompt + tool schema are updated to project targets
forward and explicitly not cap breakouts at the prior high.

- Spec: `docs/superpowers/specs/2026-06-24-exit-target-redesign-design.md`
- Plan: `docs/superpowers/plans/2026-06-24-forward-projected-exit-targets.md`

## Milestone Status

| Milestone | Status | Date |
|---|---|---|
| Forward-Projected Exit Targets | ⏳ Pending | — |
