# Forward-Projected Exit Targets — Design Spec

**Date:** 2026-06-24
**Status:** Approved

## Goal

Replace the current exit-target logic — which lets the Claude analyst anchor the
target to the *nearest swing high or 52-week high* — with a **forward-projected,
volatility-based target** that is gated on reward:risk. Stop recommending targets
that sit right on top of the entry (the 52w-high collapse) and stop implicitly
betting that a momentum breakout will stall at its prior high.

## Motivation

The scanner selects 12-1m **momentum leaders** — by construction, names already at
or near new highs. The target is not computed; it is chosen by the model in
`recommendation.py:synthesize_pick`, guided by `technicals.py:144`:

> `"target = nearest swing high or 52w high."`

For a stock at new highs, its nearest swing high *is* the 52w high, and that number
sits right on top of the current price. The two references collapse into one, so the
target lands a sliver above entry. This is:

- **Not useful** — near-zero upside, poor or negative reward:risk.
- **Conceptually backwards** — momentum's premise is that strength continues
  *through* prior highs; capping the target there throws away the breakout's upside.
- **Unguarded** — the `10–25% upside` hint in the tool schema is not enforced, so a
  degenerate target flows straight through to the DB and the execution proposals.

## Principle

The target is a **forward-looking objective** anchored to volatility and the trade's
own risk — not a backward-looking high. A target is only worth taking if its reward
meaningfully exceeds the distance to the stop.

## Approach (settled)

**Approach 3 — Hybrid.** Fix the prompt so the model usually anchors correctly, AND
add a deterministic code-side guard that owns the final number and guarantees the
reward:risk floor. The 2:1 floor acts as a **quality gate** (flag/surface), never as
a target-stretcher — inflating a target to force 2:1 manufactures an unreachable
objective precisely when the stop is wide.

### Parameters (settled)

- Holding horizon: a few days to ~2 weeks, leaning toward the safer multi-week end.
- `TARGET_ATR_MULTIPLE = 3.5` — ~2–3 week volatility projection (expected move ≈
  ATR × √days; ~10 trading days ≈ 3.2×, leaning safe ≈ 3.5×).
- `TARGET_MIN_REWARD_RISK = 2.0` — 2:1 floor.
- `TARGET_MIN_UPSIDE_PCT = 0.05` — a "target" under 5% above entry is degenerate.

## Core contract

New pure function `validate_target()` in `recommendation.py`. The model still
proposes all four price levels; this runs *after* parsing and owns the final target.

```
validate_target(entry_high, stop, atr, model_target) -> (target, flags)

  atr_target = entry_high + TARGET_ATR_MULTIPLE × atr

  # 1. Degenerate guard — catches the 52w-high collapse
  if model_target < entry_high × (1 + TARGET_MIN_UPSIDE_PCT):
        target = atr_target
        flags += "target_recomputed"
  else:
        target = model_target          # model anchored to a real level above entry

  # 2. Reward:risk gate — flags, does NOT inflate
  rr = (target − entry_high) / (entry_high − stop)
  if rr < TARGET_MIN_REWARD_RISK:
        flags += "weak_rr"

  return target, flags
```

Key decisions:

- **Entry anchor = `entry_high`** (top of the no-chasing zone) for both the
  projection and the R:R calc — the conservative worst-case fill. It also guarantees
  `target > entry_high`, preserving the `stop < support < entry_low ≤ entry_high <
  target` ordering the rest of the system assumes.
- **The gate flags, never stretches.** A sub-2:1 trade is surfaced as a risk, not
  disguised with a fantasy target.
- **`atr` fallback:** if `atr` is `None` (rare; very short history), use
  `entry_high × 1.10` as the recomputed target when the model target is degenerate.

## Changes by file

### 1. `src/swing_lab/config.py`
- Add `TARGET_ATR_MULTIPLE = 3.5`, `TARGET_MIN_REWARD_RISK = 2.0`,
  `TARGET_MIN_UPSIDE_PCT = 0.05`. (Per project convention, all thresholds live here.)

### 2. `src/swing_lab/technicals.py`
- In `format_levels_for_prompt`, add a computed reference line using current price as
  the entry proxy:
  > `Projected swing target (entry + 3.5×ATR ≈ +N%): $X`
- Replace the guidance line (`technicals.py:144`):
  - **Old:** `"target = nearest swing high or 52w high."`
  - **New:** `"target = project forward from entry using the ATR-based swing target
    above. For names at or near the 52-week high, do NOT cap the target at the prior
    high — momentum breakouts run through it. Only use a swing high as the target if
    it sits clearly above the entry zone. Target should clear ~2:1 reward vs. the
    stop."`

### 3. `src/swing_lab/recommendation.py`
- Add the `validate_target()` function above.
- Update the `target` field description in `_RECOMMENDATION_TOOL` (`:66`) from
  `"10–25% upside"` to: forward-projected (~ATR-based), clearly above entry, ~2:1
  reward:risk vs. stop, never the prior 52w high for breakout names.
- In `synthesize_pick`, after parsing `entry_low/entry_high/support/stop/target`,
  call `validate_target(entry_high, stop, levels.get("atr_14"), target)`. Replace
  `target` with the returned value and carry the flags.
- **Surface flags:**
  - `weak_rr` → append a human-readable note to `key_risks` (e.g.
    *"Reward:risk only 1.6:1 vs. stop — below 2:1; tighten stop or pass"*). This
    shows in the dashboard and Obsidian with no DB migration.
  - `target_recomputed` → print to the run log only.

## Out of scope (noted)

- **No demotion / hard-filtering** of weak-R:R picks — selection still ranks by
  `blended_score`. R:R-based filtering is possible future work.
- **No DB schema change** — flags ride on `risks_json` / the run log.
- **No downstream display changes** — dashboard pages and execution proposals already
  read `target` as a plain number; ordering is preserved.

## Testing

- Unit tests for `validate_target`:
  - degenerate model target (≤ entry) → recomputed to `atr_target`, `target_recomputed` flag.
  - low-upside model target (< 5% above entry) → recomputed.
  - non-degenerate model target (≥ 5% above entry, e.g. a real overhead swing high) → kept unchanged, even if below the ATR projection.
  - `rr < 2.0` → `weak_rr` flag.
  - `rr ≥ 2.0` → no flag.
  - `atr is None` + degenerate model target → `entry_high × 1.10` fallback.
- `format_levels_for_prompt` emits the projected-target line when ATR is present.
