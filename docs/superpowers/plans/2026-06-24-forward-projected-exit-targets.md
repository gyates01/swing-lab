# Forward-Projected Exit Targets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 52w-high/swing-high target anchoring with an ATR-projected, 2:1-reward:risk-gated exit target so the recommendation engine stops emitting degenerate near-entry targets.

**Architecture:** The Claude analyst still proposes all four price levels in `synthesize_pick`. A new pure `validate_target()` runs after parsing and owns the final target: it recomputes degenerate targets (≤ a 5% upside floor) to an ATR projection and flags sub-2:1 reward:risk. The prompt and tool schema are updated so the model usually anchors correctly on its own. Weak-R:R picks are flagged (appended to `key_risks`), not filtered.

**Tech Stack:** Python 3.11+, pandas, yfinance, anthropic SDK, pytest, uv.

## Global Constraints

- Python 3.11+; run everything via `uv run`.
- All thresholds/constants live in `src/swing_lab/config.py` — never hardcode them elsewhere; import from config.
- Tests are pytest, plain functions, no classes (match `tests/test_recommendation_picks.py`).
- The price-level ordering `stop < support < entry_low ≤ entry_high < target` must always hold downstream.
- Frequent commits — one per task. TDD: failing test first.

---

### Task 1: Core target validation logic + config constants

**Files:**
- Modify: `src/swing_lab/config.py` (add 3 constants in the "Recommendation engine" block)
- Modify: `src/swing_lab/recommendation.py` (add `reward_risk`, `validate_target`, `risks_with_target_flags`; extend the config import)
- Test: `tests/test_target_validation.py` (create)

**Interfaces:**
- Consumes: `TARGET_ATR_MULTIPLE`, `TARGET_MIN_REWARD_RISK`, `TARGET_MIN_UPSIDE_PCT` from `config`.
- Produces:
  - `reward_risk(entry_high: float, stop: float, target: float) -> float`
  - `validate_target(entry_high: float, stop: float, atr: float | None, model_target: float) -> tuple[float, list[str]]` — returns `(target, flags)` where flags ⊆ `{"target_recomputed", "weak_rr"}`
  - `risks_with_target_flags(risks: list[str], flags: list[str], rr: float) -> list[str]`

- [ ] **Step 1: Add config constants**

In `src/swing_lab/config.py`, after the `RECOMMEND_SECOND_PICK_MIN_SCORE` line (currently `:36`):

```python
# Exit-target projection + reward:risk gate
TARGET_ATR_MULTIPLE = 3.5        # ATR multiple for forward-projected swing target (~2-3wk horizon)
TARGET_MIN_REWARD_RISK = 2.0     # min (target-entry_high)/(entry_high-stop); below this → weak_rr flag
TARGET_MIN_UPSIDE_PCT = 0.05     # a target under this % above entry_high is degenerate → recomputed
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_target_validation.py`:

