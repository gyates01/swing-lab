"""Conversational analyst agent with tool use and prompt caching."""
import json
import os
import time

import anthropic

from swing_lab.config import ANALYST_MAX_TURNS, MODEL

_SYSTEM_PROMPT = (
    "You are an AI trading analyst assistant embedded in Swing Lab, a momentum swing trading "
    "research tool.\n\n"
    "You have access to the user's portfolio, scan results, macro gate scores, and trade history "
    "via a project snapshot (updated every 5 minutes) and a set of dynamic lookup tools.\n\n"
    "Your role:\n"
    "- Answer questions about the macro environment, scan results, open positions, and trade history\n"
    "- Look up any ticker on demand (not limited to the S&P 500)\n"
    "- Flag risks, explain momentum signals, and help reason through trade decisions\n"
    "- Be concise and direct — this is a research tool, not a chatbot\n\n"
    "Tool usage guidelines:\n"
    "- For snapshot questions ('what's in the scanner?', 'how's the gate?'), answer from the "
    "snapshot without calling tools\n"
    "- Use `lookup_ticker` for 'what's going on with X?' questions about any stock\n"
    "- Use `deep_dive_ticker` ONLY when the user explicitly asks for a deep dive, full analysis, "
    "or review — it costs tokens and takes ~10s\n"
    "- Use `query_trade_log` for detailed position/history questions beyond the snapshot\n"
    "- Use `query_postmortems` when asked about patterns in past trade outcomes\n"
    "- Use `recompute_gate` when asked if macro conditions have changed since the last snapshot"
)

