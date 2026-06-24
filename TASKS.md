# Swing Lab — Active Tasks

## Forward-Projected Exit Targets (COMPLETE ✅ 2026-06-24)

Replace backward-looking 52w-high/swing-high target anchoring with a forward-projected ATR-based target gated on 2:1 reward:risk. Pushed to origin/main.

- [x] Task 1: config constants (`TARGET_ATR_MULTIPLE=3.5`, `TARGET_MIN_REWARD_RISK=2.0`, `TARGET_MIN_UPSIDE_PCT=0.05`) + pure `reward_risk`/`validate_target`/`risks_with_target_flags` + `tests/test_target_validation.py` (commit `8034513`)
- [x] Task 2: wire `validate_target` into `synthesize_pick` after level parsing; surface `weak_rr` in key_risks, `target_recomputed` to run log (commit `feb2770`)
- [x] Task 3: prompt + tool-schema project targets forward, never cap at 52w high; `format_levels_for_prompt` emits projected-target line + `tests/test_levels_prompt.py` (commit `90f2938`)
- [x] Final whole-branch review ("ready to merge, with fixes"); applied the one pre-merge fix — value assertion on projection formula (commit `c31e9c3`)
- [x] Full suite green: 125 passed
- [x] Live verified via `recommend`: ALB target $176.44 (R:R 2.84:1) + APA target $38.11 (R:R 3.55:1) — both forward-looking, neither pinned to 52w high, no weak_rr flags; APA rationale explicitly cites "ATR-based swing target"
- [ ] Still unverified live: the exact original failure case (a momentum leader sitting *at new highs*) hasn't surfaced under the current PARTIAL macro gate (scanner favoring oversold mean-reversion names)

## CLI UTF-8 Encoding Fix (COMPLETE ✅ 2026-06-24, commit `e954c50`)

- [x] `recommend` crashed with `UnicodeEncodeError` (`★` ★) when stdout is piped — Windows defaults pipes to cp1252; reconfigure stdout/stderr to UTF-8 at `cli.main()` entry (guarded + `errors="replace"`). Also fixes mojibake in captured nightly logs. Verified via piped `gate` (em-dash prints). Pushed to origin/main.

## Execution Price Levels & Charts (COMPLETE ✅ 2026-06-17)

Surface each pending buy proposal's entry/support/stop/target levels + a candlestick chart on the Execution page, reusing Recommendation-page components.

- [x] Task 1: `load_recommendation(conn, rec_id)` DB helper + `tests/test_rec_load.py` (commit `7026abe`)
- [x] Task 2: render `zone_kpi_grid_html` + lazy `candle_chart` (in `st.expander`) on pending buys in `pages/7_Execution.py` (commit `beec852`)
- [x] Milestone marked complete + plan tracked (commit `08fd43c`); all pushed to origin/main
- [x] Full suite green: 101 passed
- [ ] Manual browser smoke (user action): Generate proposals during market hours → confirm KPI grid + chart expander render on #1-rec buy; runner-ups show chart only; Approve/Reject don't auto-open expanders
- [ ] Deferred follow-up: live stop/target *tracking* (flag "below stop"/"hit target") on open positions — display-only for now

## Execution Guardrail False-Flag Fixes (COMPLETE ✅ 2026-06-17, commit `2521c39`)

- [x] Fix false "position exceeds max position size": `generate_proposals` now `math.floor`s shares to 6dp so notional can't round above the cap (+ `test_full_size_open_not_flagged_by_rounding`)
- [x] Fix stale "outside regular trading hours": Execution page recomputes guardrails against current state at display time instead of trusting create-time flags
- [x] Tighten `expire_stale` to key off the current ET trading session (not the UTC calendar date) (+ `test_expire_stale_uses_et_session_not_utc_day`)

## Sync-Only Trade Log (COMPLETE ✅ 2026-06-16)

Robinhood sync + paper engine are now the only writers of the trade log.

- [x] Task 1: scope postmortem to strategy trades (`rec_id IS NOT NULL OR mode='paper'`) in `db.load_trades_with_context` + `dashboard/lib.load_trade_outcomes` (+ `test_postmortem_scope.py`)
- [x] Task 2: remove CLI `log open`/`log close` (argparse now rejects them) (+ `test_cli_no_manual_log.py`)
- [x] Task 3: Trade Log page read-only (dropped Open/Close/Edit/Delete tabs + inline buttons); removed Recommendation "Open trade from this pick" button
- [x] Task 4: delete dead `edit_trade`/`delete_trade` from `tradelog.py`
- [x] Task 5: one-time cleanup of phantom manual trade #3 (SNDK dup) — remaining ids [4,5,6,7]
- [x] Task 6: update PLANNING.md milestone table + sub-project #3 section
- [x] Full suite green: 97 passed

