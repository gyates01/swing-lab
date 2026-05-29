"""Swing Lab CLI entry point."""
import argparse
import sys


def _cmd_gate():
    from swing_lab.macro_gate import compute_gate
    from swing_lab.db import init_db, save_gate_run
    gate = compute_gate()
    conn = init_db()
    try:
        save_gate_run(conn, gate)
    finally:
        conn.close()
    print(f"\nMACRO GATE — {gate['label']}")
    print(f"  Composite score: {gate['score']:.1f}/100")
    print(f"  Deployment sizing: {gate['sizing']*100:.0f}%")
    print(f"\nComponents:")
    for k, v in gate['components'].items():
        print(f"  {k:20s}: {v:.1f}")


def _cmd_scan():
    from swing_lab.universe import fetch_sp500
    from swing_lab.scanner import score_universe, top_n_picks
    from swing_lab.macro_gate import compute_gate
    from swing_lab.db import init_db, save_scan
    from tabulate import tabulate

    print("Fetching macro gate...")
    gate = compute_gate()

    if gate["sizing"] == 0.0:
        print("STAND DOWN — macro gate closed. No scan.")
        return

    print(f"MACRO GATE — {gate['label']} | score={gate['score']:.1f} | sizing={gate['sizing']*100:.0f}%")
    print("Scoring S&P 500 universe (this takes ~2–3 minutes)...")

    universe = fetch_sp500()
    scored = score_universe(universe)
    picks = top_n_picks(scored, gate["sizing"])

    conn = init_db()
    try:
        scan_id = save_scan(conn, gate["score"], gate["sizing"], picks)
    finally:
        conn.close()

    display_cols = ["symbol", "sector", "momentum", "score", "gate_sizing"]
    print(tabulate(
        picks[display_cols].head(20),
        headers="keys",
        floatfmt=".2f",
        tablefmt="simple",
    ))
    print(f"\nScan #{scan_id} saved to swing.db")


def _cmd_review():
    from swing_lab.universe import fetch_sp500
    from swing_lab.scanner import score_universe, top_n_picks
    from swing_lab.macro_gate import compute_gate
    from swing_lab.db import init_db, save_scan, save_reviews
    from swing_lab.review import review_candidates
    from tabulate import tabulate

    print("Fetching macro gate...")
    gate = compute_gate()

    if gate["sizing"] == 0.0:
        print("STAND DOWN — macro gate closed. No review.")
        return

    print(f"MACRO GATE — {gate['label']} | score={gate['score']:.1f} | sizing={gate['sizing']*100:.0f}%")
    print("Scoring S&P 500 universe (this takes ~2–3 minutes)...")

    # Fresh scan for each review run ensures the Claude analysis uses current market rankings
    universe = fetch_sp500()
    scored = score_universe(universe)
    picks = top_n_picks(scored, gate["sizing"])

    conn = init_db()
    try:
        scan_id = save_scan(conn, gate["score"], gate["sizing"], picks)

        print(f"\nRunning Claude analyst review on top candidates...")
        reviews_df = review_candidates(picks)

        if reviews_df.empty:
            print("No review results returned.")
            return

        save_reviews(conn, scan_id, reviews_df)
    finally:
        conn.close()

    display_cols = ["symbol", "sector", "quant_score", "claude_score", "blended_score", "claude_summary"]
    print(f"\n{'='*70}")
    print("CLAUDE ANALYST REVIEW RESULTS")
    print(f"{'='*70}")
    print(tabulate(
        reviews_df[display_cols],
        headers="keys",
        floatfmt=".2f",
        tablefmt="simple",
        showindex=False,
    ))
    print(f"\nReview for scan #{scan_id} saved to swing.db")


def _cmd_log_open(symbol, shares, price, thesis, scan_id):
    from swing_lab.db import init_db
    from swing_lab.tradelog import open_trade
    conn = init_db()
    try:
        trade_id = open_trade(conn, symbol.upper(), shares, price, scan_id, thesis)
    finally:
        conn.close()
    print(f"Trade #{trade_id} opened: {symbol.upper()} {shares} shares @ ${price:.2f}")


