"""Trade Recommendation Engine — M8."""
import json
import os
import time
import anthropic
import pandas as pd
from swing_lab.config import (
    DATA_DIR, MAX_POSITION_PCT, MODEL, RECOMMEND_TOP_N,
    RECOMMEND_RED_FLAG_MAX, RECOMMEND_SECOND_PICK_MIN_SCORE, get_api_key,
)
from swing_lab.technicals import get_price_levels, format_levels_for_prompt

_DIAG_FILE = DATA_DIR / ".cache_ids.json"


def _load_cache_id(key: str) -> str | None:
    try:
        return json.loads(_DIAG_FILE.read_text()).get(key)
    except Exception:
        return None


def _save_cache_id(key: str, msg_id: str) -> None:
    try:
        try:
            data = json.loads(_DIAG_FILE.read_text())
        except Exception:
            data = {}
        data[key] = msg_id
        _DIAG_FILE.write_text(json.dumps(data))
    except Exception:
        pass

_SYSTEM_PROMPT = (
    "You are a quantitative momentum trader synthesizing a final trade recommendation. "
    "Be direct and specific. Focus on risk-adjusted conviction given the macro regime "
    "and the relative quality of the candidate set."
)

_RECOMMENDATION_TOOL = {
    "name": "submit_recommendation",
    "description": "Submit the synthesized trade recommendation with structured price levels.",
    "input_schema": {
        "type": "object",
        "required": [
            "rationale", "key_risks", "exit_signals",
            "entry_low", "entry_high", "support", "stop", "target",
        ],
        "properties": {
            "rationale":    {"type": "string",
                             "description": "2-3 sentences: why this is the strongest trade right now."},
            "key_risks":    {"type": "array", "items": {"type": "string"},
                             "minItems": 2, "maxItems": 4},
            "exit_signals": {"type": "array", "items": {"type": "string"},
                             "minItems": 2, "maxItems": 4,
                             "description": "Behavioral/qualitative exit conditions only — NO price levels."},
            "entry_low":    {"type": "number",
                             "description": "Lower bound of the entry zone in dollars."},
            "entry_high":   {"type": "number",
                             "description": "Upper bound of the entry zone in dollars."},
            "support":      {"type": "number",
                             "description": "Support shelf price below entry in dollars."},
            "stop":         {"type": "number",
                             "description": "Hard stop-loss price in dollars. Must be below support."},
            "target":       {"type": "number",
                             "description": "Realistic profit target price in dollars (10–25% upside from entry)."},
        },
    },
}


def select_candidates(
    reviews_df: pd.DataFrame,
    open_symbols: set,
    *,
    red_flag_max: int = RECOMMEND_RED_FLAG_MAX,
) -> pd.DataFrame:
    """Filter held symbols and high-red-flag names; return sorted by blended_score desc."""
    df = reviews_df.copy()
    df = df[~df["symbol"].isin(open_symbols)]

    def _flag_count(flags_json):
        try:
            return len(json.loads(flags_json) if flags_json else [])
        except Exception:
            return 0

    df = df[df["red_flags_json"].apply(_flag_count) <= red_flag_max]
    return df.sort_values("blended_score", ascending=False).reset_index(drop=True)


def compute_sizing(gate_sizing: float, n: int) -> float:
    """Return per-position size: min(MAX_POSITION_PCT, gate_sizing / n)."""
    if n == 0:
        return 0.0
    return min(MAX_POSITION_PCT, gate_sizing / n)


def n_picks_to_synthesize(
    candidates: pd.DataFrame,
    *,
    second_min_score: float = RECOMMEND_SECOND_PICK_MIN_SCORE,
    cap: int = RECOMMEND_TOP_N,
) -> int:
    """How many picks to fully synthesize: 1 by default, 2 only if the #2
    candidate independently clears `second_min_score`. Never below 1 (unless
    there are no candidates) and never above `cap`."""
    n = len(candidates)
    if n == 0:
        return 0
    count = 1
    if n >= 2 and float(candidates.iloc[1].get("blended_score") or 0) >= second_min_score:
        count = 2
    return min(count, cap)


