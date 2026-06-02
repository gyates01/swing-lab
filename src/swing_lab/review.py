"""Claude analyst review layer for top momentum candidates."""
import json
import os

import anthropic
import pandas as pd

from swing_lab.config import MODEL, REVIEW_TOP_N, get_api_key
from swing_lab.fundamentals import get_fundamentals

ANTHROPIC_API_KEY = get_api_key()

SYSTEM_PROMPT = """You are a buyside equity analyst performing fundamental due diligence.
Your job: score each stock candidate 1–10 on four dimensions, identify red flags,
and give a one-line investment thesis summary.

Scoring criteria:
- earnings_quality (1–10): Revenue consistency, FCF generation vs net income, accruals risk
- growth (1–10): Revenue YoY growth rate and trajectory
- balance_sheet (1–10): Debt-to-equity, coverage ratios, balance sheet stress
- margins (1–10): Gross and operating margin levels vs. sector norms

composite_1_to_10: Weighted average (earnings_quality 30%, growth 25%, balance_sheet 20%, margins 25%)

red_flags: List specific concerns (e.g., "negative FCF despite positive net income", "D/E > 3x").
If none, return an empty list.

one_line_summary: One sentence stating the investment thesis or primary concern.

Respond ONLY with valid JSON matching this exact schema:
{
  "symbol": "string",
  "scores": {
    "earnings_quality": number,
    "growth": number,
    "balance_sheet": number,
    "margins": number
  },
  "composite_1_to_10": number,
  "red_flags": ["string"],
  "one_line_summary": "string"
}"""


def blend(quant_score: float, claude_score: float, w_quant: float = 0.6, w_claude: float = 0.4) -> float:
    """Weighted blend of quant and claude scores (both on 0-100 scale)."""
    return w_quant * quant_score + w_claude * claude_score


def review_candidates(top_n_df: pd.DataFrame, progress=None) -> pd.DataFrame:
    """Run Claude analyst review on top momentum candidates.

    Args:
        top_n_df: DataFrame with columns symbol, sector, momentum, score, gate_sizing.
        progress: optional callable(current, total, symbol) for UI progress bars.

    Returns:
        DataFrame with columns:
            symbol, sector, momentum, quant_score, claude_score,
            blended_score, red_flags_json, claude_summary
    """
    if ANTHROPIC_API_KEY is None:
        raise RuntimeError("ANTHROPIC_API_KEY env var not set")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    candidates = top_n_df.head(REVIEW_TOP_N).copy()

    results = []
    total = len(candidates)
    prev_id: str | None = None

    for i, (_, row) in enumerate(candidates.iterrows(), start=1):
        symbol = row["symbol"]
        print(f"  Reviewing {symbol} ({i}/{total})...")
        if progress:
            progress(i, total, symbol)

        fundamentals = get_fundamentals(symbol)
        dq = fundamentals.pop("data_quality", {})
        dq_note = ""
        if dq:
            stale = [f"{k}={v}" for k, v in dq.items() if v not in ("quarterly", "missing")]
            missing = [k for k, v in dq.items() if v == "missing"]
            if stale:
                dq_note += f"\nData quality notes: {', '.join(stale)} (source not TTM)"
            if missing:
                dq_note += f"\nMissing fields (treat as unknown, do not assume): {', '.join(missing)}"

        try:
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=1024,
                betas=["cache-diagnosis-2026-04-07"],
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Analyze this candidate:\n\n{json.dumps(fundamentals, indent=2)}"
                            + (f"\n{dq_note}" if dq_note else "")
                        ),
                    }
                ],
                diagnostics={"previous_message_id": prev_id},
            )
            prev_id = response.id

            # Check for cache hit and diagnostics
            usage = getattr(response, "usage", None)
            if usage is not None:
                cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
                diag = getattr(response, "diagnostics", None)
                if diag:
                    reason = getattr(diag, "cache_miss_reason", None)
                    status = f"miss ({reason})" if reason else "hit"
                    print(f"  [cache diag] {symbol}: {status}")
                elif cache_read > 0:
                    print("  [cache hit]")

            raw_text = response.content[0].text
            claude_data = json.loads(raw_text)

        except json.JSONDecodeError:
            print(f"  WARNING: Failed to parse Claude response for {symbol} — skipping")
            continue
        except Exception as exc:
            print(f"  WARNING: Claude call failed for {symbol}: {exc} — skipping")
            continue

        quant_score = float(row.get("score", 0.0))
        claude_score_raw = float(claude_data.get("composite_1_to_10", 5.0))
        # Scale claude score (1-10) to 0-100 for blending
        blended = blend(quant_score, claude_score_raw * 10)

        results.append(
            {
                "symbol": symbol,
                "sector": row.get("sector"),
                "momentum": row.get("momentum"),
                "quant_score": quant_score,
                "claude_score": claude_score_raw,
                "blended_score": blended,
                "red_flags_json": json.dumps(claude_data.get("red_flags", [])),
                "claude_summary": claude_data.get("one_line_summary", ""),
            }
        )

    return pd.DataFrame(results)
