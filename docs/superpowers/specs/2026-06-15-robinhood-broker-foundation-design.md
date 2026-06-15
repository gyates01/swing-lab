# Robinhood Broker Foundation + Real Account Visibility — Design

> **Date:** 2026-06-15
> **Status:** Approved design (pre-implementation)
> **Sub-project:** #1 of the Robinhood integration roadmap
> **Target:** Swing Lab at `H:\Other\Claude Projects\Swing Lab\`

---

## 1. Context & Goal

Garrett connected a Robinhood MCP to Claude Code and wants to "utilize this with Swing Lab."
The long-term vision is an **automated trading system that learns over time** — using Swing
Lab's existing signals (macro gate, scan, Claude review, recommendation) to act on trades and
then grade whether each prediction was good/bad and whether the outcome was explained by the
fundamentals/macro it logged or by other factors.

**Primary goal is the system + its learning loop, not immediate returns.** This is explicit
because Swing Lab's own walk-forward backtest (`PROJECT.md:69-71`) concluded **no tested
configuration beat SPY** on absolute or risk-adjusted return, and the documented defensible use
was *"the scanner/review pipeline as idea generation for discretionary trades — not as a
systematic SPY-beating strategy."* Automating execution does not create edge; the value here is
building and learning from the closed loop.

### Architectural foundation (applies to the whole roadmap)

Swing Lab is a standalone Python program (`uv run swing-lab ...`); it cannot call an MCP tool
directly. The Robinhood MCP lives inside Claude Code. (`INTEGRATION_PLAN.md:36-39` already caught
this exact mismatch for the TradingView MCP.) Decision: **hybrid model.**

- **Python-native client** (`robin_stocks`) inside Swing Lab → works headless / scheduled / from
  Claude Code via `swing-lab` commands. This is the foundation everything is built on.
- **Keep the Robinhood MCP** for ad-hoc interactive exploration in Claude Code ("what's my
  portfolio look like right now") — not wired into the Python program.

### Roadmap decomposition (each its own spec → plan → build)

1. **Broker Foundation + Real Account Visibility** *(this spec)* — read-only RH client; import
   real fills into the trade log (matched to recommendations); real positions into rebalance.
2. **Paper execution engine** — recommendation → sized orders → *simulated* fills, full-auto,
   recorded with full prediction context. Zero money, zero ToS risk.
3. **Learning loop** — grade predictions vs. outcomes; attribute to market/fundamentals/other.
   (Note: the attribution structure already largely exists — see §3.)
4. **Live execution** — real `place_equity_order` behind a **phone-approval gate** + hard caps.
   Built last, on a proven foundation.

**Autonomy decision:** paper trading may run **full-auto**; real-money trades go through an
**approval gate** (pipeline runs unattended → pushes sized orders to phone → user taps approve →
execute). Full-auto for real money is a possible *future* step gated on demonstrated performance,
not now.

---

## 2. Why this is mostly a "feed real data" project, not a "build the learning loop" project

The existing `swing.db` schema already implements the learning infrastructure:

- `trade_outcomes` (`db.py:53-63`) already **is** the structured attribution layer:
  `thesis_validated`, `exit_driver`, `red_flags_materialized`, `exit_triggers_fired`,
  `macro_aligned`, `notes`.
- `trades.rec_id` (`db.py:47`) already links each trade to the `recommendation` that predicted
  it, which carries the full thesis: `entry_low/high`, `support`, `stop_price`, `target`,
  `rationale`, `risks_json`.
- `postmortem` already runs Claude pattern analysis over closed trades + outcomes.

Today this loop runs on **hand-typed** trades. Sub-project #1 swaps manual entry for **real
Robinhood fills**, so the loop runs on ground truth automatically.

**Learning scope:** start with **structured outcome attribution** (the existing qualitative
grading). Design the schema to support future **adaptive parameter tuning** and a **predictive
model** by capturing rich data now (e.g., `account_snapshots`) even if it is only graded
qualitatively at first.

---

## 3. Sub-project #1 — Scope

**IN scope:**
- `broker.py` — a **read-only** `RobinhoodClient` (via `robin_stocks`).
- `swing-lab broker-login` — one-time interactive command to store credentials + validate.
- `swing-lab sync` — pulls current positions + filled orders from Robinhood into `swing.db`.
- `rebalance`/recommendation reads **real** held symbols from the positions snapshot.

**OUT of scope (deferred):**
- **No order placement of any kind — not even paper.** This sub-project is read-only. Paper
  execution = #2; live approval-gated execution = #4. The foundation must be boring and correct
  before any order can be sent.
- No Telegram/approval gate (#4).
- The Robinhood MCP is not wired into Python; it stays for interactive use.

---

## 4. Architecture (Approach 1: thin sync module + CLI command)

Mirrors the existing pattern — each concern is its own module + CLI subcommand, all writing to
`swing.db`.

- **`src/swing_lab/broker.py`** → `RobinhoodClient` with a clean read-only method surface.
  Required by #1: `authenticate()`, `get_positions()`, `get_filled_orders(since=...)`,
  `get_account_snapshot()`. Thin wrappers `get_quote(symbol)` / `get_historicals(symbol)` are
  *optional* — one-liners over `robin_stocks` included only if convenient; they serve later
  live-data work (§11) and are **not** required by #1's success criteria. Returns plain data;
  **does no DB writes**.
- **Sync orchestrator** (function/module) maps broker data → `swing.db` via `db.py` functions
  (keeps broker I/O separate from persistence).
- **`cli.py`** gets `broker-login` and `sync` subparsers.
- **`config.py`** gets `BROKER='robinhood'`, `SYNC_LOOKBACK_DAYS`, `REC_MATCH_WINDOW_DAYS=5`.
- **Credentials** live **only** in Windows Credential Manager (`keyring`, service e.g.
  `swing_lab_robinhood`). `robin_stocks`' own token cache handles session reuse so MFA isn't
  re-triggered every run.

**Future-broker seam:** the `broker` column on persisted rows + the clean client method surface =
a trivial future extraction into a `BrokerClient` interface. **No abstraction built now** (YAGNI);
Robinhood-only today.

---

## 5. Data Flow & Matching Logic

Two Robinhood endpoints, two purposes.

### Flow A — Current holdings (authoritative "what do I own")
`get_positions()` → symbol, quantity, average cost, market value → **upserted** into the
`positions` snapshot table. This is the source of truth that `rebalance`/recommendation reads to
filter out symbols already held. Replace-on-sync (sold-out symbols removed).

### Flow B — Trade history + outcomes (learning fuel)
`get_filled_orders(since=...)` → a stream of buy/sell fills → reconstructed into Swing Lab's
position-lifecycle `trades` rows.

**The reconstruction algorithm is the only genuinely new logic.** Robinhood gives *fills*; Swing
Lab models *round-trip positions*. Decisions:

1. **Granularity → position-episode.** All fills for a symbol from "first share bought" until
   "flat again" collapse into **one** trade: averaged entry, averaged exit, total P&L net of fees.
   Matches how a swing trader thinks and how a recommendation predicts (one thesis → one trade →
   one grade). (Rejected alternative: FIFO lot-by-lot rows — granular but fragments scaled entries
   into noise.)
2. **Trade→rec matching window → 5 trading days** (`REC_MATCH_WINDOW_DAYS`, config). When an
   episode opens, link it to the most recent `recommendation` for that symbol created within the
   prior 5 trading days. If matched, `rec_id` is set → existing outcome machinery can grade it.
3. **Discretionary (un-recommended) trades → imported with `rec_id = NULL`.** Logged for a
   complete picture; simply not graded against a prediction. (Whether a trade was recommended is
   captured by `rec_id IS NULL`, not a separate column.)

**Baked-in rules:**
- **Idempotency:** sync is re-runnable. Imported `broker_order_id`s are tracked; reconstruction is
  deterministic; re-running never duplicates.
- **Reconciliation:** if reconstructed open trades disagree with the live positions snapshot
  (splits, transfers, fractional quirks), the **snapshot wins** and the mismatch is **logged as a
  warning** for review rather than silently rewriting history.

---

## 6. Schema Changes

All additive, using the existing safe-migration pattern (`db.py:119-136`).

**Extend `trades`:**
- `broker TEXT` — `'robinhood'` (legacy hand-typed rows stay `'manual'`/NULL)
- `broker_order_ids_json TEXT` — RH order IDs composing the episode (idempotency + audit)
- `source TEXT` — origin only: `'manual'` or `'broker'`
- `mode TEXT DEFAULT 'live'` — `'live'`/`'paper'` (everything in #1 is `'live'`; column exists now
  so #2's paper engine writes to the same table)
- `fees REAL` — total regulatory fees for the episode (net P&L)

*(No `status` column on `trades` — open/closed is already `exit_price IS NULL`. Order lifecycle
status belongs on a future `orders` table in #2/#4.)*

**New `positions` table** (live holdings snapshot):
```sql
positions(
  position_id INTEGER PK AUTOINCREMENT, synced_at TEXT NOT NULL, broker TEXT NOT NULL,
  symbol TEXT NOT NULL, quantity REAL NOT NULL, average_buy_price REAL,
  market_value REAL, last_price REAL,
  UNIQUE(broker, symbol)   -- upsert latest; sold-out symbols removed each sync
)
```

**New `account_snapshots` table** (captured each sync; unused in #1, seeded for B/C learning):
```sql
account_snapshots(
  snapshot_id INTEGER PK AUTOINCREMENT, synced_at TEXT NOT NULL, broker TEXT NOT NULL,
  total_equity REAL, buying_power REAL, cash REAL
)
```

---

## 7. Components & Error Handling

**`swing-lab broker-login` (one-time, interactive):** prompts for username / password / 2FA-seed,
stores them in Windows Credential Manager, authenticates once to validate + cache the session
token. The only interactive step; afterward `sync` runs unattended.

**Error handling:**
- **Missing/invalid credentials** → clear, actionable error ("run `swing-lab broker-login`"); no
  raw stack trace; **no secrets ever logged**.
- **API flakiness** (unofficial API) → retry with exponential backoff, reusing the pattern in
  `recommendation.py:240-246`. On persistent failure, **abort cleanly** — no partial writes.
- **Atomic sync** → whole sync in a DB transaction; interruption rolls back. Combined with tracked
  `broker_order_id`s, re-running is always safe (idempotent).
- **Reconciliation mismatch** → positions snapshot wins; discrepancy logged as a warning.
- **Order states** → only `filled` fills imported; `cancelled`/`rejected`/`pending` skipped. Empty
  account / no new fills → graceful no-op summary.

---

## 8. Testing

- **`robin_stocks` is fully mocked** — zero live API calls in the suite (no real credentials, no
  hitting Robinhood). Fixtures mirror real return shapes.
- **Reconstruction is the priority** (the only real algorithm). Cases: simple round-trip;
  scale-in averaging; partial-then-full close; still-open position; back-to-back episodes on one
  symbol; rec matched in-window vs. out-of-window; discretionary (`rec_id` NULL).
- **Idempotency test:** sync twice on same fixtures → no duplicate trades.
- **Reconciliation test:** snapshot vs. reconstruction conflict → snapshot wins + warning.
- DB tests use in-memory SQLite seeded by `init_db()`; auth tests mock `keyring` (verify "missing
  creds → actionable error"), never a real login. Follows existing test setup.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Strategy has no demonstrated edge** (backtest trails SPY) | Goal is explicitly the *system + learning loop*, not returns. #1 is read-only — no money at risk regardless. |
| **Robinhood ToS** — `robin_stocks` is unofficial; automated trading is a gray area, can flag/lock an account | #1 is read-only (lowest risk). Execution sub-projects revisit this with eyes open. |
| **Credential power** — login grants full account access (incl. banking endpoints), not just trading | Code only ever calls read (and later equity-order) endpoints; never banking/ACH. **Primary control: fund the account with a deliberately bounded amount** — caps max loss from bugs *or* a leak. Withdrawals only go to a verified linked bank. |
| **Unattended automation holds money-moving credentials** | Inherent and accepted. Bounded funding + keyring at-rest encryption + (later) per-trade/per-day caps + approval gate for real orders. |
| **Reconstruction errors** (splits/fractional/transfers) | Positions snapshot is authoritative; mismatches flagged, not silently trusted. |

---

## 10. Success Criteria

- [ ] `swing-lab broker-login` stores credentials in Windows Credential Manager and validates a
      live authentication once.
- [ ] `swing-lab sync` imports filled Robinhood orders into `trades` as position-episodes, net of
      fees, matched to `rec_id` where a recommendation exists within 5 trading days.
- [ ] `swing-lab sync` populates the `positions` snapshot; `rebalance`/recommendation filters held
      symbols from real holdings.
- [ ] Re-running `sync` produces no duplicate trades (idempotent).
- [ ] The existing `trade_outcomes` + `postmortem` loop runs on imported real trades unchanged.
- [ ] Full test suite passes with `robin_stocks` mocked; no live API calls.

---

## 11. Future Work (subsequent sub-projects)

- **#2 Paper execution engine** — `orders` table (lifecycle status), simulated fills, full-auto.
- **#3 Learning loop** — extend attribution; later adaptive parameter tuning (B) and a predictive
  model (C), drawing on `account_snapshots` + accumulated graded trades.
- **#4 Live execution** — `place_equity_order` behind a Telegram/phone approval gate + hard caps
  (per-trade $, per-day $, max positions, gate-red precondition, kill switch).
- Live quotes/historicals from the broker client to supplement yfinance where it's spotty
  (pre-market).