def _fetch_current_price(symbol: str) -> tuple[float | None, str]:
    """Return (price, session) where session is 'after-hours', 'pre-market', or '' (regular/close)."""
    try:
        import yfinance as yf
        from datetime import datetime, timezone

        try:
            from zoneinfo import ZoneInfo
            now_et = datetime.now(ZoneInfo("America/New_York"))
        except Exception:
            # Fallback approximation if tz database is unavailable
            now_utc = datetime.now(timezone.utc)
            et_offset = -4 if 3 <= now_utc.month <= 11 else -5
            now_et = now_utc.replace(hour=(now_utc.hour + et_offset) % 24)
        mins = now_et.hour * 60 + now_et.minute

        if 16 * 60 <= mins < 20 * 60:
            session = "after-hours"
        elif 4 * 60 <= mins < 9 * 60 + 30:
            session = "pre-market"
        else:
            session = ""

        ticker = yf.Ticker(symbol)
        fi = ticker.fast_info
        price = getattr(fi, "last_price", None)

        if price is None:
            hist = ticker.history(period="2d")
            return (float(hist["Close"].iloc[-1]) if not hist.empty else None), ""

        price = float(price)

        # Verify extended-hours movement: if price == previous_close, no real AH/PM trading
        if session:
            prev = getattr(fi, "previous_close", None)
            if prev is not None and abs(price - float(prev)) < 0.01:
                session = ""

        return price, session
    except Exception:
        pass
    return None, ""


def synthesize_pick(
    pick_row,
    others_df: pd.DataFrame,
    gate_dict: dict,
    open_symbols: list,
) -> dict:
    """Single Anthropic call to synthesize rationale + risks + price levels for one pick."""
    client = anthropic.Anthropic(api_key=get_api_key())

    symbol = pick_row["symbol"]
    current_price, price_session = _fetch_current_price(symbol)
    price_str = f"${current_price:.2f}" if current_price else "unknown"

    levels = get_price_levels(symbol)
    levels_block = format_levels_for_prompt(levels, current_price)

    other_lines = []
    for _, row in others_df.iterrows():
        other_lines.append(
            f"- {row['symbol']}: blended {row.get('blended_score', 0):.1f}/100, "
            f"quant {row.get('quant_score', 0):.1f}/100, "
            f"Claude {row.get('claude_score', 0):.1f}/10"
        )

    flags = []
    try:
        flags = json.loads(pick_row.get("red_flags_json") or "[]")
    except Exception:
        pass

    levels_section = f"\n{levels_block}\n" if levels_block else ""
    user_msg = f"""Candidate: {symbol}
Current price: {price_str}
Blended score: {pick_row.get("blended_score", 0):.2f}/100
Quant score: {pick_row.get("quant_score", 0):.1f}/100
Claude score: {pick_row.get("claude_score", 0):.1f}/10
Red flags: {flags or "none"}

Macro gate: {gate_dict.get("label", "")} (score {gate_dict.get("score", 0):.1f}, sizing {gate_dict.get("sizing", 0)*100:.0f}%)
Currently held: {", ".join(open_symbols) if open_symbols else "none"}

Other candidates this cycle:
{chr(10).join(other_lines) if other_lines else "none"}
{levels_section}
Claude's prior analysis of {symbol}:
{pick_row.get("claude_summary", "")}

Call submit_recommendation with your synthesized analysis. Price levels must be consistent: stop < support < entry_low ≤ entry_high < target. All levels must be anchored to the technical chart levels above — do not invent arbitrary numbers.
"""

    prev_id = _load_cache_id("recommend")
    for attempt in range(5):
        try:
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=2000,
                betas=["cache-diagnosis-2026-04-07"],
                tools=[_RECOMMENDATION_TOOL],
                tool_choice={"type": "tool", "name": "submit_recommendation"},
                system=[{
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_msg}],
                diagnostics={"previous_message_id": prev_id},
            )
            break
        except anthropic.APIStatusError as exc:
            if exc.status_code in (529, 503, 502) and attempt < 4:
                wait = 2 ** attempt  # 1, 2, 4, 8 s
                print(f"  [API overloaded (attempt {attempt+1}/5) — retrying in {wait}s…]")
                time.sleep(wait)
            else:
                raise

    _save_cache_id("recommend", response.id)
    cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    diag = getattr(response, "diagnostics", None)
    if diag:
        reason = getattr(diag, "cache_miss_reason", None)
        status = f"miss ({reason})" if reason else "hit"
        print(f"  [{symbol} synthesis cache] {status}")
    elif cache_read > 0:
        print(f"  [{symbol} synthesis: cache hit — {cache_read:,} tokens saved]")
    else:
        print(f"  [{symbol} synthesis: cache miss — system prompt cached for next run]")

    tool_block = next((b for b in response.content if getattr(b, "type", "") == "tool_use"), None)
    if tool_block is None:
        raise RuntimeError(f"{symbol}: model did not call submit_recommendation — cannot produce recommendation")
    args = tool_block.input

    entry_low  = float(args["entry_low"])
    entry_high = float(args["entry_high"])
    support    = float(args["support"])
    stop       = float(args["stop"])
    target     = float(args["target"])
    entry_zone_text = (
        f"${entry_low:.2f}–${entry_high:.2f}; "
        f"support at ${support:.2f}; stop below ${stop:.2f}; target ${target:.2f}"
    )

    return {
        "rationale": args.get("rationale", ""),
        "risks": args.get("key_risks") or [],
        "exit_triggers": args.get("exit_signals") or [],
        "entry_zone": entry_zone_text,
        "entry_low":  entry_low,
        "entry_high": entry_high,
        "support":    support,
        "stop":       stop,
        "target":     target,
        "is_synthesized": True,
        "cache_hit": 1 if cache_read > 0 else 0,
        "price_at_scan": current_price,
        "price_session": price_session,
    }