Deferred follow-ups (from earlier sub-projects, not blocking):
- [ ] Task 10 idempotency: replace `broker_order_ids_json LIKE` substring scan with indexed column + rollback test
- [ ] Task 6 reconstruction: add interleaved-rebuy / negative-shares edge-case coverage
- [ ] Task 7 rec matching: add window-boundary + same-day tie-break tests
- [ ] Task 9 broker: harden ISO-timestamp comparison + sell-side fill normalization test

## M10 — Conversational Analyst Agent (step 9)

Steps 1–8 complete. One item remaining:

- [x] M10 step 9: final wiring + integration test — connect agent tool loop to live `swing-lab` CLI commands, run end-to-end conversation test with gate + scan context injected

## M14 — Design Audit D1+D2+D3 (COMPLETE ✅ 2026-05-31)

- [x] D1: FS_*/SP_*/RADIUS_*/TRANS constants added to theme.py; TEXT_DIM bumped #7a7e96→#8c8fa8 (WCAG AA); prefers-reduced-motion block in _CSS
- [x] D1: All 8 HTML helper functions swept — magic rem/px values replaced with scale constants
- [x] D1: KPI grid changed from fixed 4-col to responsive auto-fit minmax(140px,1fr)
- [x] D2+D3: FS_BASE + TRANS constants added; all 4 CSS injection blocks (_CSS/_CSS2/_CSS3/_CSS4) fully tokenized
- [x] D2+D3: RADIUS/RADIUS_SM/RADIUS_XS uniform across all Streamlit UI overrides; scrollbar raw hex eliminated

## Trade Log UI Polish (2026-05-31)

- [x] Replace sparkline with full candlestick chart (matching Recommendation page) — `charts.py` shared module
- [x] Add `trade_entry_price` + `trade_entry_date` markers to chart (white dotted hline + vertical vline)
- [x] Extract `_candle_chart` + helpers into `dashboard/charts.py` shared module
- [x] Update `load_open_trades` to LEFT JOIN recommendations for `rec_entry_zone`
- [x] Add `_market_status()` + market status badge (page header + metric column)
- [x] Add portfolio stats bar (# positions, $ deployed, market status dot)
- [x] Remove left-border AI-slop amber card; replace with `st.caption()`
- [x] Inline `30d+` stale badge on symbol; remove redundant bottom warning
- [x] Rename "Remove" → "Close" with better confirmation copy
- [x] Live test with active position data — verify 200px candlestick renders cleanly in narrow column
  - Tested: SNDK open trade (#3, entry $1662.44), 200px chart renders with 4 traces (SMA200/50/20 + candlestick), entry markers confirmed

## M13 — Design polish remaining pages (2026-05-31)

- [x] 1_Macro_Gate.py — replace `st.error()` flags with `risk_row_html` (no jarring red Streamlit boxes)
- [x] 2_Scanner.py — replace `st.warning()` with `risk_row_html`, replace plain `st.dataframe()` with styled HTML table
- [x] 3_Claude_Review.py — replace `st.warning()` cost notice with themed inline block, fix `border-left` → `border-top`
- [x] 6_Postmortem.py — add Layer 6 header, clean empty state, replace `st.dataframe()` with styled HTML table
- [x] 5_Recommendation.py — add company name below ticker (cached yfinance shortName), entry zone shows full range `$lo–$hi` in KPI grid
- [x] theme.py — `zone_kpi_grid_html` now accepts `entry_range=(lo, hi)` to show the full band vs. midpoint only


## M15 — Recommendation Overlays Consistency (COMPLETE ✅ 2026-05-31)

- [x] Switch `synthesize_top_pick` to tool_use (`submit_recommendation` schema) — model can't skip price levels
- [x] Remove `thinking={"type":"adaptive"}` — API rejects it with forced tool_choice
- [x] Increase max_tokens 700→2000 — eliminates truncation before price fields
- [x] Add 5 new DB columns: entry_low, entry_high, support, stop_price, target (REAL) + migrations
- [x] Update `save_recommendations` + `load_latest_recommendations` for new columns
- [x] Rewrite `_parse_zone_levels(rec, price)` — prefers DB columns, text-parse fallback for legacy rows
- [x] Fix key mismatch: `stop` key renamed to `stop_price` in generate_recommendations/compose_runner_up
- [x] Extend `candle_chart()` with explicit level kwargs — skips text-parse when all 5 provided
- [x] Add visible amber warning when overlays unavailable (no more silent hiding)
- [x] Kill lingering stale Python processes; restart dashboard clean
- [x] Verified working end-to-end: stop/target/support/entry zone all render + KPI grid updates
