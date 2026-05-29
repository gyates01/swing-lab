"""Claude-powered trade postmortem analysis with prompt caching and structured outcome data."""
import json
import os
import time
import anthropic

from swing_lab.config import MODEL

_SYSTEM_PROMPT = (
    "You are a trading coach analyzing a student's recent swing trades. "
    "You have access to structured outcome data: which predicted risks materialized, "
    "which exit triggers fired, whether the thesis was validated, and what drove the exit. "
    "Use this data to identify patterns in prediction accuracy — not just P&L. "
    "Focus on: which rec signals are predictive vs. noise, what thesis validation rates look like "
    "across exit drivers, and whether macro regime alignment correlates with outcomes. "
    "Be specific and reference actual symbols and scores. Be actionable."
)


def analyze_trades_with_context(trade_rows: list[dict]) -> dict:
    """Send trades (with outcome + rec context) to Claude. Returns summary dict."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    if not trade_rows:
        return {
            "summary_text": "No closed trades to analyze.",
            "cache_hit": None,
            "model": MODEL,
            "trade_count": 0,
            "outcome_count": 0,
        }

    outcome_count = sum(1 for r in trade_rows if r.get("thesis_validated") is not None)

    lines = []
    for r in trade_rows:
        symbol = r.get("symbol", "?")
        entry = r.get("entry_price")
        exit_p = r.get("exit_price")
        pnl_pct = r.get("pnl_pct")
        opened = str(r.get("opened_at", ""))[:10]
        closed = str(r.get("closed_at", ""))[:10]
        pnl_str = f"{pnl_pct*100:+.1f}%" if pnl_pct is not None else "unknown"

        header = f"Trade: {symbol} | Entry ${entry:.2f} on {opened} → Exit ${exit_p:.2f} on {closed} | P&L {pnl_str}"

        if r.get("blended_score") is not None:
            header += f" | Rec blended score {r['blended_score']:.1f}/100, gate sizing {r['gate_sizing']*100:.0f}%"

        parts = [header]

        risks = []
        try:
            risks = json.loads(r.get("risks_json") or "[]")
        except Exception:
            pass
        if risks:
            parts.append(f"  Predicted risks: {'; '.join(risks)}")

        if r.get("thesis_validated"):
            parts.append(f"  Outcome — thesis validated: {r['thesis_validated']}, exit driver: {r.get('exit_driver', '?')}")
            mats = []
            try:
                mats = json.loads(r.get("red_flags_materialized_json") or "[]")
            except Exception:
                pass
            fired = []
            try:
                fired = json.loads(r.get("exit_triggers_fired_json") or "[]")
            except Exception:
                pass
            if mats:
                parts.append(f"  Red flags that materialized: {'; '.join(mats)}")
            if fired:
                parts.append(f"  Exit triggers that fired: {'; '.join(fired)}")
            if r.get("macro_aligned"):
                parts.append(f"  Macro regime aligned: {r['macro_aligned']}")
            if r.get("notes"):
                parts.append(f"  Notes: {r['notes']}")
        else:
            parts.append("  Outcome: no structured data captured at close")

        lines.append("\n".join(parts))

    user_msg = (
        f"Here are my last {len(trade_rows)} closed trades "
        f"({outcome_count} with full outcome data, {len(trade_rows)-outcome_count} legacy):\n\n"
        + "\n\n".join(lines)
        + "\n\nPlease analyze: prediction accuracy (did flagged risks/exits hold up?), "
        "thesis validation rate by exit driver, any macro alignment patterns, "
        "and what I should specifically watch in future recommendations."
    )

    for attempt in range(5):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1500,
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
                wait = 2 ** attempt
                print(f"  [postmortem API overloaded (attempt {attempt+1}/5) — retrying in {wait}s…]")
                time.sleep(wait)
            else:
                raise

    cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    if cache_read > 0:
        print(f"  [postmortem: cache hit — {cache_read:,} tokens saved]")
    else:
        print(f"  [postmortem: cache miss — system prompt cached for next run]")

    text_parts = [block.text for block in response.content if hasattr(block, "text")]
    summary = "\n\n".join(text_parts)

    return {
        "summary_text": summary,
        "cache_hit": 1 if cache_read > 0 else 0,
        "model": MODEL,
        "trade_count": len(trade_rows),
        "outcome_count": outcome_count,
    }


def analyze_trades(trades: list[dict]) -> str:
    """Legacy shim: send raw trade dicts without context. Returns text string."""
    result = analyze_trades_with_context(trades)
    return result["summary_text"]