def generate_recommendations(
    scan_id: int,
    gate: dict,
    reviews_df: pd.DataFrame,
    open_positions: list,
) -> list[dict]:
    """Filter → rank → synthesize #1 → compose #2/#3. Return list of rec dicts."""
    if reviews_df is None or reviews_df.empty or "symbol" not in reviews_df.columns:
        return []

    open_symbols = set()
    if open_positions:
        first = open_positions[0]
        open_symbols = (
            {t["symbol"] for t in open_positions}
            if isinstance(first, dict)
            else set(open_positions)
        )

    candidates = select_candidates(reviews_df, open_symbols)
    n = n_picks_to_synthesize(candidates)

    if n == 0:
        return []

    top_n = candidates.head(n)
    sizing_pct = compute_sizing(gate["sizing"], n)
    recs = []

    for rank_idx in range(1, n + 1):
        row = top_n.iloc[rank_idx - 1]
        # Every recommended pick gets a full synthesis with real price levels —
        # if a name can't clear the bar for that, it isn't recommended at all.
        synthesis = synthesize_pick(row, top_n.iloc[rank_idx:], gate, list(open_symbols))
        price = synthesis.pop("price_at_scan", None)
        price_session = synthesis.pop("price_session", "")

        flags = []
        try:
            flags = json.loads(row.get("red_flags_json") or "[]")
        except Exception:
            pass

        recs.append({
            "rank": rank_idx,
            "symbol": row["symbol"],
            "blended_score": row.get("blended_score"),
            "sizing_pct": sizing_pct,
            "gate_sizing": gate["sizing"],
            "review_id": row.get("review_id"),
            "rationale": synthesis.get("rationale", ""),
            "risks_json": json.dumps(synthesis.get("risks") or flags),
            "exit_triggers_json": json.dumps(synthesis.get("exit_triggers") or []),
            "entry_zone": synthesis.get("entry_zone", ""),
            "entry_low":  synthesis.get("entry_low"),
            "entry_high": synthesis.get("entry_high"),
            "support":    synthesis.get("support"),
            "stop_price": synthesis.get("stop"),
            "target":     synthesis.get("target"),
            "is_synthesized": synthesis.get("is_synthesized", False),
            "cache_hit": synthesis.get("cache_hit"),
            "price_at_scan": price,
            "price_session": price_session,
        })

    return recs
