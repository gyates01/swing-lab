# Swing Lab — 5-Milestone Rollout Plan (Reconstructed)

## Milestone Status

| Milestone | Status | Completed |
|---|---|---|
| Phase 1 — Factor Exposure Analysis | ✅ Complete | (prior session) |
| Phase 2 — Define Your Edge | ✅ Complete | (prior session) |
| M2 Closeout — Phase 2 Obsidian writeback | ✅ Complete | 2026-05-25 |
| M3a — Core scanner + macro gate + CLI + DB | ✅ Complete | 2026-05-25 |
| M3b — Walk-forward backtest | ✅ Complete | 2026-05-25 |
| M3.5 — Full 6-signal macro gate | ✅ Complete | 2026-05-25 |
| M4 — Claude Analyst review layer | ✅ Complete | 2026-05-25 |
| M5 — Trade log + adaptation loop | ✅ Complete | 2026-05-25 |
| M6 — Educational web dashboard (Streamlit) | ✅ Complete | 2026-05-25 |
| M7 — Dashboard refresh buttons + stronger fundamentals | ✅ Complete | 2026-05-26 |
| M8 — Trade Recommendation Engine | ✅ Complete | 2026-05-26 |
| M9 — Trade Outcome Feedback Loop | ✅ Complete | 2026-05-27 |
| M10 — Conversational Analyst Agent | ⏳ Steps 1–8 complete, step 9 pending | 2026-05-28 |
| Automation — Scheduled gate/scan/review | ✅ Complete | 2026-05-30 |
| Chart — Recommendation level labels | ✅ Complete | 2026-05-30 |

---

## Context

The user remembered a "full 5-milestone rollout plan" for the Swing Lab project and believed milestones 1–2 were complete. The terminal building this project was cancelled mid-session, raising concern that work was lost.

**Nothing was lost.** The plan corresponds to the **5-Phase framework** in the Obsidian note `E:\Downloads\Other\Obsidian Vault\Active\Claude for Trading — Methods, Strategies & Personal Framework.md` (lines 206–239), and the codebase confirms Phase 1 + Phase 2 deliverables are present:

- **Phase 1 (Understand What You Own)** — done. `scripts/phase1_factor_exposure.py` is a complete factor-exposure analyzer that writes a "Phase 1 — Factor Exposure (Filled)" block back into the Obsidian note.
- **Phase 2 (Define Your Edge)** — done in code. All edge decisions (12-1 momentum, S&P 500 universe, bi-weekly Sunday rebalance, 8% max position, top-20 picks, top-6 to Claude review, macro gate thresholds 70/40) are committed to `src/swing_lab/config.py`. **Outstanding sub-task:** write a "Phase 2 — Define Edge (Filled)" block to the Obsidian note so the framework note visibly tracks Phase 2 as done (mirroring what Phase 1 does).
- **Phases 3–5** — not yet built. The CLI entry point `swing_lab.cli:main` declared in `pyproject.toml` does not exist; `src/swing_lab/__init__.py` is empty; `data/swing.db` is not created.

