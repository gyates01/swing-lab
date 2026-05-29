"""Build project snapshot for the analyst sidebar."""
from datetime import datetime, timezone

import pandas as pd

from swing_lab.dashboard.lib import (
    fmt_local_time,
    load_gate_runs,
    load_latest_postmortem,
    load_open_trades,
    load_scan_picks,
    load_scans,
)


def build_snapshot(current_page: str, visible_df: pd.DataFrame | None = None) -> dict:
    """Collect latest gate/scan/open-trades/postmortem into a snapshot dict."""
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Gate
    gate_data = None
    gate_df = load_gate_runs(limit=1)
    if not gate_df.empty:
        row = gate_df.iloc[0]
        gate_data = {
            "score": float(row.get("composite_score", 0)),
            "label": str(row.get("label", "")),
            "sizing": float(row.get("sizing", 0)),
            "run_at": fmt_local_time(row.get("run_at")),
            "components": {
                k: (float(row[k]) if row.get(k) is not None else None)
                for k in ("vix_level", "vix_term_structure", "breadth",
                          "credit_spread", "put_call", "factor_crowding")
            },
        }

    # Scan top-10
    scan_data = None
    scans_df = load_scans(limit=1)
    if not scans_df.empty:
        scan_row = scans_df.iloc[0]
        scan_id = int(scan_row["scan_id"])
        picks_df = load_scan_picks(scan_id)
        top_10 = [
            {
                "rank": rank,
                "symbol": pick.get("symbol"),
                "sector": pick.get("sector"),
                "momentum": (float(pick["momentum"]) if pick.get("momentum") is not None else None),
            }
            for rank, (_, pick) in enumerate(picks_df.head(10).iterrows(), start=1)
        ]
        scan_data = {
            "scan_id": scan_id,
            "run_at": fmt_local_time(scan_row.get("run_at")),
            "top_10": top_10,
        }

    # Open trades
    trades_df = load_open_trades()
    open_trades_data = {
        "count": len(trades_df),
        "symbols": trades_df["symbol"].tolist() if not trades_df.empty else [],
    }

    # Recent postmortem
    postmortem_data = None
    pm = load_latest_postmortem()
    if pm:
        summary = pm.get("summary_text", "")
        postmortem_data = {
            "created_at": fmt_local_time(pm.get("run_at")),
            "summary_first_500_chars": summary[:500],
        }

    # Page context — serialize top-20 rows of whatever the page is showing
    visible_data = None
    if visible_df is not None and not visible_df.empty:
        try:
            visible_data = visible_df.head(20).to_json(orient="records")
        except Exception:
            pass

    return {
        "as_of": as_of,
        "gate": gate_data,
        "scan": scan_data,
        "open_trades": open_trades_data,
        "recent_postmortem": postmortem_data,
        "page_context": {
            "current_page": current_page,
            "visible_data": visible_data,
        },
    }
