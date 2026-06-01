# Swing Lab — Planning

## Overview
Python CLI trading research tool built across 12 milestones. Covers the full swing trading workflow: factor exposure analysis, edge definition, momentum scanner, macro gate, walk-forward backtest, Claude review layer, trade log, post-mortem, Streamlit dashboard, and conversational analyst agent. All milestones shipped except M10 step 9.

_Full implementation step details (now executed) archived in `PLAN.md`. That file can be deleted when no longer needed as a reference._

## Milestone Status

| Milestone | Description | Status | Completed |
|---|---|---|---|
| Phase 1 | Factor exposure analysis, Obsidian writeback | ✅ Complete | (prior session) |
| Phase 2 | Edge definition, config.py, Phase 2 Obsidian writeback | ✅ Complete | 2026-05-25 |
| M3a | Core scanner + simple macro gate (2-signal) + CLI + SQLite DB | ✅ Complete | 2026-05-25 |
| M3b | Walk-forward backtest | ✅ Complete | 2026-05-25 |
| M3.5 | Full 6-signal macro gate (VIX, SPY trend, HYG, yield curve, breadth, VIX term) | ✅ Complete | 2026-05-25 |
| M4 | Claude Analyst review layer (top-6 candidates via API) | ✅ Complete | 2026-05-25 |
| M5 | Trade log + adaptation loop (open/close/list/postmortem) | ✅ Complete | 2026-05-25 |
| M6 | Streamlit educational dashboard | ✅ Complete | 2026-05-25 |
| M7 | Dashboard refresh buttons + stronger fundamentals signals | ✅ Complete | 2026-05-26 |
| M8 | Trade Recommendation Engine | ✅ Complete | 2026-05-26 |
| M9 | Trade Outcome Feedback Loop | ✅ Complete | 2026-05-27 |
| M10 | Conversational Analyst Agent (steps 1–8 complete; step 9 pending) | ✅ Complete | 2026-05-31 |
| Automation | Scheduled gate/scan/review | ✅ Complete | 2026-05-30 |
| Chart | Recommendation level labels on charts | ✅ Complete | 2026-05-30 |
| M11 | Dashboard visual rehaul (floating chat, ticker hero, bull/bear split, zone KPIs, topbar) | ✅ Complete | 2026-05-31 |
| M12 | Trade Log design pass + shared charts module + market status indicator | ✅ Complete | 2026-05-31 |
| M13 | Design polish pass — remaining dashboard pages (Macro Gate, Scanner, Claude Review, Postmortem) | ✅ Complete | 2026-05-31 |
| M14 | Design audit D1+D2+D3 — type/spacing/radius/transition token system in theme.py, TEXT_DIM contrast fix, prefers-reduced-motion, KPI grid responsive. Score: 61→83/100 | ✅ Complete | 2026-05-31 |
| M15 | Recommendation overlays consistency — switch to tool_use structured output, persist price levels as DB columns, dashboard prefers columns over text-parse, visible warning on failure | ✅ Complete | 2026-05-31 |

---

## Phase 1 — Factor Exposure Analysis
Analyzes current portfolio factor exposures (momentum, value, quality, size, volatility). Writes "Phase 1 — Factor Exposure (Filled)" block back into the Obsidian strategy note. Script: `scripts/phase1_factor_exposure.py`.

---

## Phase 2 — Edge Definition
All edge parameters committed to `src/swing_lab/config.py`: 12-1 month momentum signal, S&P 500 universe, bi-weekly Sunday rebalance, 8% max position, top-20 scanner output, top-6 to Claude review, macro gate thresholds (full ≥70, partial 40–69, stand down <40). Obsidian writeback: `scripts/phase2_define_edge.py`.

---

## M3a — Scanner + Gate + CLI
`swing-lab gate`, `swing-lab scan` operational. Simple 2-signal gate. SQLite DB initialized. Ranked momentum table output.

---

## M3b — Walk-Forward Backtest
`swing-lab backtest`: rolling window validation of 12-1 momentum signal across historical data. Performance metrics vs SPY benchmark.

---

## M3.5 — Full 6-Signal Macro Gate
Expanded from 2 to 6 signals: VIX level, SPY 200-day trend, HYG credit spread, yield curve slope, market breadth (% above 200MA), VIX term structure. Composite score 0–100.

---

## M4 — Claude Analyst Review
`swing-lab review`: top-6 candidates from scanner fed to Claude via Anthropic SDK. Returns structured analysis (thesis, risks, conviction) per ticker. Prompt caching used for efficiency.

---

## M5 — Trade Log + Adaptation Loop
`swing-lab log open/close/list`, `swing-lab postmortem`: SQLite trade log. Claude pattern analysis across closed trades identifies systematic edge or drift.

---

## M6 — Streamlit Dashboard
Educational/review UI: macro gate components, top picks, trade history, P&L chart. Local only (`streamlit run`).

---

## M7 — Dashboard Refresh + Fundamentals
Live refresh buttons on dashboard. Added fundamental signals (EPS trend, revenue growth) to scanner ranking.

---

## M8 — Trade Recommendation Engine
`swing-lab rebalance` enhanced: combines gate score + scan rank + Claude review conviction into a weighted recommendation. Outputs diff vs current positions.

---

## M9 — Trade Outcome Feedback Loop
Closed trade outcomes feed back into the recommendation engine. Adjusts signal weights based on historical accuracy per signal type.

---

## M10 — Conversational Analyst Agent ⏳
Steps 1–8 complete: agent scaffolding, tool definitions, conversation loop, context injection. Step 9 (final wiring + integration test) pending. See TASKS.md.

---

## Automation — Scheduled Gate/Scan/Review
Task scheduler runs gate + scan + review every Sunday morning. Output logged to `data/swing.db` and written to Obsidian.

---

## v2 Ideas (not scheduled)
- Live data feed integration (replace yfinance polling)
- Options screening layer (calls on top momentum picks)
- Multi-strategy support (mean reversion, breakout)
- Update Wealthfront positions when new statement available

---

## M11 — Dashboard Visual Rehaul

| # | Milestone | Status | Completed |
|---|---|---|---|
| M11.1 | Add 4 HTML helpers to theme.py | ✅ Complete | 2026-05-31 |
| M11.2 | Floating chat button + st.dialog | ✅ Complete | 2026-05-31 |
| M11.3 | Sidebar section labels + header bar | ✅ Complete | 2026-05-31 |
| M11.4 | Recommendation page rewrite | ✅ Complete | 2026-05-31 |
| M11.5 | Scanner polish | ✅ Complete | 2026-05-31 |
| M11.6 | Claude Review bull/bear split | ✅ Complete | 2026-05-31 |
| M11.7 | Gate/Trade Log/Postmortem consistency | ✅ Complete | 2026-05-31 |
