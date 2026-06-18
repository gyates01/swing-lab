# Execution Price Levels & Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface each pending **buy** proposal's entry/support/stop/target levels and a candlestick chart on the Execution tab, reusing the Recommendation tab's components.

**Architecture:** Buy orders already store `rec_id`, a foreign key into `recommendations`, which holds Claude-generated `entry_low/entry_high/support/stop_price/target`. Add a `load_recommendation(conn, rec_id)` DB helper, then wire the existing `theme.zone_kpi_grid_html` (cheap, always rendered) and `charts.candle_chart` (lazy, inside a per-order `st.expander`) into the pending-queue loop of `pages/7_Execution.py`. No new charting code, no extra Claude call, no live-quote polling (the chart fetches its own history only when expanded).

**Tech Stack:** Python 3.11, SQLite, Streamlit, Plotly (via existing `charts.candle_chart`), pytest.

**Out of scope (deferred follow-up):** live stop/target *tracking* — i.e. flagging "price is below stop" or "hit target" on open positions. This plan only *displays* the static levels.

---

### Task 1: `load_recommendation(conn, rec_id)` DB helper

**Files:**
- Modify: `src/swing_lab/db.py` (add function after `load_latest_recommendations`, ~line 343)
- Test: `tests/test_rec_load.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_rec_load.py`:

```python
from datetime import datetime, timezone


def _insert_rec(conn, **levels):
    cols = ("rec_id", "batch_id", "created_at", "scan_id", "rank", "symbol",
            "sizing_pct", "gate_sizing", "entry_low", "entry_high",
            "support", "stop_price", "target")
    row = {
        "rec_id": 1, "batch_id": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "scan_id": 1, "rank": 1, "symbol": "ALB", "sizing_pct": 0.08, "gate_sizing": 1.0,
        "entry_low": 160.0, "entry_high": 168.0, "support": 150.0,
        "stop_price": 145.0, "target": 190.0,
    }
    row.update(levels)
    placeholders = ", ".join("?" for _ in cols)
    conn.execute(f"INSERT INTO recommendations ({', '.join(cols)}) VALUES ({placeholders})",
                 tuple(row[c] for c in cols))
    conn.commit()


def test_load_recommendation_returns_levels(db_conn):
    from swing_lab.db import load_recommendation
    _insert_rec(db_conn)
    rec = load_recommendation(db_conn, 1)
    assert rec["symbol"] == "ALB"
    assert rec["entry_low"] == 160.0 and rec["entry_high"] == 168.0
    assert rec["support"] == 150.0 and rec["stop_price"] == 145.0 and rec["target"] == 190.0


def test_load_recommendation_missing_returns_none(db_conn):
    from swing_lab.db import load_recommendation
    assert load_recommendation(db_conn, 999) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rec_load.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_recommendation'`.

- [ ] **Step 3: Write minimal implementation**

In `src/swing_lab/db.py`, immediately after `load_latest_recommendations` (ends ~line 342), add:

```python
def load_recommendation(conn, rec_id: int) -> dict | None:
    """Return one recommendation row (with price levels + claude_summary) by id, or None."""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT r.rec_id, r.batch_id, r.created_at, r.scan_id, r.review_id, r.rank, r.symbol,
                  r.blended_score, r.sizing_pct, r.gate_sizing, r.rationale, r.risks_json,
                  r.exit_triggers_json, r.entry_zone, r.is_synthesized, r.cache_hit,
                  r.price_at_scan, r.price_session,
                  r.entry_low, r.entry_high, r.support, r.stop_price, r.target,
                  rv.claude_summary
           FROM recommendations r
           LEFT JOIN reviews rv ON r.review_id = rv.review_id
           WHERE r.rec_id = ?""",
        (rec_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rec_load.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swing_lab/db.py tests/test_rec_load.py
git commit -m "feat: add load_recommendation(conn, rec_id) helper"
```

---

### Task 2: Render levels + lazy chart on pending buys

**Files:**
- Modify: `src/swing_lab/dashboard/pages/7_Execution.py` (imports + pending-queue loop, ~lines 5-14 and ~37-56)

