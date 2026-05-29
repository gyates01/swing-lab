# Swing Lab — Project Instructions

## Project Overview
Short-term momentum swing trading research tool. Python package at `src/swing_lab/`, run via `uv run swing-lab <command>`.

## Active Plan
See `PLAN.md` in this directory — 5-milestone rollout. Milestones 1-2 complete, Milestones 3a onward in progress.

## Stack
- Python 3.11+, uv for packaging
- yfinance (data), pandas/numpy (analysis), anthropic (Claude review layer)
- SQLite at `data/swing.db`
- Obsidian vault at `E:\Downloads\Other\Obsidian Vault\Active\`

## Key Paths
- Config: `src/swing_lab/config.py` — all constants, import from here, never re-declare
- Obsidian strategy note: `E:\Downloads\Other\Obsidian Vault\Active\Claude for Trading — Methods, Strategies & Personal Framework.md`
- Obsidian Swing Lab dir: `E:\Downloads\Other\Obsidian Vault\Active\Swing Lab\` (created lazily in M5)
- Finance Tracker DB: `H:\Other\Claude Projects\Finance Tracker\backend\finance.db`

## Patterns to Follow
- Obsidian writeback: idempotent marker-based insertion — see `scripts/phase1_factor_exposure.py:286–341`
- Momentum calc (12-1m): canonical version lives in `src/swing_lab/scanner.py` — import from there, do not re-implement
- All config constants come from `src/swing_lab/config.py` — never hardcode gate thresholds, position sizes, etc.

## CLI Commands (as milestones complete)
```
swing-lab gate       # macro gate score + components
swing-lab scan       # top-20 momentum picks
swing-lab backtest   # walk-forward backtest
swing-lab review     # Claude analyst review of top-6
swing-lab log        # trade log (open/close/list)
swing-lab postmortem # Claude pattern analysis of trade log
swing-lab rebalance  # combined gate → scan → review → diff
```

## Skill Routing (project-specific)
- Any Claude API work (review.py, postmortem) → invoke `claude-api` skill first
- New milestone planning → invoke `superpowers:writing-plans`
