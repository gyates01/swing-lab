"""Trade Recommendation Engine — M8."""
import json
import os
import time
import anthropic
import pandas as pd
from swing_lab.config import MAX_POSITION_PCT, MODEL, RECOMMEND_TOP_N, RECOMMEND_RED_FLAG_MAX

_SYSTEM_PROMPT = (
    "You are a quantitative momentum trader synthesizing a final trade recommendation. "
    "Be direct and specific. Focus on risk-adjusted conviction given the macro regime "
    "and the relative quality of the candidate set."
)


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


def compose_runner_up(review_row) -> dict:
    """Build runner-up rec dict from stored review data — no API call."""
    flags = []
    try:
        flags = json.loads(review_row.get("red_flags_json") or "[]")
    except Exception:
        pass

    summary = review_row.get("claude_summary") or ""
    if len(summary) > 350:
        truncated = summary[:350].rsplit(".", 1)
        summary = (truncated[0] + ".") if len(truncated) > 1 else summary[:350]

    # Red flags are already the opposite-side conditions; reuse as exit triggers
    exit_triggers = [f"Watch if: {f}" for f in flags[:3]] if flags else []

    return {
        "rationale": summary,
        "risks": flags[:3],
        "exit_triggers": exit_triggers,
        "entry_zone": "",
        "is_synthesized": False,
        "cache_hit": None,
    }


def _fetch_current_price(symbol: str) -> tuple[float | None, str]:
    """Return (price, session) where session is 'after-hours', 'pre-market', or '' (regular/close)."""
    try:
        import yfinance as yf
        from datetime import datetime, timezone, timedelta

        now_utc = datetime.now(timezone.utc)
        # DST approximation: UTC-4 Mar–Nov (EDT), UTC-5 otherwise (EST)
        et_offset = -4 if 3 <= now_utc.month <= 11 else -5
        mins = (now_utc.hour + et_offset) % 24 * 60 + now_utc.minute

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


def synthesize_top_pick(
    top_pick_row,
    runner_ups_df: pd.DataFrame,
    gate_dict: dict,
    open_symbols: list,
) -> dict:
    """Single Anthropic call to synthesize rationale + risks for the #1 pick."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    symbol = top_pick_row["symbol"]
    current_price, price_session = _fetch_current_price(symbol)
    price_str = f"${current_price:.2f}" if current_price else "unknown"

    runner_lines = []
    for _, row in runner_ups_df.iterrows():
        runner_lines.append(
            f"- {row['symbol']}: blended {row.get('blended_score', 0):.1f}/100, "
            f"quant {row.get('quant_score', 0):.1f}/100, "
            f"Claude {row.get('claude_score', 0):.1f}/10"
        )

    flags = []
    try:
        flags = json.loads(top_pick_row.get("red_flags_json") or "[]")
    except Exception:
        pass

    user_msg = f"""Top pick: {symbol}
Current price: {price_str}
Blended score: {top_pick_row.get("blended_score", 0):.2f}/100
Quant score: {top_pick_row.get("quant_score", 0):.1f}/100
Claude score: {top_pick_row.get("claude_score", 0):.1f}/10
Red flags: {flags or "none"}

Macro gate: {gate_dict.get("label", "")} (score {gate_dict.get("score", 0):.1f}, sizing {gate_dict.get("sizing", 0)*100:.0f}%)
Currently held: {", ".join(open_symbols) if open_symbols else "none"}

Runner-ups (ranked #2 and #3):
{chr(10).join(runner_lines) if runner_lines else "none"}

Claude's prior analysis of {symbol}:
{top_pick_row.get("claude_summary", "")}

Provide:
1. A 2-3 sentence synthesized rationale — why is this the strongest trade among candidates right now?
2. 2-4 specific key risks, each on its own line starting with "- "
3. 2-4 exit signals — observable conditions (NOT price targets) that would tell you the thesis is failing and it's time to exit. Think chart behavior, earnings results, macro shifts, or sector signals. Each on its own line starting with "EXIT: "
4. A specific entry price or tight range in dollars (e.g. "$142–$145"). Current price is {price_str} — anchor to that and suggest whether to buy at market, on a slight pullback to a support level, or on a breakout above a resistance level. Be specific with numbers. One line starting with "Entry zone: "
"""

    for attempt in range(5):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=700,
                thinking={"type": "adaptive"},
                system=[{
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_msg}],
            )
            break
        except anthropic.APIStatusError as exc:
            if exc.status_code in (529, 503, 502) and attempt < 4:
                wait = 2 ** attempt  # 1, 2, 4, 8 s
                print(f"  [API overloaded (attempt {attempt+1}/5) — retrying in {wait}s…]")
                time.sleep(wait)
            else:
                raise

    cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    if cache_read > 0:
        print(f"  [{symbol} synthesis: cache hit — {cache_read:,} tokens saved]")
    else:
        print(f"  [{symbol} synthesis: cache miss — system prompt cached for next run]")

    raw = next((b.text for b in response.content if hasattr(b, "text")), "")

    rationale_lines = []
    risks = []
    exit_triggers = []
    entry_zone = ""
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("entry zone:"):
            entry_zone = line.split(":", 1)[1].strip()
        elif line.upper().startswith("EXIT:"):
            exit_triggers.append(line.split(":", 1)[1].strip())
        elif line.startswith("- "):
            risks.append(line[2:].strip())
        elif not risks and not exit_triggers and not entry_zone:
            rationale_lines.append(line)

    return {
        "rationale": " ".join(rationale_lines),
        "risks": risks,
        "exit_triggers": exit_triggers,
        "entry_zone": entry_zone,
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
    top_n = candidates.head(RECOMMEND_TOP_N)
    n = len(top_n)

    if n == 0:
        return []

    sizing_pct = compute_sizing(gate["sizing"], n)
    recs = []

    for rank_idx in range(1, n + 1):
        row = top_n.iloc[rank_idx - 1]
        if rank_idx == 1:
            synthesis = synthesize_top_pick(row, top_n.iloc[1:], gate, list(open_symbols))
            price = synthesis.pop("price_at_scan", None)
            price_session = synthesis.pop("price_session", "")
        else:
            synthesis = compose_runner_up(row)
            price, price_session = _fetch_current_price(row["symbol"])

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
            "is_synthesized": synthesis.get("is_synthesized", False),
            "cache_hit": synthesis.get("cache_hit"),
            "price_at_scan": price,
            "price_session": price_session,
        })

    return recs