> No unit test: this is Streamlit view code that runs `st.*` at import time and has no test harness in this repo. Verified manually in the browser (Step 4). This matches how the sibling Recommendation page (`pages/5_Recommendation.py`) is exercised.

- [ ] **Step 1: Add imports**

In `src/swing_lab/dashboard/pages/7_Execution.py`, update the import block. Add `load_recommendation` to the db import and import the two view helpers:

```python
from swing_lab.db import init_db, load_recommendation
from swing_lab.dashboard.charts import candle_chart
from swing_lab.dashboard.theme import inject, render_topbar, zone_kpi_grid_html
```

(Keep the existing `from swing_lab.dashboard.theme import inject, render_topbar` — merge `zone_kpi_grid_html` into it rather than duplicating the import line.)

- [ ] **Step 2: Render the grid + lazy chart inside the pending loop**

In the `for o in pending:` loop, after the Approve/Reject column block (currently ending at the `c4.button("Reject", ...)` / `st.rerun()` lines, ~line 56), append — still inside the loop, at the same indentation as `c1, c2, c3, c4 = st.columns(...)`:

```python
    if o["side"] == "buy":
        rec = load_recommendation(conn, o["rec_id"]) if o["rec_id"] is not None else None
        has_levels = bool(rec and rec.get("entry_low") is not None
                          and rec.get("stop_price") is not None)
        if has_levels:
            entry_mid = (rec["entry_low"] + rec["entry_high"]) / 2
            st.markdown(
                zone_kpi_grid_html(rec["stop_price"], rec["support"], entry_mid,
                                   rec["target"], o["est_price"],
                                   entry_range=(rec["entry_low"], rec["entry_high"])),
                unsafe_allow_html=True,
            )
        with st.expander(f"{o['symbol']} chart"):
            chart = candle_chart(
                o["symbol"], price=o["est_price"], period="3mo", height=320,
                trade_entry_price=o["est_price"],
                entry_low=rec["entry_low"] if has_levels else None,
                entry_high=rec["entry_high"] if has_levels else None,
                support=rec["support"] if has_levels else None,
                stop=rec["stop_price"] if has_levels else None,
                target=rec["target"] if has_levels else None,
            )
            if chart:
                st.plotly_chart(chart, use_container_width=True)
```

- [ ] **Step 3: Byte-compile (catches syntax/indent errors — the page can't be imported standalone)**

Run: `uv run python -m py_compile "src/swing_lab/dashboard/pages/7_Execution.py"`
Expected: no output, exit 0.

- [ ] **Step 4: Manual browser verification**

Run: `uv run streamlit run src/swing_lab/dashboard/Home.py` (or the project's dashboard entrypoint), open the **Execution** page, click **Generate proposals** during market hours.
Expected:
- The buy derived from the #1 recommendation shows a 4-card STOP / SUPPORT / ENTRY / TARGET grid with % deltas vs `est_price`.
- Every buy shows a collapsed "{SYMBOL} chart" expander; opening it renders a candlestick (with level overlays when present).
- Runner-up buys (no DB levels) show the chart but no grid — consistent with the Recommendation page.
- Approve/Reject still work; clicking them does not auto-open the chart expanders (confirms charts stay lazy and yfinance isn't hit on every rerun).

- [ ] **Step 5: Commit**

```bash
git add "src/swing_lab/dashboard/pages/7_Execution.py"
git commit -m "feat: show entry/stop/target levels + lazy chart on execution buys"
```

---

## Self-Review

- **Spec coverage:** (1) entry/support/stop/target on Execution buys → Task 2 grid via `zone_kpi_grid_html`. (2) "how are prices tracked" → answered in conversation (point-in-time `get_quote`; no change needed). (3) add a graph → Task 2 lazy `candle_chart`. Live tracking explicitly deferred.
- **Placeholder scan:** none — full code + exact commands in every step.
- **Type consistency:** `load_recommendation(conn, rec_id)` defined in Task 1 is the exact name/signature used in Task 2. Column names (`entry_low`, `entry_high`, `support`, `stop_price`, `target`, `est_price`, `rec_id`, `side`) match the `recommendations`/`orders` schemas in `db.py`. `candle_chart` and `zone_kpi_grid_html` argument names match their definitions in `charts.py:122` and `theme.py:218`.
