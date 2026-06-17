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


def _cmd_scan(strategy=None):
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
    print("Scoring S&P 500 universe (batched download — under a minute)...")

    universe = fetch_sp500()
    scored = score_universe(universe)
    picks = top_n_picks(scored, gate["sizing"])

    # Apply strategy filter if requested
    if strategy:
        from swing_lab.strategy_filter import filter_candidates, format_filter_result
        print(f"\nApplying strategy filter: {strategy}...")
        symbols = picks["symbol"].tolist()
        checks = filter_candidates(symbols, strategy=strategy)
        print()
        print(format_filter_result(checks, top_n=10))
        # Keep only passing candidates
        passing = [s for s, c in checks.items() if c.passed]
        picks = picks[picks["symbol"].isin(passing)].reset_index(drop=True)
        print(f"\nPassing candidates: {len(passing)}/{len(symbols)}")

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


def _cmd_review(strategy=None):
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
    print("Scoring S&P 500 universe (batched download — under a minute)...")

    # Fresh scan for each review run ensures the Claude analysis uses current market rankings
    universe = fetch_sp500()
    scored = score_universe(universe)
    picks = top_n_picks(scored, gate["sizing"])

    # Apply strategy filter if requested
    if strategy:
        from swing_lab.strategy_filter import filter_candidates, format_filter_result
        print(f"\nApplying strategy filter: {strategy}...")
        symbols = picks["symbol"].tolist()
        checks = filter_candidates(symbols, strategy=strategy)
        print()
        print(format_filter_result(checks, top_n=10))
        passing = [s for s, c in checks.items() if c.passed]
        picks = picks[picks["symbol"].isin(passing)].reset_index(drop=True)
        print(f"\nPassing candidates: {len(passing)}/{len(symbols)}")

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