def _cmd_log_close(trade_id, exit_price, reason, thesis_validated=None,
                   exit_driver=None, macro_aligned=None, notes=None):
    import json
    from swing_lab.db import init_db
    from swing_lab.tradelog import close_trade
    outcome = None
    if thesis_validated:
        outcome = {
            "thesis_validated": thesis_validated,
            "exit_driver": exit_driver or "discretionary",
            "red_flags_materialized_json": json.dumps([]),
            "exit_triggers_fired_json": json.dumps([]),
            "macro_aligned": macro_aligned or "na",
            "notes": notes,
        }
    conn = init_db()
    try:
        trade = close_trade(conn, trade_id, exit_price, reason, outcome=outcome)
    finally:
        conn.close()
    if trade is None:
        print(f"Trade #{trade_id} not found or already closed.")
        return
    pnl_sign = "+" if trade["pnl"] >= 0 else ""
    print(f"Trade #{trade_id} closed: {pnl_sign}${trade['pnl']:.2f} ({pnl_sign}{trade['pnl_pct']*100:.1f}%)")
    if outcome:
        print(f"  Outcome recorded: thesis={thesis_validated}, driver={exit_driver}")


def _cmd_log_list(limit):
    from swing_lab.db import init_db
    from swing_lab.tradelog import recent_trades
    from tabulate import tabulate
    conn = init_db()
    try:
        trades = recent_trades(conn, n=limit)
    finally:
        conn.close()
    if not trades:
        print("No trades logged yet.")
        return
    headers = ["id", "symbol", "shares", "entry", "exit", "pnl", "pnl%", "opened", "thesis"]
    rows = []
    for t in trades:
        rows.append([
            t["trade_id"],
            t["symbol"],
            t["shares"],
            f"${t['entry_price']:.2f}",
            f"${t['exit_price']:.2f}" if t["exit_price"] else "OPEN",
            f"${t['pnl']:.2f}" if t["pnl"] is not None else "—",
            f"{t['pnl_pct']*100:.1f}%" if t["pnl_pct"] is not None else "—",
            t["opened_at"][:10] if t["opened_at"] else "",
            (t["thesis_text"] or "")[:40],
        ])
    print(tabulate(rows, headers=headers, tablefmt="simple"))


def _cmd_postmortem(last, write_obsidian):
    from swing_lab.db import init_db, load_trades_with_context, save_postmortem
    from swing_lab.postmortem import analyze_trades_with_context
    from swing_lab.config import OBSIDIAN_SWING_LAB_DIR
    conn = init_db()
    try:
        trade_rows = load_trades_with_context(conn, limit=last)
    finally:
        conn.close()
    if not trade_rows:
        print("No closed trades to analyze.")
        return
    print(f"Sending {len(trade_rows)} trades to Claude for analysis...")
    result = analyze_trades_with_context(trade_rows)
    conn = init_db()
    try:
        save_postmortem(conn, result["trade_count"], result["outcome_count"],
                        result["summary_text"], result["model"], result["cache_hit"])
    finally:
        conn.close()
    print("\n" + "=" * 70)
    print("TRADE POSTMORTEM ANALYSIS")
    print("=" * 70)
    print(result["summary_text"])
    if write_obsidian:
        from datetime import datetime
        OBSIDIAN_SWING_LAB_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.today().strftime("%Y-%m-%d")
        out_path = OBSIDIAN_SWING_LAB_DIR / f"Trade Log Review {today}.md"
        out_path.write_text(f"# Trade Log Review {today}\n\n{result['summary_text']}\n", encoding="utf-8")
        print(f"\nSaved to: {out_path}")


