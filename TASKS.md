# Swing Lab — Active Tasks

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