def _cmd_recommend(strategy=None):
    from swing_lab.dashboard.actions import refresh_recommend
    from tabulate import tabulate
    import json

    print("Running gate + scan + Claude review + recommendation engine…")
    strategy_msg = f" [{strategy} strategy filter]" if strategy else ""
    print(f"(This may take several minutes — fetching data and calling Claude.{strategy_msg})\n")

    def scan_prog(cur, total, sym):
        print(f"  Scanning {cur}/{total}: {sym}", end="\r", flush=True)

    def review_prog(cur, total, sym):
        print(f"  Reviewing {cur}/{total}: {sym}          ", end="\r", flush=True)

    try:
        batch_id, recs = refresh_recommend(
            scan_progress=scan_prog,
            review_progress=review_prog,
            strategy=strategy,
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
        print(f"    Blended score:  {rec['blended_score']:.2f}/100")
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
    from swing_lab.db import init_db, load_positions
    from swing_lab.config import BROKER
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

    # Get real held positions from the latest Robinhood sync snapshot
    conn = init_db()
    try:
        held = load_positions(conn, BROKER)
    finally:
        conn.close()
    open_positions = {p["symbol"] for p in held}
    if not held:
        print("\n(No synced positions found — run `swing-lab sync` first. "
              "Treating account as flat.)")

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


def _cmd_broker_login():
    """One-time interactive setup: store Robinhood credentials and validate login."""
    import getpass
    from swing_lab.config import store_broker_credentials
    from swing_lab.broker import RobinhoodClient

    print("Robinhood login setup — credentials are stored in Windows Credential Manager.")
    username = input("Robinhood email/username: ").strip()
    password = getpass.getpass("Robinhood password: ")
    totp_seed = getpass.getpass(
        "TOTP seed (base32 secret from authenticator-app 2FA, no spaces) — "
        "leave blank if you approve logins in the Robinhood mobile app: "
    ).strip()

    store_broker_credentials(username, password, totp_seed)
    print("Credentials stored. Validating login...")
    if not totp_seed:
        print("No TOTP seed entered — using mobile-app approval. "
              "Watch your phone for an approval prompt now.")
    try:
        RobinhoodClient().authenticate()
    except Exception as exc:
        print(f"Login FAILED: {exc}")
        print("Credentials were saved but could not be validated. "
              "Re-run `swing-lab broker-login` to correct them.")
        return
    print("Login successful — session token cached. You can now run `swing-lab sync`.")


def _cmd_sync(lookback_days=None):
    """Pull positions + filled orders from Robinhood into swing.db."""
    from swing_lab.config import SYNC_LOOKBACK_DAYS, REC_MATCH_WINDOW_DAYS
    from swing_lab.db import init_db
    from swing_lab.broker import RobinhoodClient
    from swing_lab.sync import sync_account

    lookback = lookback_days if lookback_days is not None else SYNC_LOOKBACK_DAYS

    client = RobinhoodClient()
    try:
        client.authenticate()
    except RuntimeError as exc:
        print(str(exc))
        return

    conn = init_db()
    try:
        summary = sync_account(conn, client, lookback, REC_MATCH_WINDOW_DAYS)
    finally:
        conn.close()

    print(f"\nSYNC COMPLETE (lookback {lookback}d)")
    print(f"  Trades imported (new):   {summary['inserted']}")
    print(f"  Trades closed (updated): {summary['updated']}")
    print(f"  Already up to date:      {summary['skipped']}")
    print(f"  Positions snapshot:      {summary['positions']} symbol(s)")
    if summary["warnings"]:
        print("\n  RECONCILIATION WARNINGS (snapshot is authoritative):")
        for w in summary["warnings"]:
            print(f"    - {w}")


def _cmd_propose():
    import json
    from swing_lab.db import init_db
    from swing_lab.execution.proposals import generate_proposals
    from tabulate import tabulate

    conn = init_db()
    try:
        result = generate_proposals(conn)
    finally:
        conn.close()

    for w in result["warnings"]:
        print(f"  ! {w}")

    created = result["created"]
    if not created:
        print("\nNo new proposals. (Nothing changed since the last run, or no recs/scan saved.)")
        return

    rows = []
    for o in created:
        flags = "; ".join(json.loads(o["guardrail_json"])) or "ok"
        rows.append([o["order_id"], o["side"], o["symbol"],
                     f"{o['shares']:.4f}", f"${o['est_notional']:.2f}", o["reason"], flags])
    print(f"\n{len(created)} proposal(s) queued as pending:\n")
    print(tabulate(rows, headers=["id", "side", "symbol", "shares", "notional", "reason", "guardrails"]))
    print("\nApprove/reject and execute from the dashboard (page 7 — Execution).")


def _cmd_dashboard(port: int = 8501) -> None:
    import subprocess
    import sys
    from pathlib import Path
    app_path = Path(__file__).parent / "dashboard" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)])


def _cmd_premarket_gap(min_gap, min_price, min_volume, top_n, json_out):
    """Run pre-market gap scanner."""
    from swing_lab.premarket import scan_premarket, format_scan_result, save_scan_result

    print("Scanning for pre-market gappers...")
    result = scan_premarket(
        min_gap_pct=min_gap,
        min_price=min_price,
        min_volume=min_volume,
        top_n=top_n,
    )

    if json_out:
        from swing_lab.premarket import format_scan_json
        print(format_scan_json(result))
    else:
        print()
        print(format_scan_result(result))

    # Save to results/ regardless
    path = save_scan_result(result)
    print(f"\nSaved to: {path}")


def _cmd_filter(symbols, strategy, detail):
    """Run strategy filter on specific symbols."""
    from swing_lab.strategy_filter import (
        filter_candidates, format_filter_result, format_detail,
    )

    print(f"Checking {len(symbols)} symbols against strategy: {strategy}...")
    checks = filter_candidates(symbols, strategy=strategy)

    if detail:
        for sym in symbols:
            if sym in checks:
                print()
                print(format_detail(checks[sym]))
    else:
        print()
        print(format_filter_result(checks))