def _cmd_recommend():
    from swing_lab.dashboard.actions import refresh_recommend
    from tabulate import tabulate
    import json

    print("Running gate + scan + Claude review + recommendation engine…")
    print("(This may take several minutes — fetching data and calling Claude.)\n")

    def scan_prog(cur, total, sym):
        print(f"  Scanning {cur}/{total}: {sym}", end="\r", flush=True)

    def review_prog(cur, total, sym):
        print(f"  Reviewing {cur}/{total}: {sym}          ", end="\r", flush=True)

    try:
        batch_id, recs = refresh_recommend(
            scan_progress=scan_prog,
            review_progress=review_prog,
        )
    except RuntimeError as exc:
        print(f"\n{exc}")
        return

    print(f"\n\n{'='*60}")
    print(f"TOP {len(recs)} TRADE RECOMMENDATIONS  (batch {batch_id})")
    print(f"{'='*60}\n")

    for rec in recs:
        risks = []
        try:
            risks = json.loads(rec.get("risks_json") or "[]")
        except Exception:
            pass
        label = "★ #1 PICK (synthesized)" if rec["is_synthesized"] else f"#{rec['rank']}"
        print(f"  {label} — {rec['symbol']}")
        print(f"    Blended score:  {rec['blended_score']:.2f}/10")
        print(f"    Deploy:         {rec['sizing_pct']*100:.0f}% of portfolio")
        if rec.get("entry_zone"):
            print(f"    Entry zone:     {rec['entry_zone']}")
        print(f"    Rationale:      {rec['rationale']}")
        if risks:
            print("    Key risks:")
            for r in risks:
                print(f"      • {r}")
        print()

    print(f"Saved to swing.db — batch_id={batch_id}")


def _cmd_rebalance():
    from swing_lab.universe import fetch_sp500
    from swing_lab.scanner import score_universe, top_n_picks
    from swing_lab.macro_gate import compute_gate
    from swing_lab.db import init_db
    from swing_lab.tradelog import open_trades
    from tabulate import tabulate

    print("Fetching macro gate...")
    gate = compute_gate()
    if gate["sizing"] == 0.0:
        print("STAND DOWN — macro gate closed. Close all positions.")
        return

    print(f"MACRO GATE — {gate['label']} | score={gate['score']:.1f} | sizing={gate['sizing']*100:.0f}%")
    print("Running scanner...")
    universe = fetch_sp500()
    scored = score_universe(universe)
    picks = top_n_picks(scored, gate["sizing"])

    # Get open trades from DB
    conn = init_db()
    try:
        current_open = open_trades(conn)
    finally:
        conn.close()
    open_positions = {t["symbol"] for t in current_open}

    # New targets = top picks symbols
    new_targets = set(picks["symbol"].tolist())

    to_open = new_targets - open_positions
    to_close = open_positions - new_targets

    print(f"\n{'='*50}")
    print("REBALANCE RECOMMENDATION (does NOT execute orders)")
    print(f"{'='*50}")
    print(f"\n  Open positions:   {sorted(open_positions) or 'none'}")
    print(f"  New targets:      {sorted(new_targets)}")
    print(f"\n  CLOSE:  {sorted(to_close) or 'none'}")
    print(f"  OPEN:   {sorted(to_open) or 'none'}")
    print(f"\n  (Gate sizing: {gate['sizing']*100:.0f}% — scale position sizes accordingly)")


def _cmd_dashboard(port: int = 8501) -> None:
    import subprocess
    import sys
    from pathlib import Path
    app_path = Path(__file__).parent / "dashboard" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)])


def _cmd_backtest(start: str, end: str) -> None:
    from swing_lab.backtest import walk_forward, report, plot_equity_curve
    print(f"Running walk-forward backtest {start} → {end}")
    print("WARNING: This fetches price history for ~500 symbols. Expect 10–30 minutes.")
    returns_df = walk_forward(start=start, end=end)
    stats = report(returns_df)
    out_path = plot_equity_curve(returns_df)
    print(f"\n{'='*50}")
    print("BACKTEST RESULTS")
    print(f"{'='*50}")
    print(f"  Periods:          {stats['n_periods']}")
    print(f"  Total return:     {stats['total_return']*100:.1f}%")
    print(f"  Annualized:       {stats['annualized_return']*100:.1f}%")
    print(f"  Sharpe ratio:     {stats['sharpe']:.2f}")
    print(f"  Max drawdown:     {stats['max_drawdown']*100:.1f}%")
    print(f"  Hit rate:         {stats['hit_rate']*100:.1f}%")
    print(f"\nEquity curve saved: {out_path}")


