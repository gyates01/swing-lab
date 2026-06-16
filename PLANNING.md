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