def _cmd_backtest(start: str, end: str, with_gate: bool = False,
                  rank_by: str = "sector", top_n: int = 20,
                  universe: str = None) -> None:
    from swing_lab.backtest import walk_forward, report, plot_equity_curve
    config = f"rank={rank_by}, top={top_n}" + (", macro gate" if with_gate else "")
    if universe:
        config += f", custom universe ({len(universe.split(','))} tickers)"
    print(f"Running walk-forward backtest {start} → {end}  [{config}]")
    print("Survivorship-bias-free: uses point-in-time S&P 500 membership.")
    print("Prices download as one batched panel — expect a few minutes total.")
    returns_df = walk_forward(start=start, end=end, with_gate=with_gate,
                              rank_by=rank_by, top_n=top_n)
    stats = report(returns_df)
    tag = ""
    if rank_by != "sector" or top_n != 20:
        tag = f"{rank_by}_top{top_n}"
    out_path = plot_equity_curve(returns_df, tag=tag)
    print(f"\n{'='*50}")
    print("BACKTEST RESULTS")
    print(f"{'='*50}")
    print(f"  Periods:          {stats['n_periods']}")
    print(f"  Total return:     {stats['total_return']*100:.1f}%")
    print(f"  Annualized:       {stats['annualized_return']*100:.1f}%")
    print(f"  Sharpe ratio:     {stats['sharpe']:.2f}")
    print(f"  Max drawdown:     {stats['max_drawdown']*100:.1f}%")
    print(f"  Hit rate:         {stats['hit_rate']*100:.1f}%")
    if "spy_total_return" in stats:
        print(f"\n  vs SPY benchmark:")
        print(f"  SPY total:        {stats['spy_total_return']*100:.1f}%")
        print(f"  SPY annualized:   {stats['spy_annualized_return']*100:.1f}%")
        print(f"  SPY Sharpe:       {stats['spy_sharpe']:.2f}")
        print(f"  SPY max drawdown: {stats['spy_max_drawdown']*100:.1f}%")
        print(f"  Excess (ann.):    {stats['excess_annualized']*100:+.1f}%")
        print(f"  Beat-SPY rate:    {stats['beat_spy_rate']*100:.1f}% of periods")
    if "avg_gate_sizing" in stats:
        print(f"\n  Macro gate exposure:")
        print(f"  Avg sizing:       {stats['avg_gate_sizing']*100:.0f}%")
        print(f"  FULL periods:     {stats['pct_full']*100:.1f}%")
        print(f"  PARTIAL periods:  {stats['pct_partial']*100:.1f}%")
        print(f"  Stand-down:       {stats['pct_stand_down']*100:.1f}%")
    print(f"\nEquity curve saved: {out_path}")