def main():
    parser = argparse.ArgumentParser(prog="swing-lab", description="Swing trading research tool")
    sub = parser.add_subparsers(dest="command", required=True)

    # gate subcommand
    gate_p = sub.add_parser("gate", help="Show macro gate score and components")

    # scan subcommand
    scan_p = sub.add_parser("scan", help="Run momentum scanner and output top picks")

    # backtest subcommand
    bt_p = sub.add_parser("backtest", help="Run walk-forward backtest (2015–2024)")
    bt_p.add_argument("--start", default="2015-01-01", help="Start date YYYY-MM-DD")
    bt_p.add_argument("--end", default="2024-12-31", help="End date YYYY-MM-DD")

    # review subcommand
    review_p = sub.add_parser("review", help="Run Claude analyst review on top candidates")

    # log subcommand group
    log_p = sub.add_parser("log", help="Trade log operations")
    log_sub = log_p.add_subparsers(dest="log_command", required=True)

    # log open
    log_open_p = log_sub.add_parser("open", help="Open a new trade")
    log_open_p.add_argument("symbol", help="Ticker symbol")
    log_open_p.add_argument("shares", type=float, help="Number of shares")
    log_open_p.add_argument("price", type=float, help="Entry price")
    log_open_p.add_argument("--thesis", default="", help="Investment thesis")
    log_open_p.add_argument("--scan-id", type=int, default=None, dest="scan_id")

    # log close
    log_close_p = log_sub.add_parser("close", help="Close a trade")
    log_close_p.add_argument("trade_id", type=int)
    log_close_p.add_argument("exit_price", type=float)
    log_close_p.add_argument("--reason", default="")
    log_close_p.add_argument("--thesis-validated", dest="thesis_validated",
                             choices=["yes", "partial", "no", "unclear"], default=None)
    log_close_p.add_argument("--exit-driver", dest="exit_driver",
                             choices=["target_hit", "stop_loss", "thesis_broken", "macro_shift",
                                      "sector_rotation", "time_stop", "discretionary"],
                             default=None)
    log_close_p.add_argument("--macro-aligned", dest="macro_aligned",
                             choices=["yes", "no", "na"], default=None)
    log_close_p.add_argument("--notes", dest="notes", default=None)

    # log list
    log_list_p = log_sub.add_parser("list", help="List recent trades")
    log_list_p.add_argument("--limit", type=int, default=20)

    # postmortem
    pm_p = sub.add_parser("postmortem", help="Claude analysis of recent trades")
    pm_p.add_argument("--last", type=int, default=20, help="Number of recent trades to analyze")
    pm_p.add_argument("--write-obsidian", action="store_true", dest="write_obsidian")

    # dashboard
    dash_p = sub.add_parser("dashboard", help="Launch educational web dashboard (localhost:8501)")
    dash_p.add_argument("--port", type=int, default=8501, help="Port to run dashboard on")

    # rebalance
    reb_p = sub.add_parser("rebalance", help="Suggest rebalance actions vs current open trades")

    # recommend
    rec_p = sub.add_parser("recommend", help="Run recommendation engine — top 3 trade picks")

    args = parser.parse_args()

    if args.command == "gate":
        _cmd_gate()
    elif args.command == "scan":
        _cmd_scan()
    elif args.command == "backtest":
        _cmd_backtest(args.start, args.end)
    elif args.command == "review":
        _cmd_review()
    elif args.command == "log":
        if args.log_command == "open":
            _cmd_log_open(args.symbol, args.shares, args.price, args.thesis, args.scan_id)
        elif args.log_command == "close":
            _cmd_log_close(
                args.trade_id, args.exit_price, args.reason,
                thesis_validated=args.thesis_validated,
                exit_driver=args.exit_driver,
                macro_aligned=args.macro_aligned,
                notes=args.notes,
            )
        elif args.log_command == "list":
            _cmd_log_list(args.limit)
    elif args.command == "postmortem":
        _cmd_postmortem(args.last, args.write_obsidian)
    elif args.command == "dashboard":
        _cmd_dashboard(args.port)
    elif args.command == "rebalance":
        _cmd_rebalance()
    elif args.command == "recommend":
        _cmd_recommend()