```python
from swing_lab.recommendation import (
    reward_risk,
    validate_target,
    risks_with_target_flags,
)
from swing_lab.config import TARGET_ATR_MULTIPLE


def test_degenerate_target_recomputed_to_atr_projection():
    # model target sits ~1% above entry → recompute to entry_high + k*ATR
    target, flags = validate_target(entry_high=100.0, stop=94.0, atr=2.0, model_target=101.0)
    assert target == 100.0 + TARGET_ATR_MULTIPLE * 2.0
    assert "target_recomputed" in flags


def test_low_upside_target_recomputed():
    # 3% above entry < 5% floor → degenerate
    _, flags = validate_target(entry_high=100.0, stop=94.0, atr=2.0, model_target=103.0)
    assert "target_recomputed" in flags


def test_good_model_target_kept():
    # 12% above entry, a real level → kept unchanged
    target, flags = validate_target(entry_high=100.0, stop=94.0, atr=2.0, model_target=112.0)
    assert target == 112.0
    assert "target_recomputed" not in flags


def test_weak_reward_risk_flagged():
    # reward 7 / risk 6 = 1.17 < 2.0
    _, flags = validate_target(entry_high=100.0, stop=94.0, atr=0.5, model_target=107.0)
    assert "weak_rr" in flags


def test_healthy_reward_risk_not_flagged():
    # reward 15 / risk 6 = 2.5 >= 2.0
    _, flags = validate_target(entry_high=100.0, stop=94.0, atr=2.0, model_target=115.0)
    assert "weak_rr" not in flags


def test_atr_none_degenerate_uses_ten_pct_fallback():
    target, flags = validate_target(entry_high=100.0, stop=94.0, atr=None, model_target=100.5)
    assert target == 100.0 * 1.10
    assert "target_recomputed" in flags


def test_reward_risk_zero_when_no_risk():
    assert reward_risk(entry_high=100.0, stop=100.0, target=120.0) == 0.0


def test_weak_rr_note_appended_without_mutating_input():
    risks = ["Sector rotation risk"]
    out = risks_with_target_flags(risks, ["weak_rr"], rr=1.6)
    assert len(out) == 2
    assert "1.6:1" in out[1]
    assert risks == ["Sector rotation risk"]  # original list untouched


def test_no_note_without_weak_rr_flag():
    assert risks_with_target_flags(["X"], ["target_recomputed"], rr=3.0) == ["X"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_target_validation.py -v`
Expected: FAIL — `ImportError: cannot import name 'reward_risk' from 'swing_lab.recommendation'`

- [ ] **Step 4: Extend the config import in `recommendation.py`**

In `src/swing_lab/recommendation.py`, change the existing import block (`:7-10`) to add the three constants:

```python
from swing_lab.config import (
    DATA_DIR, MAX_POSITION_PCT, MODEL, RECOMMEND_TOP_N,
    RECOMMEND_RED_FLAG_MAX, RECOMMEND_SECOND_PICK_MIN_SCORE, get_api_key,
    TARGET_ATR_MULTIPLE, TARGET_MIN_REWARD_RISK, TARGET_MIN_UPSIDE_PCT,
)
```

- [ ] **Step 5: Implement the three functions**

In `src/swing_lab/recommendation.py`, add these above `synthesize_pick` (e.g. right after `_fetch_current_price`):

```python
def reward_risk(entry_high: float, stop: float, target: float) -> float:
    """Reward:risk = (target - entry_high) / (entry_high - stop). 0.0 if risk <= 0."""
    risk = entry_high - stop
    if risk <= 0:
        return 0.0
    return (target - entry_high) / risk


def validate_target(
    entry_high: float,
    stop: float,
    atr: float | None,
    model_target: float,
) -> tuple[float, list[str]]:
    """Own the final target. Recompute degenerate model targets (≤ the upside floor)
    to a forward ATR projection; flag sub-threshold reward:risk. Anchored to
    entry_high (top of the no-chasing zone) — the conservative worst-case fill, which
    also guarantees target > entry_high so price-level ordering holds.
    Returns (target, flags) with flags ⊆ {"target_recomputed", "weak_rr"}."""
    flags: list[str] = []
    atr_target = entry_high + TARGET_ATR_MULTIPLE * atr if atr is not None else entry_high * 1.10

    if model_target < entry_high * (1 + TARGET_MIN_UPSIDE_PCT):
        target = atr_target
        flags.append("target_recomputed")
    else:
        target = model_target

    if reward_risk(entry_high, stop, target) < TARGET_MIN_REWARD_RISK:
        flags.append("weak_rr")

    return target, flags


def risks_with_target_flags(risks: list[str], flags: list[str], rr: float) -> list[str]:
    """Return a copy of `risks` with a human-readable weak-R:R note appended when flagged."""
    out = list(risks)
    if "weak_rr" in flags:
        out.append(
            f"Reward:risk only {rr:.1f}:1 vs. stop — below "
            f"{TARGET_MIN_REWARD_RISK:.0f}:1; tighten stop or pass"
        )
    return out
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_target_validation.py -v`
Expected: PASS (9 passed)