TOOLS = [
    {
        "name": "lookup_ticker",
        "description": (
            "Fetch lightweight factor data for any stock ticker — momentum (12-1), "
            "fundamentals (revenue YoY, FCF, margins, D/E), sector. "
            "Use for routine 'what's going on with X' questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "deep_dive_ticker",
        "description": (
            "Run the full Claude analyst review pipeline on a single ticker — 1-10 scores, "
            "red flags. ~10s, uses API tokens. Only use when user explicitly asks for a deep dive."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "query_trade_log",
        "description": "Query the user's trade history with optional outcome data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["open", "closed", "all"]},
                "symbol": {"type": "string"},
                "last_n": {"type": "integer"},
            },
        },
    },
    {
        "name": "query_postmortems",
        "description": "Retrieve recent postmortem analyses.",
        "input_schema": {
            "type": "object",
            "properties": {"last_n": {"type": "integer"}},
        },
    },
    {
        "name": "recompute_gate",
        "description": (
            "Run a fresh macro gate computation. "
            "Use when user asks if conditions have changed."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ── Tool implementations ────────────────────────────────────────────────────────

def _tool_lookup_ticker(symbol: str) -> dict:
    from swing_lab.scanner import compute_momentum
    from swing_lab.fundamentals import get_fundamentals
    momentum = compute_momentum(symbol)
    fundamentals = get_fundamentals(symbol)
    fundamentals.pop("data_quality", None)
    return {"symbol": symbol, "momentum_12_1": momentum, **fundamentals}


def _tool_deep_dive_ticker(symbol: str) -> dict:
    import pandas as pd
    from swing_lab.scanner import compute_momentum
    from swing_lab.review import review_candidates
    from swing_lab.db import init_db, save_reviews
    from swing_lab.dashboard.lib import load_scans

    momentum = compute_momentum(symbol)
    candidate_df = pd.DataFrame([{
        "symbol": symbol,
        "sector": "Unknown",
        "momentum": momentum,
        "score": 50.0,
        "gate_sizing": 0.6,
    }])
    reviews_df = review_candidates(candidate_df)
    if reviews_df.empty:
        return {"error": "Review returned no results"}

    scans_df = load_scans(limit=1)
    if not scans_df.empty:
        scan_id = int(scans_df.iloc[0]["scan_id"])
        conn = init_db()
        try:
            save_reviews(conn, scan_id, reviews_df)
        finally:
            conn.close()

    row = reviews_df.iloc[0]
    return {
        "symbol": symbol,
        "claude_score": row.get("claude_score"),
        "blended_score": row.get("blended_score"),
        "red_flags": json.loads(row.get("red_flags_json") or "[]"),
        "summary": row.get("claude_summary"),
    }


def _tool_query_trade_log(status: str, symbol: str | None, last_n: int) -> dict:
    from swing_lab.dashboard.lib import load_trades, load_open_trades
    df = load_open_trades() if status == "open" else load_trades()
    if status == "closed":
        df = df[df["exit_price"].notna()]
    if symbol:
        df = df[df["symbol"].str.upper() == symbol.upper()]
    df = df.head(last_n)
    return {"trades": df.to_dict(orient="records"), "count": len(df)}


def _tool_query_postmortems(last_n: int) -> dict:
    from swing_lab.dashboard.lib import get_conn
    try:
        with get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT postmortem_id, run_at, trade_count, outcome_count, "
                "summary_text, model, cache_hit "
                "FROM postmortems ORDER BY postmortem_id DESC LIMIT ?",
                (last_n,),
            )
            cols = [d[0] for d in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    except Exception as exc:
        return {"error": str(exc)}
    return {"postmortems": rows, "count": len(rows)}


def _tool_recompute_gate() -> dict:
    from swing_lab.dashboard.actions import refresh_gate
    gate = refresh_gate()
    return {
        "score": gate["score"],
        "label": gate["label"],
        "sizing": gate["sizing"],
        "components": gate.get("components", {}),
    }


def _dispatch_tool(name: str, inputs: dict) -> dict:
    try:
        if name == "lookup_ticker":
            return _tool_lookup_ticker(inputs["symbol"].upper())
        if name == "deep_dive_ticker":
            return _tool_deep_dive_ticker(inputs["symbol"].upper())
        if name == "query_trade_log":
            return _tool_query_trade_log(
                status=inputs.get("status", "all"),
                symbol=inputs.get("symbol"),
                last_n=inputs.get("last_n", 20),
            )
        if name == "query_postmortems":
            return _tool_query_postmortems(last_n=inputs.get("last_n", 3))
        if name == "recompute_gate":
            return _tool_recompute_gate()
        return {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        return {"error": str(exc)}


# ── Core turn runner ────────────────────────────────────────────────────────────

def _serialize_messages(messages: list) -> list:
    """Convert Anthropic SDK content blocks to plain dicts for storage/display."""
    result = []
    for msg in messages:
        content = msg["content"]
        if isinstance(content, str):
            result.append({"role": msg["role"], "content": content})
        elif isinstance(content, list):
            serialized = []
            for block in content:
                if isinstance(block, dict):
                    serialized.append(block)
                elif hasattr(block, "model_dump"):
                    serialized.append(block.model_dump())
                else:
                    serialized.append({"type": "text", "text": str(block)})
            result.append({"role": msg["role"], "content": serialized})
        else:
            result.append({"role": msg["role"], "content": str(content)})
    return result


def _snapshot_to_system_text(snapshot: dict) -> str:
    return "## Project Snapshot\n\n" + json.dumps(snapshot, indent=2, default=str)


def run_turn(
    history: list[dict],
    user_msg: str,
    snapshot: dict,
    prev_message_id: str | None = None,
) -> tuple[str, list[dict], dict]:
    """Run one conversational turn (may invoke multiple tool-call rounds).

    Returns:
        (assistant_text, updated_history, telemetry)
        telemetry = {"cache_hit": bool, "tokens_saved": int, "tool_calls": list[str], "message_id": str|None}
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY env var not set")

    client = anthropic.Anthropic(api_key=api_key)
    messages = list(history) + [{"role": "user", "content": user_msg}]
    # Stable persona cached; snapshot excluded from cache (changes every 5 min)
    system = [
        {
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": _snapshot_to_system_text(snapshot),
        },
    ]

    tool_calls_made: list[str] = []
    assistant_text = ""
    cache_read = 0
    last_message_id: str | None = None
    is_first_call = True

    for _turn in range(ANALYST_MAX_TURNS):
        response = None
        for attempt in range(5):
            try:
                response = client.beta.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    betas=["cache-diagnosis-2026-04-07"],
                    thinking={"type": "adaptive"},
                    system=system,
                    tools=TOOLS,
                    messages=messages,
                    diagnostics={"previous_message_id": prev_message_id if is_first_call else last_message_id},
                )
                break
            except anthropic.APIStatusError as exc:
                if exc.status_code in (529, 503, 502) and attempt < 4:
                    wait = 2 ** attempt
                    print(
                        f"  [analyst API overloaded (attempt {attempt+1}/5)"
                        f" — retrying in {wait}s…]"
                    )
                    time.sleep(wait)
                else:
                    raise

        cache_read += getattr(response.usage, "cache_read_input_tokens", 0) or 0
        last_message_id = response.id
        if is_first_call:
            diag = getattr(response, "diagnostics", None)
            if diag:
                reason = getattr(diag, "cache_miss_reason", None)
                status = f"miss ({reason})" if reason else "hit"
                print(f"  [analyst cache] {status}", flush=True)
        is_first_call = False

        if response.stop_reason == "end_turn":
            text_parts = [b.text for b in response.content if hasattr(b, "text")]
            assistant_text = "\n\n".join(text_parts)
            messages.append({"role": "assistant", "content": response.content})
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls_made.append(block.name)
                    result = _dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })
            messages.append({"role": "user", "content": tool_results})

    if cache_read > 0:
        print(f"  [analyst: cache hit — {cache_read:,} tokens saved]")
    else:
        print("  [analyst: cache miss — system prompt cached for next turn]")

    telemetry = {
        "cache_hit": cache_read > 0,
        "tokens_saved": cache_read,
        "tool_calls": tool_calls_made,
        "message_id": last_message_id,
    }
    return assistant_text, _serialize_messages(messages), telemetry
