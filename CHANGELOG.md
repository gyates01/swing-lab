# Swing Lab — Changelog

Format: `Date | Version | Type | Description`
Types: `functional` (features/logic), `backend` (data/DB), `interactive` (UX/CLI), `research` (analysis/model)

---

| Date | Version | Type | Description |
|---|---|---|---|
| (prior) | v0.1 | research | Phase 1: factor exposure analysis; Obsidian writeback (`scripts/phase1_factor_exposure.py`) |
| 2026-05-25 | v0.2 | research | Phase 2: edge definition committed to `config.py`; Obsidian Phase 2 writeback script |
| 2026-05-25 | v1.0 | functional | M3a: `swing-lab gate` + `swing-lab scan` + CLI entry point + SQLite DB init |
| 2026-05-25 | v1.1 | functional | M3b: `swing-lab backtest` — walk-forward validation, SPY benchmark comparison |
| 2026-05-25 | v1.2 | research | M3.5: 6-signal macro gate (VIX, SPY trend, HYG, yield curve, breadth, VIX term structure) |
| 2026-05-25 | v1.3 | functional | M4: `swing-lab review` — Claude Analyst via Anthropic SDK, prompt caching |
| 2026-05-25 | v1.4 | functional | M5: `swing-lab log` + `swing-lab postmortem` — trade log + Claude pattern analysis |
| 2026-05-25 | v1.5 | interactive | M6: Streamlit educational dashboard (gate, picks, trade history, P&L chart) |
| 2026-05-26 | v1.6 | interactive | M7: Dashboard live refresh buttons; fundamentals signals (EPS trend, revenue growth) added to scanner |
| 2026-05-26 | v1.7 | research | M8: Trade Recommendation Engine — weighted gate + scan + Claude conviction → position diff |
| 2026-05-27 | v1.8 | research | M9: Trade Outcome Feedback Loop — closed trade outcomes adjust signal weights |
| 2026-05-28 | v1.9 | functional | M10 steps 1–8: Conversational Analyst Agent scaffolding, tool definitions, context injection |
| 2026-05-30 | v1.9.1 | functional | Automation: scheduled Sunday gate/scan/review → Obsidian writeback |
| 2026-05-30 | v1.9.2 | interactive | Charts: recommendation level labels on price + momentum charts |
| 2026-05-29 | — | — | Structured per /new-project: PROJECT.md, PLANNING.md, CHANGELOG.md, TASKS.md added; CLAUDE.md updated |
| 2026-06-11 | v1.10 | functional | Full code audit (AUDIT-2026-06-11.md): 13 findings fixed — batched yf.download (scan ~10s), survivorship-free backtest (point-in-time membership + delisting capture), vix_score fallback, review_id wiring, analyst loop max_tokens handling, forced tool_choice reviews, zoneinfo DST, tradelog hygiene |
| 2026-06-11 | v1.11 | research | Backtest upgrades: SPY benchmark line + stats, `--with-gate` (point-in-time gate replay), `--rank raw\|sector`, `--top N` |
| 2026-06-11 | v1.12 | research | Factor-crowding signal fixed: market-excess MTUM/VLUE correlation (raw correlation measured shared beta, pinning signal ~12/100; live gate scores now read ~5–10 pts higher) |
| 2026-06-11 | — | research | **Backtest verdict (see PROJECT.md):** no configuration beat SPY 2015–2024 on absolute or risk-adjusted return; gate = effective risk reducer (max DD halved at equal Sharpe), not return enhancer; raw+concentrated added return but cost Sharpe and drawdown |