- [ ] **Step 7: Commit**

```bash
git add src/swing_lab/config.py src/swing_lab/recommendation.py tests/test_target_validation.py
git commit -m "feat: ATR-projected exit target with 2:1 reward:risk gate"
```

---

### Task 2: Wire validation into `synthesize_pick`

**Files:**
- Modify: `src/swing_lab/recommendation.py` (`synthesize_pick`, `:255-279`)

**Interfaces:**
- Consumes: `validate_target`, `reward_risk`, `risks_with_target_flags`, `TARGET_ATR_MULTIPLE` (Task 1).
- Produces: no new public symbols. `synthesize_pick`'s returned dict keeps its keys; `target` is now the validated value and `risks` includes any weak-R:R note.

- [ ] **Step 1: Insert validation after the levels are parsed**

In `synthesize_pick`, replace the block at `:259-263`:

```python
    target     = float(args["target"])
    entry_zone_text = (
        f"${entry_low:.2f}–${entry_high:.2f}; "
        f"support at ${support:.2f}; stop below ${stop:.2f}; target ${target:.2f}"
    )
```

with:

```python
    target     = float(args["target"])

    atr = levels.get("atr_14")
    target, target_flags = validate_target(entry_high, stop, atr, target)
    rr = reward_risk(entry_high, stop, target)
    risks = risks_with_target_flags(args.get("key_risks") or [], target_flags, rr)
    if "target_recomputed" in target_flags:
        print(f"  [{symbol}] target recomputed to ${target:.2f} "
              f"(model target was degenerate; entry_high + {TARGET_ATR_MULTIPLE}×ATR)")

    entry_zone_text = (
        f"${entry_low:.2f}–${entry_high:.2f}; "
        f"support at ${support:.2f}; stop below ${stop:.2f}; target ${target:.2f}"
    )
```

- [ ] **Step 2: Use the augmented risks in the return dict**

In the same function, change the returned `"risks"` value (`:267`) from:

```python
        "risks": args.get("key_risks") or [],
```

to:

```python
        "risks": risks,
```

(Leave `"target": target` as-is — it now references the validated value.)

- [ ] **Step 3: Verify no regressions across the suite**

Run: `uv run pytest -q`
Expected: PASS — all existing tests plus Task 1's 9 tests green. (`synthesize_pick` itself makes a live API call and is not unit-tested in this codebase; the pure logic it now calls is covered by `tests/test_target_validation.py`.)

- [ ] **Step 4: Smoke-check the wiring imports and resolves**

Run: `uv run python -c "from swing_lab.recommendation import synthesize_pick, validate_target; print('ok')"`
Expected: prints `ok` with no ImportError.

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/recommendation.py
git commit -m "feat: validate synthesized target + surface weak reward:risk"
```

---

### Task 3: Update analyst prompt + tool schema

**Files:**
- Modify: `src/swing_lab/technicals.py` (`format_levels_for_prompt`, `:103-147`; add config import)
- Modify: `src/swing_lab/recommendation.py` (`_RECOMMENDATION_TOOL` target description, `:65-66`)
- Test: `tests/test_levels_prompt.py` (create)

**Interfaces:**
- Consumes: `TARGET_ATR_MULTIPLE` from `config`.
- Produces: `format_levels_for_prompt` output now includes a `Projected swing target (...)` line when ATR and current price are present, and the guidance no longer says "nearest swing high or 52w high".

- [ ] **Step 1: Write the failing tests**

Create `tests/test_levels_prompt.py`:

```python
from swing_lab.technicals import format_levels_for_prompt


def _levels():
    return {
        "price_52w_high": 110.0,
        "price_52w_low": 70.0,
        "ma_20": 98.0, "ma_50": 95.0, "ma_200": 88.0,
        "atr_14": 2.0,
        "swing_highs": [(108.0, 10)],
        "swing_lows": [(95.0, 20)],
    }


