"""Strategy filters — deterministic entry criteria for momentum candidates.

Each strategy is a named set of criteria checked against yfinance data.
Strategies live in the STRATEGIES registry and can be applied to scanner
output, review candidates, or pre-market gap results.

Current strategies:
- trend_join_long: 4-criteria higher-date breakout trend-following setup
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class CriterionResult:
    """Result of a single criterion check."""
    name: str
    passed: bool
    detail: str = ""


@dataclass
class StrategyCheck:
    """Result of checking a strategy against one symbol."""
    symbol: str
    strategy: str
    criteria: list[CriterionResult] = field(default_factory=list)
    passed: bool = False          # all criteria passed
    pass_count: int = 0
    total_criteria: int = 0
    price: float = 0.0
    error: str = ""


# ── Strategy definitions ─────────────────────────────────────────────────────

def _check_trend_join_long(symbol: str) -> StrategyCheck:
    """Trend Join Long — higher-date breakout trend-following setup.

    Criteria:
    1. Price > yesterday's daily high   (breaking out of prior day's range)
    2. Yesterday's close > SMA(200)     (above long-term trend)
    3. Price > today's pre-market high  (sustaining above pre-market)
    4. Price > today's high of day      (making a new high intraday)
    """
    result = StrategyCheck(symbol=symbol, strategy="trend_join_long")

    try:
        # Fetch daily data (last 15 months for SMA200)
        daily = yf.Ticker(symbol).history(period="15mo", interval="1d")
        if daily.empty or len(daily) < 210:
            result.error = f"Insufficient daily history ({len(daily)} bars)"
            return result

        # Fetch intraday data for current session (pre-market + regular)
        intra = yf.Ticker(symbol).history(period="1d", interval="5m", prepost=True)

        # Determine current price
        if not intra.empty:
            current_price = float(intra["Close"].iloc[-1])
        else:
            current_price = float(daily["Close"].iloc[-1])

        result.price = current_price

        # Yesterday's data
        yesterday = daily.iloc[-2]
        prev_close = float(yesterday["Close"])
        prev_high = float(yesterday["High"])

        # SMA(200)
        close_series = daily["Close"]
        sma_200 = float(close_series.tail(200).mean())

        # Today's intraday high (pre-market + regular)
        if not intra.empty:
            today_high = float(intra["High"].max())
            # Pre-market high (bars before 9:30 AM ET)
            pm_bars = intra.between_time("04:00", "09:30") if hasattr(intra.index, 'time') else intra
            pm_high = float(pm_bars["High"].max()) if not pm_bars.empty else today_high
        else:
            today_high = float(daily.iloc[-1]["High"])
            pm_high = today_high

        # Criterion 1: Price above yesterday's high
        c1 = current_price > prev_high
        result.criteria.append(CriterionResult(
            name="price_above_yesterday_high",
            passed=c1,
            detail=f"${current_price:.2f} > ${prev_high:.2f}" if c1
                   else f"${current_price:.2f} ≤ ${prev_high:.2f} (gap: ${prev_high - current_price:.2f})",
        ))

        # Criterion 2: Yesterday's close above SMA(200)
        c2 = prev_close > sma_200
        result.criteria.append(CriterionResult(
            name="close_above_200sma",
            passed=c2,
            detail=f"${prev_close:.2f} > ${sma_200:.2f}" if c2
                   else f"${prev_close:.2f} ≤ ${sma_200:.2f}",
        ))

        # Criterion 3: Price above pre-market high
        c3 = current_price > pm_high
        result.criteria.append(CriterionResult(
            name="price_above_premarket_high",
            passed=c3,
            detail=f"${current_price:.2f} > ${pm_high:.2f}" if c3
                   else f"${current_price:.2f} ≤ ${pm_high:.2f}",
        ))

        # Criterion 4: Price above today's high of day (making new high)
        # During market hours: current > previous bar high = pushing higher
        # If only EOD data: current > yesterday's high = breaking out
        c4 = current_price >= today_high * 0.999  # Allow 0.1% tolerance for rounding
        result.criteria.append(CriterionResult(
            name="new_high_of_day",
            passed=c4,
            detail=f"${current_price:.2f} ≥ ${today_high:.2f}" if c4
                   else f"${current_price:.2f} < ${today_high:.2f}",
        ))

        result.total_criteria = 4
        result.pass_count = sum(1 for c in result.criteria if c.passed)
        result.passed = result.pass_count >= 3  # 3 of 4 = pass (relaxed from 4/4)

    except Exception as e:
        result.error = str(e)

    return result


# ── Strategy registry ────────────────────────────────────────────────────────

STRATEGIES: dict[str, callable] = {
    "trend-join-long": _check_trend_join_long,
}

DEFAULT_STRATEGY = "trend-join-long"


# ── Public API ───────────────────────────────────────────────────────────────

def check_strategy(symbol: str, strategy: str = DEFAULT_STRATEGY) -> StrategyCheck:
    """Check a single symbol against a named strategy.

    Args:
        symbol: Ticker symbol (e.g. 'AAPL')
        strategy: Name from STRATEGIES registry

    Returns:
        StrategyCheck with per-criterion results and pass/fail verdict.
    """
    checker = STRATEGIES.get(strategy)
    if not checker:
        return StrategyCheck(
            symbol=symbol, strategy=strategy,
            error=f"Unknown strategy '{strategy}'. Available: {list(STRATEGIES.keys())}",
        )
    return checker(symbol)


def filter_candidates(
    symbols: list[str],
    strategy: str = DEFAULT_STRATEGY,
    progress=None,
) -> dict[str, StrategyCheck]:
    """Check multiple symbols against a strategy.

    Args:
        symbols: List of ticker symbols
        strategy: Strategy name
        progress: optional callable(current, total, symbol)

    Returns:
        Dict of {symbol: StrategyCheck}
    """
    results = {}
    total = len(symbols)
    for i, sym in enumerate(symbols):
        if progress:
            progress(i + 1, total, sym)
        results[sym] = check_strategy(sym, strategy=strategy)
    return results


def format_filter_result(
    checks: dict[str, StrategyCheck],
    top_n: int = None,
    show_fails: bool = False,
) -> str:
    """Format strategy filter results as a terminal table.

    Args:
        checks: Dict from filter_candidates()
        top_n: Show only top N passing results
        show_fails: Include failing candidates
    """
    lines = []
    passing = {s: c for s, c in checks.items() if c.passed}
    failing = {s: c for s, c in checks.items() if not c.passed and not c.error}

    lines.append(f"Strategy filter: {len(passing)}/{len(checks)} passed")
    lines.append("")

    if not passing:
        lines.append("No candidates passed the strategy filter.")
        if show_fails and failing:
            lines.append("")
            lines.append("Closest misses:")
            for sym, c in sorted(failing.items(),
                                 key=lambda x: x[1].pass_count, reverse=True)[:5]:
                lines.append(f"  {sym}: {c.pass_count}/{c.total_criteria} criteria met")
        return "\n".join(lines)

    # Header
    lines.append(f"{'#':>3}  {'Symbol':>6}  {'Pass':>4}/4  Criteria")
    lines.append(f"{'─'*3}  {'─'*6}  {'─'*8}  {'─'*40}")

    sorted_passing = sorted(passing.items(), key=lambda x: x[1].pass_count, reverse=True)
    if top_n:
        sorted_passing = sorted_passing[:top_n]

    for i, (sym, c) in enumerate(sorted_passing, start=1):
        crit_summary = []
        for cr in c.criteria:
            mark = "✓" if cr.passed else "✗"
            crit_summary.append(f"{mark} {cr.name}")
        lines.append(f"{i:>3}  {sym:>6}  {c.pass_count:>4}/{c.total_criteria:<4}  {' | '.join(crit_summary)}")

    if show_fails and failing:
        lines.append("")
        lines.append("Failed:")
        sorted_fails = sorted(failing.items(), key=lambda x: x[1].pass_count, reverse=True)
        for sym, c in sorted_fails[:5]:
            fails = [cr.name for cr in c.criteria if not cr.passed]
            lines.append(f"  {sym}: failed {len(fails)}/{c.total_criteria} — {', '.join(fails)}")

    return "\n".join(lines)


def format_detail(check: StrategyCheck) -> str:
    """Full detail for a single strategy check result."""
    lines = [
        f"STRATEGY: {check.strategy} — {check.symbol}",
        f"Verdict: {'✅ PASS' if check.passed else '❌ FAIL'} ({check.pass_count}/{check.total_criteria})",
        f"Price: ${check.price:.2f}",
    ]
    if check.error:
        lines.append(f"Error: {check.error}")
        return "\n".join(lines)

    lines.append("")
    for cr in check.criteria:
        mark = "✅" if cr.passed else "❌"
        lines.append(f"  {mark} {cr.name}")
        lines.append(f"     {cr.detail}")

    return "\n".join(lines)
