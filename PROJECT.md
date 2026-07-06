# Swing Lab — Project

## Purpose & Goals
Short-term momentum swing trading research tool. Automates the full workflow: macro environment scoring, momentum scanning, Claude-powered analyst review, trade logging, and post-mortem analysis. Research + decision-support only — no automated order execution.

## Target User
Personal use only (Garrett). CLI-driven, runs locally on Windows.

## Tech Stack
| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Packaging | uv (`uv run swing-lab <command>`) |
| Data | yfinance (price data), pandas/numpy (analysis) |
| AI layer | Anthropic SDK — Claude analyst review + conversational agent |
| Database | SQLite at `data/swing.db` |
| Obsidian integration | Marker-based idempotent writeback to vault notes |
| Config | `src/swing_lab/config.py` — single source of truth for all constants |
| Dashboard | Streamlit (educational/review UI) |

## CLI Commands
```
uv run swing-lab gate        # macro gate score + 6 signal components
uv run swing-lab scan        # top-20 momentum picks (12-1m, sector-relative)
uv run swing-lab review      # Claude analyst review of top-6 candidates
uv run swing-lab backtest    # walk-forward backtest
uv run swing-lab log         # trade log: open / close / list
uv run swing-lab postmortem  # Claude pattern analysis of trade log
uv run swing-lab rebalance   # combined: gate → scan → review → diff
```

## Architecture Decisions

**Why Python CLI with uv instead of a web app?**
Trading research is a command-driven workflow — gate check before a Sunday rebalance, quick scan, read Claude's review. A web app adds UI complexity for no benefit. uv handles isolated environments without the friction of venv activation. Trade-off: no mobile access.

**Why SQLite for trade log instead of flat files?**
The trade log needs structured queries (open positions, P&L by ticker, pattern lookups for postmortem). Flat CSV would require custom parsing. SQLite is zero-setup and already in use for Finance Tracker. Trade-off: requires a DB viewer to inspect directly.

**Why Claude API for review/postmortem instead of rule-based scoring?**
Momentum screening is deterministic (12-1m rank, sector-relative). But narrative context — earnings calendar, sector rotation, macro regime — requires synthesis that rules can't handle well. Claude reads the structured scan output and adds qualitative judgment. Trade-off: API cost per review (acceptable for bi-weekly cadence).

**Why idempotent Obsidian writeback instead of a separate report?**
The trading strategy framework lives in Obsidian. Writing results back to the same note (marker-based insertion) keeps the research loop closed: scan → review → note update. Re-running doesn't duplicate. Trade-off: fragile if Obsidian note structure changes.

**Why hardcode Wealthfront positions for Phase 1 instead of live fetch?**
Wealthfront has no public API. Phase 1 factor exposure analysis required snapshot data. Hardcoded from Dec 2025 statement. Update when user provides a new statement.

## Key Dependencies & Gotchas
- All constants in `src/swing_lab/config.py` — never hardcode gate thresholds, position sizes, or universe URL elsewhere
- Obsidian vault at `E:\Downloads\Other\Obsidian Vault\Active\` — writeback target
- Wealthfront positions hardcoded from Dec 2025 statement — stale after ~3 months
- `data/swing.db` created on first run — not committed to git

## Backtest Findings (2026-06-11)
Walk-forward backtest, 2015-01-01 → 2024-12-31, bi-weekly rebalance, 260 periods.
Survivorship-bias-free (point-in-time S&P 500 membership), no look-ahead, **before
trading costs/slippage/taxes**. Gate uses the corrected factor-crowding signal
(market-excess MTUM/VLUE correlation).

| Configuration | Total | Ann. | Sharpe | Max DD | Hit rate |
|---|---|---|---|---|---|
| SPY buy-and-hold (benchmark) | 242.5% | 13.1% | **0.82** | -31.0% | — |
| Sector-neutral top-20, ungated | 206.7% | 11.9% | 0.67 | -35.7% | **61.2%** |
| Sector-neutral top-20, gated | 96.4% | 7.0% | 0.67 | **-17.2%** | 54.2% |
| Raw-rank top-5, ungated | 223.8% | 12.5% | 0.55 | -47.0% | 58.5% |
| Raw-rank top-5, gated | 85.1% | 6.4% | 0.43 | -25.8% | 51.9% |

**Conclusion: no tested configuration beat SPY on absolute or risk-adjusted return
over this window.** The verdict is robust across ranking method, concentration, and
gate overlay — not an artifact of one setup.

What the components are individually worth:
- **Selection has signal but not enough edge.** The default config hit 61.2% of
  periods positive with Sharpe 0.67 — the signal is real. Raw-rank + top-5
  concentration added +0.6% annualized but cost 0.12 Sharpe and 11 points of
  drawdown (rank method and concentration were changed together, so their
  individual effects are confounded — concentration is the likely culprit for
  the risk increase).
- **The gate is a risk reducer, not a return enhancer.** Its stand-downs are
  well-timed (Aug 2015, Q4 2018, COVID Feb–Apr 2020, the 2022 bear) and it halved
  max drawdown — but final wealth matched the mechanical effect of average exposure
  (3.1x^0.65 ≈ gated outcome), i.e. timing alpha ≈ 0. It also hurt concentrated
  momentum specifically by missing post-stand-down rebounds.
- **Defensible uses going forward:** the gate as a sizing dial on equity exposure
  held anyway; the scanner/review pipeline as idea generation for discretionary
  trades — not as a systematic SPY-beating strategy.

Caveats: 2015–2024 was a mega-cap-led decade unusually kind to SPY; results are
before costs (which would worsen the strategy, not improve it); single decade,
single market.

Repro: `uv run swing-lab backtest [--with-gate] [--rank raw|sector] [--top N]`

## Lessons Learned
- **Marker-based Obsidian writeback:** First implemented in `scripts/phase1_factor_exposure.py:286–341`. The pattern (locate marker → find next `###` boundary → insert → mark checklist `[x]`) is reusable across all writeback scripts. Idempotency is critical — running twice must not duplicate.
- **2-signal → 6-signal gate evolution (M3a → M3.5):** Started with a simple 2-signal macro gate (VIX + SPY trend). Expanded to 6 signals after M3a was complete. Building incrementally and expanding after validation was faster than designing the full gate upfront.
- **Claude review as a separate milestone:** Initial plan bundled the Claude review with the scanner. Separating M4 (Claude review) from M3 (scanner) made both easier to test independently — scanner output can be validated without burning API credits.
- **Survivorship bias flattered the original backtest (2026-06):** Using current S&P 500 membership for 2015–2024 inflated momentum returns enough to make a SPY-trailing strategy look like a winner. Point-in-time membership + counting delistings at their last print reversed the conclusion. Validate the data before trusting the strategy.
- **A signal can be broken and never noticed (factor crowding):** Raw MTUM/VLUE correlation measured shared market beta (~0.75 always), pinning one of six gate signals near zero in every regime and silently capping composite scores ~6 points low. Backtesting the gate historically is what exposed it — point-in-time replay is a diagnostic tool, not just a performance report.
