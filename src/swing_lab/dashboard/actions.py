"""Shared refresh actions used by both dashboard buttons and CLI handlers."""
from swing_lab.macro_gate import compute_gate
from swing_lab.scanner import score_universe, top_n_picks
from swing_lab.universe import fetch_sp500
from swing_lab.db import (
    init_db, save_gate_run, save_scan, save_reviews, save_recommendations,
    load_trades_with_context, save_postmortem,
)
from swing_lab.review import review_candidates
from swing_lab.config import POSTMORTEM_TRADE_LIMIT
import pandas as pd


def refresh_gate(progress=None) -> dict:
    """Run macro gate, persist (upsert today's row), return gate dict."""
    gate = compute_gate()
    conn = init_db()
    try:
        save_gate_run(conn, gate)
    finally:
        conn.close()
    return gate


def refresh_scan(progress=None, strategy: str = None) -> tuple[int, dict, pd.DataFrame]:
    """Run gate + scan, persist, return (scan_id, gate, picks_df).

    picks_df has columns: symbol, sector, momentum, score, gate_sizing.
    Raises RuntimeError if gate is STAND DOWN.
    progress: optional callable(current, total, symbol) forwarded to score_universe.
    strategy: optional strategy filter name (e.g. 'trend-join-long').
    """
    gate = compute_gate()
    if gate["sizing"] == 0.0:
        raise RuntimeError(f"STAND DOWN — gate score {gate['score']:.1f}. Scanner skipped.")

    universe = fetch_sp500()
    scored = score_universe(universe, progress=progress)
    picks = top_n_picks(scored, gate["sizing"])

    # Apply strategy filter if requested
    if strategy:
        from swing_lab.strategy_filter import filter_candidates
        symbols = picks["symbol"].tolist()
        checks = filter_candidates(symbols, strategy=strategy)
        passing = [s for s, c in checks.items() if c.passed]
        picks = picks[picks["symbol"].isin(passing)].reset_index(drop=True)
        print(f"  Strategy filter '{strategy}': {len(passing)}/{len(symbols)} passed")

    conn = init_db()
    try:
        scan_id = save_scan(conn, gate["score"], gate["sizing"], picks)
    finally:
        conn.close()

    return scan_id, gate, picks


def refresh_review(scan_progress=None, review_progress=None,
                   strategy: str = None) -> tuple[int, dict, pd.DataFrame]:
    """Run gate + scan + Claude review, persist, return (scan_id, gate, reviews_df).

    reviews_df includes a review_id column linking back to the reviews table.
    scan_progress: callback(current, total, symbol) for the scanner phase.
    review_progress: callback(current, total, symbol) for the review phase.
    strategy: optional strategy filter name (e.g. 'trend-join-long').
    Raises RuntimeError if gate is STAND DOWN.
    """
    scan_id, gate, picks = refresh_scan(progress=scan_progress, strategy=strategy)
    reviews_df = review_candidates(picks, progress=review_progress)

    conn = init_db()
    try:
        review_ids = save_reviews(conn, scan_id, reviews_df)
    finally:
        conn.close()

    if not reviews_df.empty:
        reviews_df = reviews_df.copy()
        reviews_df["review_id"] = reviews_df["symbol"].map(review_ids)

    return scan_id, gate, reviews_df


def refresh_recommend(
    scan_progress=None,
    review_progress=None,
    rec_progress=None,
    strategy: str = None,
) -> tuple[int, list[dict]]:
    """Run gate + scan + review + recommendation engine, persist, return (batch_id, recs).

    Raises RuntimeError if gate is STAND DOWN.
    strategy: optional strategy filter name (e.g. 'trend-join-long').
    """
    from swing_lab.tradelog import open_trades
    from swing_lab.recommendation import generate_recommendations

    scan_id, gate, reviews_df = refresh_review(
        scan_progress=scan_progress,
        review_progress=review_progress,
        strategy=strategy,
    )

    conn = init_db()
    try:
        # Reuse the gate computed during the scan — recomputing here could
        # disagree with the gate the scan was sized under (and wastes ~30s).
        open_positions = open_trades(conn)

        if rec_progress:
            rec_progress(0, 1, "Synthesizing top pick…")

        recs = generate_recommendations(scan_id, gate, reviews_df, open_positions)

        if rec_progress:
            rec_progress(1, 1, "Done")

        batch_id = save_recommendations(conn, scan_id, recs)
    finally:
        conn.close()

    return batch_id, recs


def refresh_postmortem(progress_cb=None) -> int:
    """Run postmortem analysis on recent closed trades. Returns postmortem_id."""
    from swing_lab.postmortem import analyze_trades_with_context

    conn = init_db()
    try:
        trade_rows = load_trades_with_context(conn, limit=POSTMORTEM_TRADE_LIMIT)
        if progress_cb:
            progress_cb(0.3, f"Loaded {len(trade_rows)} trades — calling Claude…")

        result = analyze_trades_with_context(trade_rows)

        if progress_cb:
            progress_cb(0.9, "Saving postmortem…")

        postmortem_id = save_postmortem(
            conn,
            result["trade_count"],
            result["outcome_count"],
            result["summary_text"],
            result["model"],
            result["cache_hit"],
        )
    finally:
        conn.close()

    return postmortem_id