def test_projected_target_line_present():
    out = format_levels_for_prompt(_levels(), current_price=100.0)
    assert "Projected swing target" in out


def test_guidance_no_longer_caps_at_52w_high():
    out = format_levels_for_prompt(_levels(), current_price=100.0)
    assert "nearest swing high or 52w high" not in out
    assert "do NOT cap the target at the prior high" in out


def test_no_projected_line_without_atr():
    levels = _levels()
    levels["atr_14"] = None
    out = format_levels_for_prompt(levels, current_price=100.0)
    assert "Projected swing target" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_levels_prompt.py -v`
Expected: FAIL — `test_projected_target_line_present` and `test_guidance_no_longer_caps_at_52w_high` fail (string not present / old guidance still there).

- [ ] **Step 3: Add the config import to `technicals.py`**

At the top of `src/swing_lab/technicals.py`, after the existing imports (`:1-3`):

```python
from swing_lab.config import TARGET_ATR_MULTIPLE
```

- [ ] **Step 4: Add the projected-target line**

In `format_levels_for_prompt`, after the ATR block (`:126-129`), add:

```python
    if atr is not None and current_price:
        proj = current_price + TARGET_ATR_MULTIPLE * atr
        proj_pct = (proj / current_price - 1) * 100
        lines.append(
            f"Projected swing target (entry + {TARGET_ATR_MULTIPLE}×ATR ≈ +{proj_pct:.0f}%): ${proj:.2f}"
        )
```

- [ ] **Step 5: Replace the guidance line**

Replace the `lines.append(...)` guidance block at `:141-145`:

```python
    lines.append(
        "Guidance: entry zone should bracket a nearby MA or the most recent swing low; "
        "support = next swing low below entry; stop = support minus 0.5–1× ATR; "
        "target = nearest swing high or 52w high."
    )
```

with:

```python
    lines.append(
        "Guidance: entry zone should bracket a nearby MA or the most recent swing low; "
        "support = next swing low below entry; stop = support minus 0.5–1× ATR; "
        "target = project forward from entry using the ATR-based swing target above. "
        "For names at or near the 52-week high, do NOT cap the target at the prior high — "
        "momentum breakouts run through it. Only use a swing high as the target if it sits "
        "clearly above the entry zone, and target should clear ~2:1 reward vs. the stop."
    )
```

- [ ] **Step 6: Update the tool schema target description**

In `src/swing_lab/recommendation.py`, replace the `target` property in `_RECOMMENDATION_TOOL` (`:65-66`):

```python
            "target":       {"type": "number",
                             "description": "Realistic profit target price in dollars (10–25% upside from entry)."},
```

with:

```python
            "target":       {"type": "number",
                             "description": "Forward-projected profit target in dollars (~ATR-based), clearly "
                                            "above the entry zone and ideally clearing 2:1 reward vs. the stop. "
                                            "Do NOT set this at the prior 52-week high for breakout names."},
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_levels_prompt.py -v`
Expected: PASS (3 passed)

- [ ] **Step 8: Full suite green**

Run: `uv run pytest -q`
Expected: PASS — entire suite green.

- [ ] **Step 9: Commit**

```bash
git add src/swing_lab/technicals.py src/swing_lab/recommendation.py tests/test_levels_prompt.py
git commit -m "feat: prompt + schema project targets forward instead of capping at 52w high"
```

---

## Notes for the implementer

- Do **not** add a DB migration — weak-R:R surfaces through `risks_json` (already persisted) and `target_recomputed` only logs to stdout.
- Do **not** change dashboard pages or execution proposals — they read `target` as a plain number and the ordering invariant is preserved.
- Do **not** demote or filter weak-R:R picks; selection still ranks by `blended_score`. Flagging only.
- The `–` characters in the guidance/notes are en-dashes (U+2013), matching the existing file; keep them.
