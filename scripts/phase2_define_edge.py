"""
Phase 2: Define Your Edge
--------------------------
Documents the core strategy decisions into the Obsidian strategy note.

Decisions captured:
  - Time horizon / rebalance cadence
  - Universe (S&P 500)
  - Signal (12-1 month sector-relative momentum)
  - Macro gate thresholds
  - Position sizing rules
  - Claude review parameters
  - Data source

No external data fetched — stdlib + pathlib only.
"""

import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from swing_lab.config import (
    MOMENTUM_LONG_MONTHS,
    MOMENTUM_SKIP_MONTHS,
    GATE_FULL,
    GATE_PARTIAL,
    MAX_POSITION_PCT,
    TOP_N_PICKS,
    REVIEW_TOP_N,
    REBALANCE_DAY_OF_WEEK,
    REBALANCE_EVERY_N_WEEKS,
    OBSIDIAN_STRATEGY_NOTE,
)


def write_to_obsidian() -> None:
    note_path = OBSIDIAN_STRATEGY_NOTE
    if not note_path.exists():
        print(f"[warn] Obsidian note not found: {note_path}")
        return

    content = note_path.read_text(encoding="utf-8")

    today = datetime.today().strftime("%Y-%m-%d")

    # Derive human-readable values from config constants
    rebalance_day_name = [
        "Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday"
    ][REBALANCE_DAY_OF_WEEK]

    gate_stand_down = GATE_PARTIAL - 1  # score < 40 → stand down

    filled_block = f"""
### Phase 2 — Define Your Edge (Filled {today})

| Decision | Value | Rationale |
|---|---|---|
| Time horizon | Swing (bi-weekly rebalance) | Every {REBALANCE_EVERY_N_WEEKS} weeks on {rebalance_day_name}; balances turnover vs. signal freshness |
| Universe | S&P 500 (~500 names) | Liquid, well-covered names reduce slippage and data gaps |
| Signal | {MOMENTUM_LONG_MONTHS}-{MOMENTUM_SKIP_MONTHS} month momentum, sector-relative | Skips most-recent month to avoid short-term reversal; sector-relative removes hot-sector bias |
| Macro gate | Full ≥{GATE_FULL}, Partial {GATE_PARTIAL}–{GATE_FULL - 1}, Stand down <{GATE_PARTIAL} | Prevents deploying into high-volatility / low-breadth environments |
| Position sizing | ≤{int(MAX_POSITION_PCT * 100)}% per name, top-{TOP_N_PICKS} scanner output | Limits single-name risk; scanner narrows universe to actionable candidates |
| Claude review | Top {REVIEW_TOP_N} candidates, 60/40 quant/Claude blend | Quant ranks; Claude stress-tests narrative, catalyst, and risk |
| Data source | Yahoo Finance (yfinance, free) | Zero cost; sufficient for daily OHLCV and fundamental snapshots |

**Edge thesis:** Sector-relative momentum captures relative strength without over-weighting
whatever sector is currently hot. Bi-weekly rebalance balances turnover vs. signal freshness.
The macro gate prevents deploying into high-volatility/low-breadth environments.

"""

    insert_marker = "### Phase 2: Define Your Edge"
    if insert_marker in content and "Phase 2 — Define Your Edge (Filled" not in content:
        idx = content.index(insert_marker)
        next_section = content.find("\n### Phase 3:", idx)
        if next_section == -1:
            next_section = content.find("\n---", idx)
        insert_at = next_section if next_section != -1 else idx + len(insert_marker) + 200
        content = content[:insert_at] + "\n" + filled_block + content[insert_at:]
        content = content.replace(
            "- [ ] Define my time horizon and risk tolerance explicitly",
            "- [x] Define my time horizon and risk tolerance explicitly",
        )
        note_path.write_text(content, encoding="utf-8")
        print(f"  Written to: {note_path}")
    elif "Phase 2 — Define Your Edge (Filled" in content:
        print("  [info] Phase 2 already filled in Obsidian note — skipping overwrite")
    else:
        print(f"  [warn] Could not find insert marker '{insert_marker}' in note")


if __name__ == "__main__":
    write_to_obsidian()
