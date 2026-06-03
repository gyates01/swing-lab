# Fix: Swing Lab silently using the TradingAgents API key

## Context

Swing Lab and TradingAgents are sibling Anthropic API projects on the same Windows box. Commit `afb2294` (2026-06-02) introduced `get_api_key()` in `src/swing_lab/config.py` to route Swing Lab to its own key via the `SWING_LAB_ANTHROPIC_API_KEY` env var, with `ANTHROPIC_API_KEY` as a fallback. The Anthropic console now confirms Swing Lab is still billing the TradingAgents key — the routing is failing silently.

**Root cause** (3 contributing factors):

1. `config.py:54-56` — `get_api_key()` silently falls back to `ANTHROPIC_API_KEY`. On this machine that var is set (Windows user env) to the *same value* as the TradingAgents key. Any process that doesn't have `SWING_LAB_ANTHROPIC_API_KEY` in its env quietly bills TradingAgents.
2. **Zero observability** — nothing logs which key was picked. `review.py:63` raises `"ANTHROPIC_API_KEY env var not set"` which doesn't even name the Swing-Lab-specific var.
3. **No project-local env loading** — no `.env` file, no `python-dotenv`, so the key comes only from inherited shell env. The Windows Task Scheduler entries that run `scripts/nightly_run.ps1` and `scripts/premarket_run.ps1` are the most likely contexts where `SWING_LAB_ANTHROPIC_API_KEY` is missing from the inherited env (neither script references the var, and no `.xml` scheduled-task export is checked in).

**Intended outcome:** Swing Lab uses *only* its dedicated key. If the dedicated key isn't available, it fails loudly with a clear, actionable error — never silently falls through to a sibling project's key.

## Approach

Three small, coordinated changes (per user choices on strictness + .env support):

### 1. Make `get_api_key()` strict — remove silent fallback

**File:** `src/swing_lab/config.py:54-56`

Replace the current `get_api_key()` with a strict version that:
- Reads only `SWING_LAB_ANTHROPIC_API_KEY` (no fallback to `ANTHROPIC_API_KEY`).
- Raises `RuntimeError` with a clear message naming the missing var and pointing at both shell-env and `.env` as remediation paths.
- Returns `str` (not `str | None`), so call-sites can drop their None-checks.

### 2. Load `.env` at the repo root once at config import

**File:** `src/swing_lab/config.py` (top of file) + `pyproject.toml`

- Add `python-dotenv>=1.0` to `pyproject.toml` dependencies.
- At the top of `config.py`, call `load_dotenv()` resolved to the repo root (walk up from `__file__` to find the dir containing `pyproject.toml`, or pass an explicit path). Use `override=False` so shell env still wins if set.
- Create `.env.example` (checked in) documenting the required `SWING_LAB_ANTHROPIC_API_KEY=sk-ant-...` entry.
- Create local `.env` (already gitignored at `.gitignore:20-21`) with the actual Swing Lab key.

This makes the key project-local: any process launched from the repo dir picks it up, regardless of which shell or scheduler invoked it. Fixes the Task Scheduler env-stripping risk without touching the `.ps1` scripts.

### 3. Stop capturing the key at module-import time

**Files:**
- `src/swing_lab/review.py:11` — remove `ANTHROPIC_API_KEY = get_api_key()` module global; call `get_api_key()` inside `review_candidates()` at `review.py:62-65`.
- `src/swing_lab/analyst.py:11` — remove the module-level capture if present; only call `get_api_key()` per turn (already does at line 238-242).

This is a hygiene fix — import-time capture is subtle and surprising (the env at import-time vs call-time can differ). With step 1+2 it's strictly safer.

Already-correct call sites that need no changes once `get_api_key()` returns `str`:
- `src/swing_lab/postmortem.py:43` — already calls `get_api_key()` inline.
- `src/swing_lab/recommendation.py:174` — same.

## Critical files

| File | Change |
|---|---|
| `src/swing_lab/config.py` | Add `load_dotenv()` at top; rewrite `get_api_key()` as strict. |
| `pyproject.toml` | Add `python-dotenv>=1.0` to `dependencies`. |
| `src/swing_lab/review.py` | Drop module-level `ANTHROPIC_API_KEY`; call `get_api_key()` inside `review_candidates()`. |
| `src/swing_lab/analyst.py` | Drop any module-level key capture; rely on per-turn `get_api_key()`. |
| `.env.example` (new) | Template: `SWING_LAB_ANTHROPIC_API_KEY=sk-ant-api03-...` |
| `.env` (new, local only) | Actual key value; gitignored via existing `.gitignore:20`. |

No changes needed to: `.gitignore` (`.env` already excluded), `scripts/*.ps1` (`.env` loading covers them), `postmortem.py`, `recommendation.py`.

## Reuse notes

- No existing `dotenv` usage in the project (confirmed by grep — zero matches). This is the first introduction of `python-dotenv`.
- `get_api_key()` is already the single source of truth — keeping that abstraction; just tightening its behavior.

## Verification

End-to-end checks the user (or I) should run after implementation:

1. **Strictness check.** In a fresh PowerShell where `SWING_LAB_ANTHROPIC_API_KEY` is unset (`Remove-Item Env:SWING_LAB_ANTHROPIC_API_KEY`) and no `.env` exists, run `uv run swing-lab review`. Expect: `RuntimeError: SWING_LAB_ANTHROPIC_API_KEY not set...` — naming the right var. Proves the silent fallback is gone.

2. **`.env` loading.** Clear the shell var as above, then create `.env` with the Swing Lab key. Run `uv run swing-lab review`. Expect: success. Proves `.env` is loaded.

3. **Shell env still wins (precedence).** With both `.env` and a different value in `$env:SWING_LAB_ANTHROPIC_API_KEY`, confirm the shell value is used (via `python -c "from swing_lab.config import get_api_key; print(get_api_key()[-4:])"` showing the shell suffix). Validates `override=False`.

4. **Billing confirmation.** After ~24h of normal use (1 nightly run + 1 premarket run + any interactive use), open the Anthropic console:
   - Swing Lab key suffix should show fresh usage.
   - TradingAgents key suffix should show **no new** usage attributable to Swing Lab runs (only TradingAgents activity).
   - This is the ground-truth signal the user originally used to detect the bug.

5. **Scheduled-task smoke test.** Manually trigger `scripts/nightly_run.ps1` (run it from PowerShell in the repo dir). Confirm: the run completes without the new RuntimeError, results land in `results/`, and the run-log in `results/nightly.log` shows a clean `gate complete` / `scan complete`. (Note: `gate` and `scan` don't actually call Anthropic — they exercise the config import path, which is what we need to verify.) Then watch the next real 2am ET run.

6. **Premarket Claude path.** Trigger `scripts/premarket_run.ps1` manually — this *does* call Anthropic via `swing-lab review`. Confirms the scheduled-task context can read the key and successfully bills the Swing Lab account.

## Out of scope

- Modifying the `.ps1` scripts to explicitly check for the env var (`.env` loading at config import covers this).
- Adding a `swing-lab whoami` debug subcommand (could be a follow-up if observability is wanted; not needed once fail-loud is in place).
- Auditing TradingAgents itself for mirror-image issues.