def main():
    parser = argparse.ArgumentParser(prog="swing-lab", description="Swing trading research tool")
    sub = parser.add_subparsers(dest="command", required=True)

    # gate subcommand
    gate_p = sub.add_parser("gate", help="Show macro gate score and components")

    # scan subcommand
    scan_p = sub.add_parser("scan", help="Run momentum scanner and output top picks")
    scan_p.add_argument("--strategy", default=None,
                        help="Optional strategy filter (e.g. 'trend-join-long')")

    # backtest subcommand
    bt_p = sub.add_parser("backtest", help="Run walk-forward backtest (2015–2024)")
    bt_p.add_argument("--start", default="2015-01-01", help="Start date YYYY-MM-DD")
    bt_p.add_argument("--end", default="2024-12-31", help="End date YYYY-MM-DD")
    bt_p.add_argument("--with-gate", action="store_true", dest="with_gate",
                      help="Apply the macro gate historically (sizing 1.0/0.6/0.0)")
    bt_p.add_argument("--rank", choices=["sector", "raw"], default="sector", dest="rank_by",
                      help="Momentum ranking: within-sector percentile (default) or raw universe-wide")
    bt_p.add_argument("--top", type=int, default=20, dest="top_n",
                      help="Number of picks held per period (default 20)")
    bt_p.add_argument("--universe", default=None,
                      help="Custom universe as comma-separated tickers (e.g. AAPL,MSFT,TSLA)")

    # review subcommand
    review_p = sub.add_parser("review", help="Run Claude analyst review on top candidates")
    review_p.add_argument("--strategy", default=None,
                          help="Optional strategy filter (e.g. 'trend-join-long')")

    # log subcommand group
    log_p = sub.add_parser("log", help="Trade log operations")
    log_sub = log_p.add_subparsers(dest="log_command", required=True)

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
    rec_p.add_argument("--strategy", default=None,
                       help="Optional strategy filter (e.g. 'trend-join-long')")

    # premarket-gap
    pm_p = sub.add_parser("premarket-gap", help="Scan for pre-market gap candidates")
    pm_p.add_argument("--min-gap", type=float, default=5.0,
                      help="Minimum gap percentage (default: 5.0)")
    pm_p.add_argument("--min-price", type=float, default=3.0,
                      help="Minimum price (default: 3.0)")
    pm_p.add_argument("--min-volume", type=int, default=50000,
                      help="Minimum pre-market volume (default: 50000)")
    pm_p.add_argument("--top", type=int, default=10, dest="top_n",
                      help="Number of top gappers to show (default: 10)")
    pm_p.add_argument("--json", action="store_true", dest="json_out",
                      help="Output as JSON")

    # filter subcommand
    filter_p = sub.add_parser("filter", help="Run strategy filter on a set of symbols")
    filter_p.add_argument("symbols", nargs="+",
                          help="Ticker symbols to check (e.g. AAPL MSFT TSLA)")
    filter_p.add_argument("--strategy", default="trend-join-long",
                          help="Strategy name (default: trend-join-long). "
                               "Available: trend-join-long")
    filter_p.add_argument("--detail", action="store_true",
                          help="Show full per-criterion detail for each symbol")

    # broker-login subcommand
    broker_login_p = sub.add_parser(
        "broker-login", help="Store Robinhood credentials and validate login (one-time)")

    # sync subcommand
    sync_p = sub.add_parser(
        "sync", help="Import Robinhood positions + filled orders into swing.db")
    sync_p.add_argument("--lookback-days", type=int, default=None, dest="lookback_days",
                        help="How far back to pull filled orders (default: config)")

    # propose subcommand
    propose_p = sub.add_parser(
        "propose", help="Generate paper-trade proposals into the order queue")

    args = parser.parse_args()

    if args.command == "gate":
        _cmd_gate()
    elif args.command == "scan":
        _cmd_scan(args.strategy if hasattr(args, 'strategy') else None)
    elif args.command == "backtest":
        _cmd_backtest(args.start, args.end, with_gate=args.with_gate,
                      rank_by=args.rank_by, top_n=args.top_n,
                      universe=args.universe)
    elif args.command == "review":
        _cmd_review(args.strategy if hasattr(args, 'strategy') else None)
    elif args.command == "log":
        if args.log_command == "list":
            _cmd_log_list(args.limit)
    elif args.command == "postmortem":
        _cmd_postmortem(args.last, args.write_obsidian)
    elif args.command == "dashboard":
        _cmd_dashboard(args.port)
    elif args.command == "rebalance":
        _cmd_rebalance()
    elif args.command == "recommend":
        _cmd_recommend(args.strategy if hasattr(args, 'strategy') else None)
    elif args.command == "premarket-gap":
        _cmd_premarket_gap(args.min_gap, args.min_price, args.min_volume,
                           args.top_n, args.json_out)
    elif args.command == "filter":
        _cmd_filter(args.symbols, args.strategy, args.detail)
    elif args.command == "broker-login":
        _cmd_broker_login()
    elif args.command == "sync":
        _cmd_sync(args.lookback_days)
    elif args.command == "propose":
        _cmd_propose()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()