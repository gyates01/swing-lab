# Integration Plan: YouTube Video Tools → Swing Lab

> **Source video:** [Claude Code + TradingView — Full Pre-Market Scanner & Automation](https://www.youtube.com/watch?v=IqvnryFzZD4) by Shay (10+ year trader)
> **Target:** Swing Lab at `H:\Other\Claude Projects\Swing Lab\`
> **Date:** 2026-06-12
> **Status:** Planning phase

---

## Table of Contents

1. [TradingView MCP Connection](#1-tradingview-mcp-connection)
2. [Pre-market Gap Scanner (Yahoo Finance + Benzinga News)](#2-pre-market-gap-scanner)
3. [Strategy Scanner / Filter (Trend Join Long)](#3-strategy-scanner--filter)
4. [Pine Script Backtesting on TradingView](#4-pine-script-backtesting)
5. [Python-Based Backtesting (Scaled Universe)](#5-python-based-backtesting)
6. [Automated Scheduling (Cron Jobs)](#6-automated-scheduling)
7. [Telegram Bot Notifications](#7-telegram-notifications)
8. [TradingView Remix AI (TV Copilot)](#8-tradingview-remix-ai)
9. [Summary Priority Matrix](#9-summary-priority-matrix)

---

## 1. TradingView MCP Connection

### What the video does
Installs the [tradingview-mcp](https://github.com/nicedouble/tradingview-mcp) GitHub project (~2.9K stars) via Claude Code. This gives Claude Code direct read/write access to TradingView Desktop — it can read candlestick data, draw levels, switch timeframes, and run Pine Script backtests. Connection is via an MCP (Model Context Protocol) server that links Claude Code to the TV Desktop app.

### Swing Lab current state
Swing Lab uses **yfinance** for all price data. It has no connection to TradingView. The macro gate computes from public data (VIX, yields, credit spreads). The scanner downloads price panels from Yahoo Finance. No live chart data, no Pine Script, no TV-level interaction.

### Integration assessment

| Aspect | Detail |
|--------|--------|
| **Compatibility** | The video creator explicitly says the TV MCP **does not work on Windows** — the TV Desktop binary format is different. He suggests asking Claude to solve it. This is a hard blocker unless the situation has changed. |
| **MCP stack mismatch** | Swing Lab uses the **Anthropic API** directly (Claude review/postmortem jobs). The MCP server is designed for **Claude Code** (the desktop IDE agent). These are different products. To use TV MCP, Swing Lab would need to either: (a) spawn Claude Code as a subprocess, or (b) find a Python-native MCP client that can talk to the TV MCP server. |
| **What we'd gain** | Live chart data (not just EOD), Pine Script execution, ability to draw levels/annotations on TV, visual backtest verification. |
| **Swing Lab alternative** | Before attempting this, ask: can Swing Lab get the same data from **yfinance / pandas-market-calendars / polygon.io** without the MCP overhead? Most TV data (price, indicators) is replicable. The unique thing we'd lose is TV's native Pine Script runner. |

### Decision: SKIP (low priority, high complexity, Windows blocker)
Revisit if either: (a) the MCP project adds Windows support, or (b) someone creates a Python MCP client that can connect to the TV MCP server standalone.

### Alternative path to live data
Instead of TV MCP, add an **intraday data source** option to the scanner (e.g., yfinance `interval="5m"` for pre-market data, or Alpaca Markets free API for real-time). This is simpler, Windows-compatible, and doesn't require a desktop app running.

---

## 2. Pre-market Gap Scanner

### What the video does
Two-part scanner:
- **Scanner A:** Queries Yahoo Finance for pre-market gappers (gap up >5%, price >$3, volume >50K) + Benzinga for news catalyst. Outputs top 10 with ticker, gap %, one-line catalyst. Saved to date-stamped JSON.
- **Scanner A feeds Scanner B** — the gap scanner output becomes the candidate pool for the strategy filter.

### Swing Lab current state
Swing Lab's scanner computes **12-1 month momentum** on the S&P 500 universe (end-of-day data, batched download). It ranks by sector-relative percentile. This is a fundamentally different signal — medium-term trend momentum vs. overnight gap.

The video's gap scanner is **additive** — a different signal type for a different time horizon (intraday/pre-market vs. multi-week swing).

### Integration proposal

**Priority: HIGH** — this fills a gap (pre-market awareness) that Swing Lab currently has zero coverage for.

### Specific implementation

#### New module: `src/swing_lab/premarket.py`
```python
# Fetch pre-market gappers from Yahoo Finance
# Source news catalysts from Benzinga (free tier) or Finviz
# Filter by: gap_pct > 5%, price > $3, volume > 50K
# Output: sorted list with ticker, gap%, price, volume, news_catalyst
# Save to results/premarket_{date}.json
```

#### Sources to evaluate:
| Source | Cost | Pre-market data | News catalysts |
|--------|------|-----------------|----------------|
| **Yahoo Finance** (yfinance) | Free | Pre-market price via `history(period="1d", interval="5m", prepost=True)` | None (need separate source) |
| **Finviz** (web scrape) | Free | Pre-market scanner page has gap % | Brief catalyst blurb per ticker |
| **Benzinga Pro** | Free tier | No | Press release summaries |
| **Alpaca Markets** | Free (signup) | Real-time pre-market via API | None |

**Recommended approach:** yfinance for prices (already a dependency), Finviz web scrape for the screener and catalyst blurbs. This requires no new API keys and no new dependencies beyond what's already in `pyproject.toml`.

#### New CLI command: `swing-lab premarket-gap`
```
Usage: uv run swing-lab premarket-gap [--min-gap 5] [--min-price 3] [--min-volume 50000]
```

#### Output format:
```
PREMARKET GAP SCANNER — 2026-06-12
Source: Yahoo Finance + Finviz

Rank  Ticker  Gap %   Price    Volume    Catalyst
────  ──────  ─────  ────────  ────────  ─────────────────────────────────
  1   AAPL    +3.2%  $198.45   1,234K    iPhone sales beat estimates
  2   TSLA    +5.8%  $345.20     892K    Q2 delivery numbers due tomorrow
  ...
```

#### Integration with Swing Lab pipeline:
- `swing-lab rebalance` could optionally run the pre-market gap scan and include gappers as context in the Claude review prompt
- The gate macro context could include a "pre-market activity" signal (number of strong gappers = market sentiment)

### Effort: 2–3 hours
- New module: `premarket.py` (~150 lines)
- CLI integration: add `premarket-gap` subparser to `cli.py`
- News source: Finviz scraping or lightweight HTML parsing
- Tests: 1 test file

---

## 3. Strategy Scanner / Filter

### What the video does
Scanner B applies the **Trend Join Long** strategy filter to the gap scanner candidates. Criteria:
1. Price above yesterday's daily high
2. Yesterday's close above 200 SMA
3. Price above today's pre-market high
4. Price above today's high of day (higher date breakout)
5. If all 5 pass → "hit" (entry trigger)

Requires TradingView Desktop running (the MCP reads live price data from the active chart).

### Swing Lab current state
Swing Lab has no strategy-level filter. The scanner produces a momentum rank, and the Claude review adds qualitative judgment. But there's no **deterministic strategy filter** that says "this set of quantitative criteria must be met for an entry."

### Integration proposal

**Priority: MEDIUM-HIGH** — A deterministic strategy filter is a missing layer in Swing Lab. The current system ranks candidates but doesn't have an explicit entry gate beyond the macro gate.

### Specific implementation

#### New module: `src/swing_lab/strategy_filter.py`

The filter criteria from the video can be computed from yfinance data (intraday/pre-market included) — no TradingView MCP needed if we use yfinance's `prepost=True` option.

```python
def check_trend_join_long(symbol: str) -> dict:
    """Check all 5 criteria for the Trend Join Long setup.
    Returns dict of {criterion: passed/false} + overall verdict.
    """
    # 1. Price > yesterday's daily high  → latest pre-market price vs prev close high
    # 2. Yesterday's close > 200 SMA     → daily close vs SMA(200)
    # 3. Price > today's pre-market high → current vs pre-market range
    # 4. Price > today's high of day      → higher date breakout check
    # Returns: {criteria: [...], passed: bool, pass_count: int}
```

#### Strategy configuration (config.py):
```python
# Strategy filters — can be extended with more strategies
STRATEGIES = {
    "trend_join_long": {
        "criteria": [
            "price_above_yesterday_high",
            "close_above_200sma",
            "price_above_premarket_high",
            "price_above_today_high",
        ],
        "min_pass": 4,  # 4 out of 5 must pass
    },
    "momentum_breakout": {
        # Future: different strategy
    },
}
```

#### Integration:
- `swing-lab scan --strategy trend_join_long` — apply the filter to top picks
- The strategy filter runs **after** momentum scoring but **before** the Claude review
- This gives Claude a pre-filtered candidate set (with pass/fail per criterion) so the analyst review is more focused

### Effort: 3–4 hours
- New module: `strategy_filter.py` (~200 lines)
- Config entries in `config.py`
- CLI integration (optional `--strategy` flag on scan/review)
- Must handle pre-market data gaps for non-US-traded hours
- Tests: 1 test file

---

## 4. Pine Script Backtesting

### What the video does
After building the strategy, asks Claude Code to write a **Pine Script v5** strategy and run it on TradingView. Gets visual backtest results (equity curve, trade list, metrics). Then extends to more tickers via the 15-min chart. TV's backtester is fast and provides built-in metrics (profit factor, Sharpe, max DD, etc.).

### Swing Lab current state
Swing Lab has a **comprehensive Python walk-forward backtest** (`src/swing_lab/backtest.py`). It's point-in-time, survivorship-bias-free, handles gate sizing historically. The backtest is more rigorous than Pine Script's built-in backtester.

### Integration assessment

| Aspect | Pine Script | Swing Lab (Python) |
|--------|-------------|-------------------|
| Speed | Fast (native C++) | Slower (downloading + pandas) |
| Survivorship bias | ❌ Uses current membership | ✅ Point-in-time |
| Walk-forward | ❌ Fixed period | ✅ Rolling out-of-sample |
| Gate simulation | ❌ No | ✅ Historical gate sizing |
| Visual verification | ✅ Chart overlays | ✅ PNG equity curve |
| Multi-ticker scale | ❌ Limited | ✅ Unlimited |

### Decision: LOW priority
Swing Lab's Python backtest is already superior in rigor. The only thing Pine Script adds is **visual verification on TV charts** — being able to see trades plotted on the actual chart. This is a nice-to-have for manual review, not a system improvement.

### If implemented later
Could add a `swing-lab backtest --pine` command that generates a Pine Script string from the strategy config and optionally copies it to clipboard for pasting into TV. But this requires the TV MCP to actually run it, which has the Windows blocker above.

### Effort: 1–2 hours (Pine Script generator only, no execution path on Windows)
Pine Script generator function: `strategy_filter.py` or a new `pinescript.py` that takes a strategy config and emits valid Pine Script v5.

---

## 5. Python-Based Backtesting

### What the video does
When Pine Script becomes too slow for 32 tickers, the creator asks Claude to **rewrite the backtest in Python**. This scales to the full watchlist (~30 stocks), 30 days, with portfolio-level metrics. Much faster than TV for multi-ticker analysis.

### Swing Lab current state
Swing Lab **already has this** — and it's more sophisticated. The Python walk-forward backtest covers 2015–2024, 260 bi-weekly periods, S&P 500 universe, with point-in-time membership, macro gate simulation, and benchmark comparison. The video's Python backtest is simpler (30 days, fixed watchlist, no gate).

### Decision: NO ACTION NEEDED
Swing Lab's backtest is already more comprehensive. However, there's a useful insight:

**Improvement idea:** The video runs backtests on a **user-defined watchlist** (not the full S&P 500). Swing Lab's backtest only runs on S&P 500 members. Adding a `--universe` option that accepts a custom ticker list (CSV file or comma-separated) would let users test strategies on specific sectors or personal watchlists.

```
uv run swing-lab backtest --universe "AAPL,MSFT,NVDA,AMD,TSLA"
```

This is a small, self-contained change.

### Effort: 1 hour (--universe option for backtest)

---

## 6. Automated Scheduling

### What the video does
Uses **Claude Code's built-in cron scheduler** to run:
- Scanner A every 30 min from 8:30 AM to 2:00 PM (12 runs/day)
- Scanner B 5 min after Scanner A, from 10:00 AM to 3:00 PM
- Results saved automatically

### Swing Lab current state
Swing Lab is **entirely manual** — `uv run swing-lab <command>` only runs when the user invokes it. There is no scheduling. The project has `scripts/nightly_run.ps1` and `scripts/premarket_run.ps1` (PowerShell scripts invoked by Windows Task Scheduler), but these are listed as tasks to verify, not actively used.

### Integration proposal

**Priority: HIGH** — Automated scheduling is the biggest gap between the video's workflow and Swing Lab. The whole point of a research tool is pre-market scans ready when you wake up.

### Implementation options

#### Option A: Hermes Agent Cron Jobs (preferred)
Swing Lab is on the same machine as Hermes Agent. Hermes has a built-in cron system (`cronjob` tool) that can:
- Run any command on a schedule
- Deliver results to Telegram/Discord/SMS
- Track run history
- No extra infrastructure needed

```
hermes cron create "Premarket Scanner" "30 8 * * 1-5" \
  "cd H:/Other/Claude Projects/Swing Lab && uv run swing-lab premarket-gap"
```

This is the most elegant solution — no Windows Task Scheduler, no PowerShell scripts, no extra setup.

#### Option B: Windows Task Scheduler (already partially set up)
The `.ps1` scripts exist but need to be verified and their Task Scheduler entries established. More fragile (env stripping, path issues).

#### Option C: Claude Code scheduler (not applicable here)
The video's approach uses Claude Code's internal scheduling. Swing Lab doesn't use Claude Code.

### Recommended schedule:
| Time | Command | Purpose |
|------|---------|---------|
| 8:30 AM ET | `premarket-gap` | Gap scanner before open |
| 9:00 AM ET | `gate` + `scan` | Morning macro check + momentum scan |
| 10:00 AM ET | `review` (on gap candidates) | Strategy filter 1hr after open |
| 2:00 PM ET | `gate` | Afternoon macro re-check |
| Sundays 8 PM | `rebalance` | Weekly portfolio rebalance |

### Effort: 2 hours (setup + testing)
- Configure Hermes cron jobs for Swing Lab commands
- Test delivery (Telegram or local notification)
- Wire up any `.env` loading needed for scheduled context (already planned in `PLANNING.md`)

---

## 7. Telegram Bot Notifications

### What the video does
Creates a Telegram bot (via BotFather), wires it to Claude Code, and sends scanner results to the user's phone after each scheduled run. Two message types:
- Scanner A: pre-market gappers (ticker, gap %, catalyst)
- Scanner B: strategy hits (trend join long candidates)

### Swing Lab current state
Swing Lab writes results to:
- SQLite database (`data/swing.db`)
- Obsidian vault notes (marker-based writeback)
- Terminal stdout

No mobile delivery. No push notifications.

### Integration proposal

**Priority: HIGH** — Mobile delivery turns Swing Lab from a "check at your desk" tool into a "check anywhere" tool. This is the single highest-impact UX improvement.

### Implementation options

#### Option A: Hermes Agent Telegram Bridge (recommended)
Hermes Agent can deliver cron job output directly to Telegram. If Swing Lab commands are scheduled via Hermes cron (see #6), the output is auto-delivered to Telegram with no additional code.

**Steps:**
1. Create a Telegram bot via BotFather (already documented in the video)
2. Configure Hermes to deliver cron job output to Telegram chat
3. Done — Swing Lab needs zero code changes for Telegram

#### Option B: Native Telegram bot in Swing Lab
Add `python-telegram-bot` to dependencies and add a `swing-lab notify` command that sends formatted messages.

**Advantages:** Can include rich formatting (markdown, inline keyboards), doesn't depend on Hermes.

**Disadvantages:** Need to manage bot tokens, polling vs webhook, state management.

#### Option C: Hybrid — Swing Lab writes structured output + Hermes delivers
Swing Lab writes results to a known file path. Hermes cron job reads that file and delivers via Telegram. No Python dependencies added to Swing Lab, no bot code to maintain.

### Recommended approach: Option A (Hermes Telegram) + Option C (structured file output)

1. Add a `--json` flag to Swing Lab commands for structured machine-readable output
2. Schedule via Hermes cron
3. Hermes delivers the formatted output to Telegram

### Effort: 1–2 hours (Telegram bot setup + Hermes configuration)
- No Swing Lab code changes needed for Option A
- Option C adds `--json` flag to relevant commands (~50 lines total across CLI)

---

## 8. TradingView Remix AI

### What the video does
TradingView's own AI copilot (beta, via Chrome extension). Can backtest across the full watchlist, run 90-day backtests on 15-min charts. Key limitations: **on-demand only** (no scheduling), no Telegram integration.

### Swing Lab current state
Not applicable — this is a TV-internal feature, not something Swing Lab can integrate with.

### Decision: SKIP (external tool, no integration surface)
This is a TradingView product feature, not an API or integration point. Treat it as an alternative tool to use alongside Swing Lab, not something to integrate.

---

## 9. Summary Priority Matrix

| # | Feature | Priority | Effort | Dependencies | Win | Notes |
|---|---------|----------|--------|-------------|-----|-------|
| 1 | **Pre-market Gap Scanner** | HIGH | 2–3h | yfinance (exists), Finviz (new) | Fills gap in pre-market signal coverage | New `premarket.py` module + CLI |
| 2 | **Telegram Notifications** | HIGH | 1–2h | Telegram bot (free), Hermes (exists) | Mobile delivery — biggest UX upgrade | Uses Hermes cron + Telegram bridge |
| 3 | **Automated Scheduling** | HIGH | 2h | Hermes cron (exists) | Results ready when you wake up | Hermes cron runs Swing Lab commands |
| 4 | **Strategy Filter (Trend Join Long)** | MED-HIGH | 3–4h | yfinance pre/post market data | Adds deterministic entry filter to pipeline | New `strategy_filter.py` module |
| 5 | **Custom Universe Backtest (--universe)** | MED | 1h | Pandas (exists) | Test strategies on personal watchlists | Small `--universe` CLI flag add |
| 6 | **TradingView MCP** | SKIP | N/A | Windows + MCP blocker | Live TV data | Revisit if Windows support appears |
| 7 | **Pine Script Backtest** | LOW | 1–2h | TV MCP blocked | Visual trade verification | Do only if TV MCP becomes available |
| 8 | **TradingView Remix AI** | SKIP | N/A | External product | — | External tool, not integrable |

### Recommended implementation order:

**Phase 1 (this week):**
1. `swing-lab premarket-gap` — new CLI command for pre-market gap scanning
2. Configure Hermes cron + Telegram for delivery
3. Wire up the schedule (pre-market, intraday, EOD)

**Phase 2 (next week):**
4. Strategy filter module — Trend Join Long and extensible strategy framework
5. `--universe` flag on `swing-lab backtest`
6. Auto-apply strategy filter in the `review` + `recommend` pipeline

**Phase 3 (ongoing):**
7. Gather feedback on which criteria work vs. need adjustment
8. Consider adding more strategy presets
9. Revisit TV MCP if Windows support lands

---

## Key Dependencies & Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Windows + pre-market data source reliability** | Pre-market data from yfinance can be spotty on weekends/holidays | Cache results; handle empty responses gracefully; add `--mock` flag for testing |
| **Finviz scraping stability** | Pre-market news source could break if Finviz changes their HTML | Add a `--news-source` option to switch between Finviz, Benzinga, or none |
| **Hermes cron + Task Scheduler env stripping** | API key not available to scheduled jobs | Already being fixed in PLANNING.md (dotenv loading in config.py) |
| **Telegram bot token management** | Token leaked or needs to rotate | Store in `.env`, never committed; bot can be revoked and recreated |
| **False positives in gap scanning** | Gap scanner flags stocks with news but no actual momentum | The strategy filter (Phase 2) is the second-pass that catches this |

---

## Success Criteria

- [ ] Running `uv run swing-lab premarket-gap` returns real pre-market gappers within 30 seconds
- [ ] Hermes cron delivers pre-market scan results to Telegram by 8:35 AM ET
- [ ] `uv run swing-lab backtest --universe "AAPL,MSFT,TSLA"` works with custom tickers
- [ ] Strategy filter correctly identifies Trend Join Long entries from historical data
- [ ] All scheduled jobs run without missing API keys (dotenv fix verified)