This plan reconstructs the detailed rollout for Phases 3–5 (renumbered as Milestones 3–5, with Milestone 3 split into 3a/3b per the user's decision to ship the simple 2-signal macro gate first), and includes the small Phase 2 documentation closeout.

---

## Current State Inventory

| File | Status | Notes |
|---|---|---|
| `pyproject.toml` | done | Declares `swing-lab = "swing_lab.cli:main"` entry point. Deps include `yfinance`, `pandas`, `numpy`, `anthropic`, `matplotlib`, `tabulate`. |
| `src/swing_lab/config.py` | done | All Phase 2 parameters. |
| `src/swing_lab/__init__.py` | empty | Will need package metadata when CLI lands. |
| `scripts/phase1_factor_exposure.py` | done | Phase 1 deliverable. |
| `src/swing_lab/cli.py` | **missing** | Declared but never written. |
| `src/swing_lab/scanner.py` | **missing** | Phase 3 deliverable. |
| `src/swing_lab/macro_gate.py` | **missing** | Phase 3 deliverable. |
| `src/swing_lab/backtest.py` | **missing** | Phase 3 deliverable. |
| `src/swing_lab/review.py` | **missing** | Phase 4 deliverable. |
| `src/swing_lab/tradelog.py` | **missing** | Phase 5 deliverable. |
| `data/swing.db` | **missing** | Created on first run. |

---

## Milestone 2 Closeout — Document Phase 2 in Obsidian

**Goal:** Mirror Phase 1's writeback pattern so the Obsidian framework note has a visible "Phase 2 — Define Edge (Filled)" block.

**Deliverable:** New script `scripts/phase2_define_edge.py` that:
- Reads all relevant constants from `src/swing_lab/config.py`
- Builds a markdown block summarizing the edge decisions:
  - Time horizon: swing (bi-weekly rebalance, 2-week holding implied by `REBALANCE_EVERY_N_WEEKS = 2`)
  - Universe: S&P 500 (from `SP500_URL`)
  - Signal: 12-1 month momentum, sector-relative
  - Macro gate thresholds: full ≥70, partial 40–69, stand down <40
  - Position sizing: 8% max single name, top-20 scanner output, top-6 to Claude
  - Data source: Yahoo Finance via `yfinance`
- Inserts the block into the note after `### Phase 2: Define Your Edge`, idempotently (re-running does not duplicate)
- Checks off `- [ ] Define my time horizon and risk tolerance explicitly` in the Resources checklist

**Reuse:** Copy the `write_to_obsidian` insertion pattern from `scripts/phase1_factor_exposure.py:286–341` (locate marker → find next `###` boundary → insert → mark checklist item as `[x]`).

---

## Milestone 3a — Deterministic Scanner + Simple Macro Gate

**Goal:** End-to-end working scan: fetch universe → compute 12-1 momentum → rank within sector → apply simple 2-signal macro gate → output top 20 candidates as a ranked table.

**Files to create:**

- `src/swing_lab/universe.py` — `fetch_sp500() -> pd.DataFrame[symbol, sector]` that scrapes `SP500_URL` (Wikipedia) via `pd.read_html`. Cache to `data/universe.parquet` with daily TTL.
- `src/swing_lab/scanner.py`:
  - `compute_momentum(symbol, end_date) -> float | None` — reuse the exact 12-1 logic from `scripts/phase1_factor_exposure.py:100–114`. Extract to this module and import from both places to avoid drift.
  - `score_universe(end_date) -> pd.DataFrame` — runs momentum on every S&P 500 name, ranks within GICS sector to a 0–100 percentile score, returns sorted dataframe.
  - `top_n_picks(scored_df, n=TOP_N_PICKS) -> pd.DataFrame` — applies macro gate sizing (1.0 / 0.6 / 0.0) and returns top N.
- `src/swing_lab/macro_gate.py` (simple version):
  - `vix_score() -> float` — fetch `^VIX` via yfinance, score 0–100 where lower VIX = higher score (use 1-year percentile).
  - `breadth_score() -> float` — % of S&P 500 names above their 200-day MA, scored 0–100.
  - `compute_gate() -> dict[score: float, sizing: float, components: dict]` — average of the two signals, then apply `GATE_FULL` / `GATE_PARTIAL` thresholds from config.
- `src/swing_lab/cli.py`:
  - `swing-lab scan` — runs gate + scanner, prints ranked table via `tabulate`.
  - `swing-lab gate` — prints just the macro gate breakdown.
  - Uses `argparse` (no extra deps).
- `src/swing_lab/__init__.py` — minimal `__version__ = "0.1.0"`.
- `src/swing_lab/db.py` — SQLite schema init for `data/swing.db`. Tables: `scans(scan_id, run_at, gate_score, sizing)`, `scan_picks(scan_id, symbol, sector, momentum, rank, score)`. Scans persisted on every `swing-lab scan` run.

**Verification:**
1. `uv sync` succeeds.
2. `uv run swing-lab gate` prints VIX + breadth components and a final score/sizing.
3. `uv run swing-lab scan` prints a 20-row table of top momentum picks. Manually spot-check 2–3 names against `yf.Ticker(sym).history()` 12-1 returns.
4. `data/swing.db` exists with `scans` and `scan_picks` populated.
5. Re-run scanner — second row in `scans` table, no schema errors.

---

## Milestone 3b — Walk-Forward Backtest

**Goal:** Validate the Milestone 3a system on historical data so we know if the deterministic edge is real before adding Claude on top.

**Files to create:**

- `src/swing_lab/backtest.py`:
  - `walk_forward(start='2015-01-01', end='2024-12-31', rebalance_weeks=2) -> pd.DataFrame` — at each rebalance date: compute scores using data only available up to that date, take top 20, equal-weight or score-weight, hold until next rebalance.
  - `report(returns_df) -> dict` — total return, annualized return, Sharpe, max drawdown, hit rate, vs. SPY benchmark.
  - `plot_equity_curve(returns_df, out_path)` — matplotlib chart saved to `data/reports/backtest_{date}.png`.
- `src/swing_lab/cli.py` additions: `swing-lab backtest [--start --end]`.

**Verification:**
1. `uv run swing-lab backtest` produces a printed report and equity curve PNG in `data/reports/`.
2. Sharpe and max drawdown numbers are plausible (Sharpe ~0.5–1.5 expected for a basic momentum strategy; if Sharpe > 2 something is leaking future data).
3. Walk-forward correctness check: pick one rebalance date, confirm scores at that date use only `data[:date]`.

---

## Milestone 3.5 — Extend Macro Gate to Full 6-Signal Version

**Goal:** Upgrade `macro_gate.py` from 2 signals to the full 6-signal Three-Layer System spec (Obsidian note lines 118–136).

**Changes:**

Add to `src/swing_lab/macro_gate.py`:
- `vix_term_structure_score()` — front-month vs. 3-month VIX futures (use `^VIX` vs. `^VIX3M` from yfinance).
- `credit_spread_score()` — HYG yield minus IEF (or TLT) yield as a proxy for HY-Treasury spread.
- `put_call_score()` — fetch CBOE total put/call ratio (consider `pandas_datareader` or scrape if yfinance lacks it; fallback: skip with warning).
- `factor_crowding_score()` — rolling correlation between MTUM and VLUE ETF returns.
- Update `compute_gate()` to average all 6 signals.

**Verification:**
1. `uv run swing-lab gate` prints all 6 components.
2. Backtest re-runs cleanly with the new gate (re-run Milestone 3b verification).
3. Compare backtest stats with 2-signal vs. 6-signal gate — record both in `data/reports/`.

---

## Milestone 4 — Claude Analyst Review Layer

**Goal:** Layer 3 of the Three-Layer System. Take top 6 (`REVIEW_TOP_N`) candidates from the scanner, fetch fundamentals, send to Claude, blend Claude's 1–10 scores with quant rank (60/40 quant/Claude).

**Files to create:**

- `src/swing_lab/fundamentals.py` — for each symbol, pull last 4 quarters of revenue, free cash flow, gross/operating margins, debt-to-equity from `yf.Ticker(sym).quarterly_financials` and `.quarterly_balance_sheet`. Returns a compact dict per symbol.
- `src/swing_lab/review.py`:
  - System prompt: Claude is a buyside analyst scoring each candidate 1–10 on earnings quality, growth, balance sheet, margins, red flags. Use the structure from Obsidian note lines 256–264.
  - Use `anthropic.Anthropic()` client. Model: latest available Sonnet (resolve at call time, e.g. `claude-sonnet-4-6`).
  - Enable prompt caching: cache the system prompt + the methodology/criteria block; only the candidate-specific fundamentals vary per call.
  - Use structured output: ask for JSON with `{symbol, scores: {earnings_quality, growth, balance_sheet, margins}, red_flags: [...], composite_1_to_10, one_line_summary}`.
  - `review_candidates(top_n_df) -> pd.DataFrame` — calls Claude once per symbol (or batched if SDK supports), returns df with Claude scores joined.
  - `blend(quant_score, claude_score, w_quant=0.6, w_claude=0.4) -> float`.
- `src/swing_lab/cli.py` additions: `swing-lab review` — runs scan → review → prints blended-ranked final picks. Persists to `swing.db` table `reviews(scan_id, symbol, claude_score, blended_score, red_flags_json, claude_summary)`.
- API key: read from `ANTHROPIC_API_KEY` env var; fail with clear message if missing.

**Reuse:** Follow guidance from the `claude-api` skill — prompt caching, latest model, structured output. The skill should be invoked when implementing this milestone.

**Verification:**
1. `uv run swing-lab review` prints top-6 with both quant and Claude columns.
2. Spot-check one Claude response: does the red-flag list make sense for a name with known issues?
3. Re-run within 5 minutes — confirm prompt-cache hit (the SDK exposes cache token usage in `response.usage`).
4. `reviews` table populated; query and confirm row count matches `REVIEW_TOP_N`.

---

## Milestone 5 — Trade Log + Adaptation Loop

**Goal:** Close the loop. Log every position taken (with thesis), every exit (with outcome), and run a periodic Claude review of recent trades looking for patterns.

**Files to create:**

- `src/swing_lab/tradelog.py`:
  - SQLite tables: `trades(trade_id, opened_at, closed_at, symbol, side, shares, entry_price, exit_price, scan_id, claude_review_id, thesis_text, exit_reason, pnl, pnl_pct)`.
  - `open_trade(symbol, shares, entry_price, scan_id, thesis)` — records entry.
  - `close_trade(trade_id, exit_price, exit_reason)` — records exit, computes P&L.
  - `recent_trades(n=20) -> pd.DataFrame`.
- `src/swing_lab/cli.py` additions:
  - `swing-lab log open SYM SHARES PRICE --thesis "..."`
  - `swing-lab log close TRADE_ID PRICE --reason "..."`
  - `swing-lab log list [--limit 20]`
  - `swing-lab postmortem [--last 20]` — sends recent trades to Claude with the pattern-analysis prompt from Obsidian line 238, prints insights, optionally writes a "Trade Log Review {date}" file to `OBSIDIAN_SWING_LAB_DIR`.
- `src/swing_lab/cli.py` cap: `swing-lab rebalance` — combined macro gate → scan → review → diff vs. current open trades → suggest opens/closes (does NOT execute orders).

**Verification:**
1. Manually log 3 fake trades, then `swing-lab log list` shows them.
2. Close one, confirm P&L computed.
3. `swing-lab postmortem` returns Claude analysis; sample-check it for relevance.
4. `swing-lab rebalance` produces a diff (open new X, close Y) without erroring.

---

## Critical Files to Modify or Create

```
H:\Other\Claude Projects\Swing Lab\
├── pyproject.toml                          (modify: add deps if needed for M5)
├── src/swing_lab/
│   ├── __init__.py                         (modify: add __version__)
│   ├── config.py                           (existing — no changes expected)
│   ├── cli.py                              (new — grows across milestones)
│   ├── universe.py                         (new — M3a)
│   ├── scanner.py                          (new — M3a, extracts momentum from phase1 script)
│   ├── macro_gate.py                       (new — M3a, extended in M3.5)
│   ├── backtest.py                         (new — M3b)
│   ├── fundamentals.py                     (new — M4)
│   ├── review.py                           (new — M4)
│   ├── tradelog.py                         (new — M5)
│   └── db.py                               (new — M3a, schema grows across milestones)
└── scripts/
    ├── phase1_factor_exposure.py           (existing — no changes)
    └── phase2_define_edge.py               (new — M2 closeout)
```

Obsidian note edits (idempotent inserts only):
- `Claude for Trading — Methods, Strategies & Personal Framework.md` — Phase 2 block insert via `scripts/phase2_define_edge.py`.
- `E:\Downloads\Other\Obsidian Vault\Active\Swing Lab\` — directory does not exist yet; create lazily on first `postmortem` writeback (M5).

---

## Existing Functions to Reuse (Do Not Re-Derive)

- `compute_momentum` — `scripts/phase1_factor_exposure.py:100–114`. Extract verbatim into `src/swing_lab/scanner.py` and import back into the phase1 script.
- `fetch_yf_info` — `scripts/phase1_factor_exposure.py:79–97`. Useful in `fundamentals.py` for sector/industry lookups.
- `write_to_obsidian` pattern — `scripts/phase1_factor_exposure.py:286–341`. Idempotent marker-based insertion. Reuse the structure for the Phase 2 writeback and the M5 postmortem writeback.
- Config constants — all gate, sizing, and rebalance parameters already live in `src/swing_lab/config.py`. Import, don't re-declare.

---

---

## Milestone 6 — Educational Web Dashboard

**Goal:** Streamlit dashboard at `localhost:8501` that walks through the Three-Layer System visually. Educational descriptions on each page pair raw `swing.db` data with plain-English explanations. Trade logging via UI (no terminal required).

**New command:** `uv run swing-lab dashboard [--port 8501]`

**Schema addition:** `gate_runs` table — persists every `swing-lab gate` run with all 6 component scores so the dashboard can show gate history.

**Files to create:**
- `src/swing_lab/dashboard/__init__.py`
- `src/swing_lab/dashboard/lib.py` — DB helpers, GATE_DESCRIPTIONS, formatters
- `src/swing_lab/dashboard/app.py` — landing page with workflow overview
- `src/swing_lab/dashboard/pages/1_Macro_Gate.py` — Layer 1: gate score + 6 components + history chart + "Run Gate Now"
- `src/swing_lab/dashboard/pages/2_Scanner.py` — Layer 2: scan_picks, sector breakdown, momentum histogram
- `src/swing_lab/dashboard/pages/3_Claude_Review.py` — Layer 3: blended scores, red flags, quant vs. Claude rank comparison
- `src/swing_lab/dashboard/pages/4_Trade_Log.py` — open/close/edit/delete trades via forms

**Files to modify:**
- `pyproject.toml` — add `streamlit>=1.40`
- `src/swing_lab/db.py` — add `gate_runs` table + `save_gate_run()`
- `src/swing_lab/cli.py` — modify `_cmd_gate` to persist runs; add `_cmd_dashboard`
- `src/swing_lab/tradelog.py` — add `edit_trade()` + `delete_trade()`

**Milestone Status Sub-tasks:**

| Sub-task | Status |
|---|---|
| Schema + persistence (gate_runs, save_gate_run, _cmd_gate update) | ✅ Done |
| tradelog.py edit_trade + delete_trade | ✅ Done |
| dashboard/lib.py | ✅ Done |
| dashboard/app.py landing page | ✅ Done |
| Page 1 — Macro Gate | ✅ Done |
| Page 2 — Scanner | ✅ Done |
| Page 3 — Claude Review | ✅ Done |
| Page 4 — Trade Log | ✅ Done |
| CLI subcommand + pyproject dep | ✅ Done |
| uv sync (streamlit install) | ✅ Done |
| Visual overhaul — Warm Graphite theme + Plotly charts | ✅ Done |
| Inline Remove buttons on open positions table | ✅ Done |
| CSS bug fixes (keyboard_double, tab overlap) | ✅ Done |
| Claude Review narrative + score guide | ✅ Done |
| Trade log — allow 0 entry price for existing holds | ✅ Done |

---

## End-to-End Verification (After All Milestones)

```bash
uv sync
uv run swing-lab gate          # M3a + M3.5
uv run swing-lab scan          # M3a
uv run swing-lab backtest      # M3b
uv run swing-lab review        # M4
uv run swing-lab log open NVDA 10 450 --thesis "top momentum + Claude 8/10"
uv run swing-lab log list
uv run swing-lab postmortem    # M5
uv run swing-lab rebalance     # M5 — combined flow
```

After full run:
- `data/swing.db` contains `scans`, `scan_picks`, `reviews`, `trades` tables with data.
- `data/reports/` contains backtest equity curve PNG.
- Obsidian note has both "Phase 1 — Factor Exposure (Filled)" and "Phase 2 — Define Edge (Filled)" blocks.
- `OBSIDIAN_SWING_LAB_DIR` contains at least one postmortem markdown file.

---

## Milestone 7 — Dashboard Refresh Buttons + Stronger Fundamentals

**Goal:** Make the dashboard self-sufficient (refresh buttons on the three data-driven pages), and tighten the fundamentals fetch so Revenue YoY growth stops coming back `None`.

### Milestone Status

| Sub-task | Status |
|---|---|
| A: Strengthen `fundamentals.py` fallback chain + `data_quality` | ✅ Complete |
| B: Progress callbacks in `scanner.score_universe` and `review.review_candidates` | ✅ Complete |
| C: New `dashboard/actions.py` — `refresh_gate/scan/review` | ✅ Complete |
| D: Macro Gate — state-aware "Run gate" / "Refresh today's gate" button | ✅ Complete |
| E: Scanner — "Run new scan" button + progress bar | ✅ Complete |
| F: Claude Review — "Run new review" button + two-phase progress | ✅ Complete |

### Files to Modify

| File | Change |
|---|---|
| `src/swing_lab/fundamentals.py` | Add `income_stmt` + `info.revenueGrowth` fallbacks; return `data_quality`; fix silent `pass` |
| `src/swing_lab/scanner.py` | Add `progress` callback param to `score_universe` |
| `src/swing_lab/review.py` | Add `progress` callback param; pass `data_quality` into Claude prompt |
| `src/swing_lab/dashboard/actions.py` | **NEW** — `refresh_gate`, `refresh_scan`, `refresh_review` |
| `src/swing_lab/dashboard/pages/1_Macro_Gate.py` | Replace "Run Gate Now" with state-aware button + "Today: N run" caption |
| `src/swing_lab/dashboard/pages/2_Scanner.py` | "Run new scan" button + progress bar |
| `src/swing_lab/dashboard/pages/3_Claude_Review.py` | "Run new review" button + two-phase progress + cost warning |

---

## Milestone 8 — Trade Recommendation Engine

**Goal:** Close the gap between "what does Claude think?" and "what should I actually buy today at what size?" — a single page that synthesizes gate + scan + review into 3 concrete recommendations with sizing, rationale, and risks.

### Milestone Status

| Step | Status | Completed |
|---|---|---|
| 1. `config.py` — RECOMMEND_TOP_N, RECOMMEND_RED_FLAG_MAX | ✅ Complete | 2026-05-26 |
| 2. `recommendation.py` — engine module (pure functions) | ✅ Complete | 2026-05-26 |
| 3. `db.py` — recommendations table + save/load functions | ✅ Complete | 2026-05-26 |
| 4. `actions.py` — refresh_recommend wrapper | ✅ Complete | 2026-05-26 |
| 5. `cli.py` — swing-lab recommend subcommand | ✅ Complete | 2026-05-26 |
| 6. `5_Recommendation.py` — dashboard page + app.py nav | ✅ Complete | 2026-05-26 |
| 7. End-to-end verification | ✅ Complete | 2026-05-28 — two recommendation batches in DB (2026-05-27 + 2026-05-28T18:18) |

---

## Milestone 9 — Trade Outcome Feedback Loop

**Goal:** Close the backward loop: link trades to recs, capture structured outcome data at close time (thesis validated? which risks materialized? which exit triggers fired?), and upgrade the postmortem to compare predictions to outcomes.

### Milestone Status

| Step | Status | Completed |
|---|---|---|
| 1. DB schema: `rec_id` FK on trades + `trade_outcomes` + `postmortems` tables | ✅ Complete | 2026-05-27 |
| 2. Extend `tradelog.open_trade` / `close_trade` with `rec_id` and `outcome` | ✅ Complete | 2026-05-27 |
| 3. DB helpers: `save_trade_outcome`, `load_trade_outcome`, `load_trades_with_context`, postmortem save/load | ✅ Complete | 2026-05-27 |
| 4. Dashboard: "Open trade from this pick" button on Recommendation page | ✅ Complete | 2026-05-27 |
| 5. Dashboard: structured outcome capture in Close Position tab | ✅ Complete | 2026-05-27 |
| 6. Rewrite `postmortem.py` with prompt caching + structured input + persistence | ✅ Complete | 2026-05-27 |
| 7. New `6_Postmortem.py` dashboard page + landing nav update | ✅ Complete | 2026-05-27 |
| 8. CLI: `swing-lab log close` outcome flags + `swing-lab postmortem` persistence | ✅ Complete | 2026-05-27 |
| 9. End-to-end verification | ⏳ Partial — "open from rec" verified (trade #3 SNDK, rec_id=4). Close-with-outcome and postmortem legs pending real trade closure. | |

---

## Milestone 10 — Conversational Analyst Agent

**Goal:** Add a persistent sidebar chat widget powered by Claude with tool use. Multi-turn conversation memory, dynamic ticker lookups for any symbol (not just S&P 500), optional deep-dive review on demand, and read access to all `swing.db` data. Bundles two incidental fixes: emoji removal across the dashboard and local-time display for all timestamps.

Also bundles three Trade Log UI improvements discovered during M10 planning: form field reset after submission, partial share decimal precision, and a live trade-value calculator.

### Milestone Status

| Step | Status |
|---|---|
| 1. Config hoist — `MODEL`, `ANALYST_MAX_TURNS`, `ANALYST_SNAPSHOT_TTL_SECONDS` | ✅ Complete 2026-05-28 |
| 2. DB migration — `analyst_sessions` table + save/load helpers | ✅ Complete 2026-05-28 |
| 3. `fmt_local_time` helper in `lib.py` | ✅ Complete 2026-05-28 |
| 4. `snapshot.py` — `build_snapshot(current_page, visible_df) -> dict` | ✅ Complete 2026-05-28 |
| 5. `analyst.py` — tool definitions, dispatcher, multi-turn loop, retry, cache telemetry | ✅ Complete 2026-05-28 |
| 6. `theme.py` — `_CSS3` chunk + replace `⚠` at `:103` with `[!]` | ✅ Complete 2026-05-28 |
| 7. `sidebar_chat.py` — Streamlit renderer with `render()` entry point | ✅ Complete 2026-05-28 |
| 8. Page-by-page edits — page name, `sidebar_chat.render()`, timestamps, emojis, Trade Log UI fixes | ✅ Complete 2026-05-28 |
| 8a. Bug fix — sidebar Del button for saved analyst sessions | ✅ Complete 2026-05-28 |
| 8b. Bug fix — Est. Value column in Open Positions table | ✅ Complete 2026-05-28 |
| 9. End-to-end browser verification | ⏳ Partial — 9/13 items verified (DB evidence + emoji audit). Browser checklist for remaining 4: lookup_ticker, query_trade_log, load/delete session, recompute_gate, multi-turn context, Open Trade form reset, Est. Value col, cache telemetry. | |

### Architecture

**Hybrid context model:**
- **Cached project snapshot** in the system prompt: latest gate score + components, top 10 scan picks, open trades summary, recent postmortem summary, current page name + visible DataFrame. Wrapped in `cache_control: {"type": "ephemeral"}` so rapid follow-up turns hit the prompt cache.
- **Targeted tools** for dynamic lookups only — Claude calls these when the question demands fresh or off-snapshot data.

**Multi-turn loop in `analyst.run_turn`:**
1. Send `messages = history + [user_msg]` with `tools=TOOLS` and the cached snapshot system block.
2. If `stop_reason == "tool_use"` → execute the tool(s), append `tool_result` blocks, re-send.
3. If `stop_reason == "end_turn"` → return assistant text + updated history.
4. Cap at `ANALYST_MAX_TURNS = 5` to prevent runaways.
5. Retry on 529/503/502 mirrors `postmortem.py:94-114` exactly (5 attempts, exponential backoff).
6. Cache telemetry: log `[analyst: cache hit — N tokens]` and surface as a small caption.

### New Files

| File | Purpose |
|---|---|
| `src/swing_lab/analyst.py` | Core agent — `run_turn(history, user_msg, snapshot) -> (assistant_text, updated_history, telemetry)`. Tool-use loop, retries, cache telemetry. Pure logic, no Streamlit imports. |
| `src/swing_lab/dashboard/sidebar_chat.py` | Streamlit renderer for the sidebar widget. Single entry point: `render()`. Called from `app.py` and every page. |
| `src/swing_lab/dashboard/snapshot.py` | `build_snapshot(current_page: str, visible_df: pd.DataFrame | None) -> dict`. Reads from `lib.py` helpers. |

### Modified Files

| File | Change |
|---|---|
| `src/swing_lab/config.py` | Hoist `MODEL = "claude-opus-4-7"` (currently hardcoded at `review.py:12`, `postmortem.py:7`, `recommendation.py:10`). Add `ANALYST_MAX_TURNS = 5`, `ANALYST_SNAPSHOT_TTL_SECONDS = 300`. |
| `src/swing_lab/review.py`, `postmortem.py`, `recommendation.py` | Replace local `MODEL = ...` with `from swing_lab.config import MODEL`. |
| `src/swing_lab/db.py` | Add `analyst_sessions(session_id PK, saved_at, title, messages_json, snapshot_json)`. Add `save_analyst_session()`, `load_analyst_sessions()`, `load_analyst_session(session_id)`. Safe `CREATE TABLE IF NOT EXISTS`. |
| `src/swing_lab/dashboard/lib.py` | Add `fmt_local_time(ts) -> str` using `datetime.astimezone()`. Add `load_analyst_session_list()` and `load_analyst_session_messages()` thin wrappers. |
| `src/swing_lab/dashboard/theme.py` | Append `_CSS3` chunk with `.sl-chat-msg`, `.sl-chat-meta`, `.sl-chat-input` overriding the `[data-testid="stSidebar"] *` wildcard at `:247`. Do NOT modify `_CSS` or `_CSS2` (Streamlit 1.57 HTML-block size limit). Replace `⚠` literal at `:103` with `"[!]"`. |
| `src/swing_lab/dashboard/app.py` | Set `st.session_state["current_page"] = "home"` at top. Add `sidebar_chat.render()`. Replace `str(row["run_at"])[:16]` at lines 42, 56 with `fmt_local_time(...)`. |
| `src/swing_lab/dashboard/pages/1_Macro_Gate.py` | Page name + `sidebar_chat.render()`. Replace `str(latest["run_at"])[:16] + " UTC"` at `:41`, `:58` with `fmt_local_time(...)`. |
| `src/swing_lab/dashboard/pages/2_Scanner.py` | Page name + `sidebar_chat.render()`. Replace `str(row.run_at)[:16]` at `:83` with `fmt_local_time(...)`. |
| `src/swing_lab/dashboard/pages/3_Claude_Review.py` | Page name + `sidebar_chat.render()`. Replace `str(...)[:16] + " UTC"` at `:54`, `str(row.run_at)[:16]` at `:109` with `fmt_local_time(...)`. |
| `src/swing_lab/dashboard/pages/4_Trade_Log.py` | Page name + `sidebar_chat.render()`. Timestamp fixes at `:82`, `:273`, `:324`. Emoji/stale fixes. **Trade Log UI fixes** (see below). |
| `src/swing_lab/dashboard/pages/5_Recommendation.py` | Page name + `sidebar_chat.render()`. Remove `page_icon="📈"`. Replace `★ TOP RECOMMENDATION` with `>> TOP RECOMMENDATION`. Replace `icon="⚠️"` with `:material/warning:` or drop. Replace `📭` with text. |
| `src/swing_lab/dashboard/pages/6_Postmortem.py` | Page name + `sidebar_chat.render()`. Remove `page_icon="🔬"`. Replace `icon="⚠️"`, `🔬` with text. Fix timestamps at `:33`, `:75`, `:85`. |

### Trade Log UI Fixes (bundled into Step 8)

Three specific improvements to `4_Trade_Log.py`:

**1. Form field reset after successful submission**

After a trade is saved, `st.rerun()` clears `open_from_rec` (so symbol resets), but shares/entry_price/thesis/scan_link persist because Streamlit keeps widget state under auto-generated keys. Fix: introduce an `open_trade_form_v` version counter in session state. Increment it after successful submission. Use it as a suffix on all widget keys inside the form. When the key changes, Streamlit creates fresh widgets with default values.

```python
_form_v = st.session_state.get("open_trade_form_v", 0)
with st.form(f"open_trade_form_{_form_v}"):
    shares = c2.number_input("Shares", key=f"shares_{_form_v}", ...)
    ...
# on success:
st.session_state["open_trade_form_v"] = _form_v + 1
st.rerun()
```

**2. Partial share decimal precision**

Current: `step=1.0, format="%.2f"` in the Open Trade form forces integer-step increments. Open Positions table shows `{row.shares:.0f}` which hides fractional shares entirely.

Fix:
- Form input: `step=0.001, format="%.4f"` — allows 0.001 share increments, shows 4 decimal places
- Open Positions table (`:332`): change `{row.shares:.0f}` to `{row.shares:g}` — shows significant figures without trailing zeros (e.g. `10`, `0.5`, `1.2345`)
- Close trade form selector (`:119`): same `.0f` → `:g` pattern for consistency

**3. Live trade value calculator**

Inside the Open Trade form, after the shares/entry_price inputs are assigned, add a `st.caption` showing the computed trade value. Streamlit evaluates widget values during render, so this works live (updates each time the user changes either field):

```python
if entry_price > 0 and shares > 0:
    st.caption(f"Estimated trade value: ${shares * entry_price:,.2f}")
```

Place this just before the thesis text area.

### Tool Definitions

```python
TOOLS = [
    {"name": "lookup_ticker", "description": "Fetch lightweight factor data for any stock ticker — momentum (12-1), fundamentals (revenue YoY, FCF, margins, D/E), sector. Use for routine 'what's going on with X' questions.", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "deep_dive_ticker", "description": "Run the full Claude analyst review pipeline on a single ticker — 1-10 scores, red flags. ~10s, uses API tokens. Only use when user explicitly asks for a deep dive.", "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "query_trade_log", "description": "Query the user's trade history with optional outcome data.", "input_schema": {"type": "object", "properties": {"status": {"type": "string", "enum": ["open", "closed", "all"]}, "symbol": {"type": "string"}, "last_n": {"type": "integer"}}}},
    {"name": "query_postmortems", "description": "Retrieve recent postmortem analyses.", "input_schema": {"type": "object", "properties": {"last_n": {"type": "integer"}}}},
    {"name": "recompute_gate", "description": "Run a fresh macro gate computation. Use when user asks if conditions have changed.", "input_schema": {"type": "object", "properties": {}}},
]
```

Tool implementations reuse existing functions:
- `lookup_ticker` → `scanner.compute_momentum` + `fundamentals.get_fundamentals`
- `deep_dive_ticker` → `review.review_candidates(single_symbol_df)` — persists to `reviews` table
- `query_trade_log` → `lib.load_trades` + `lib.load_trade_outcome_context`
- `query_postmortems` → `lib.load_latest_postmortem` + new `load_postmortems(last_n)` helper
- `recompute_gate` → `actions.refresh_gate()`

Each tool wraps its body in try/except; on failure returns `{"error": "<message>"}` so Claude apologizes and continues.

### Project Snapshot Structure

```python
{
    "as_of": "2026-05-28T14:30:00Z",
    "gate": {"score": 62.3, "sizing": "partial", "components": {...6 signals...}},
    "scan": {"scan_id": 47, "run_at": "...", "top_10": [{"symbol": "NVDA", "sector": "Tech", "momentum": 0.42, "rank": 1}, ...]},
    "open_trades": {"count": 3, "symbols": ["NVDA", "AVGO", "META"], "unrealized_pnl_pct": 4.2},
    "recent_postmortem": {"created_at": "...", "summary_first_500_chars": "..."},
    "page_context": {"current_page": "scanner", "visible_data": "[serialized top-20 or null]"},
}
```

### UI Layout (sidebar)

```
┌─────────────────────────┐
│ Analyst                 │
│ ─────────────────────── │
│ [Saved chats ▼] [Load]  │
│ ─────────────────────── │
│ ┌─────────────────────┐ │
│ │ chat history scroll │ │
│ └─────────────────────┘ │
│ [Type a question...]    │  <- st.chat_input
│ ─────────────────────── │
│ Deep dive: [SYM ▼] [Go] │
│ [Save chat] [Clear]     │
│ cache hit · 4.2k tokens │
└─────────────────────────┘
```

Session state keys (all prefixed `analyst_` to avoid collision):
- `analyst_history: list[dict]` — conversation turns
- `analyst_last_telemetry: dict` — `{cache_hit: bool, tokens: int, tool_calls: list[str]}`
- `analyst_snapshot_built_at: datetime` — for TTL
- `current_page: str` — set by each page at top of file

### Reuse Map

| Need | Function | Location |
|---|---|---|
| Anthropic client + retry | inline pattern | mirror `postmortem.py:94-114` |
| Prompt caching block | inline pattern | mirror `postmortem.py:100-105` |
| Cache telemetry | inline pattern | mirror `postmortem.py:116-127` |
| Ticker-agnostic momentum | `compute_momentum(symbol, end_date)` | `scanner.py` |
| Ticker-agnostic fundamentals | `get_fundamentals(symbol)` | `fundamentals.py:27` |
| Deep dive pipeline | `review_candidates(df)` | `review.py` |
| Trade log read | `load_trades`, `load_trade_outcome_context` | `lib.py:139,183` |
| Gate refresh | `refresh_gate()` | `actions.py:14` |

### Verification

1. `uv sync` succeeds.
2. Sidebar shows Analyst widget on every page.
3. "What's in the scanner right now?" → answers from snapshot, no tool call, cache hit on follow-up.
4. "Look up TSLA" → `lookup_ticker` fires, answer cites TSLA momentum + fundamentals.
5. Deep-dive button (TSLA) → `deep_dive_ticker` fires, new row in `reviews` table.
6. "What patterns are in my recent trades?" → `query_trade_log` + `query_postmortems` fire.
7. Multi-turn: "Why is NVDA ranking high?" → "What are the biggest risks?" — second turn knows context.
8. Save chat → row in `analyst_sessions`. Clear → empties. Load saved → restores.
9. Timestamps show local time (no UTC suffix). Compare raw DB value to confirm offset.
10. No emoji codepoints in `dashboard/` directory.
11. Open Trade form: after successful log, all fields reset (not just symbol).
12. Shares input allows fractional values; Open Positions table shows them with correct decimal places.
13. Trade value calculator appears in Open Trade form when both shares and price are non-zero.

### Risk Notes

- **CSS wildcard at `theme.py:247`** recolors all sidebar text. Mitigated by `.sl-chat-msg` overrides in `_CSS3`. Verify in browser.
- **Streamlit 1.57 HTML-block size**: `_CSS` and `_CSS2` already split. `_CSS3` must be a separate chunk — do not append to existing chunks.
- **Local time formatter**: uses system tz via `datetime.astimezone()`. Single-user local dashboard; out of scope for server deployments.
- **`deep_dive_ticker` cost**: ~$0.02/call. Gated behind explicit user intent. System prompt tells Claude to prefer `lookup_ticker` first.
- **Form version counter**: the `open_trade_form_v` key must be initialized before the form renders, and incremented (not just set to 0) on success, otherwise the form never gets different widget keys across reruns.
