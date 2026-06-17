"""Postmortem data sources must include only strategy trades (rec-linked or paper)."""


def _seed_three_closed(db_conn):
    """One rec-linked live, one paper, one bare live — all closed. Returns nothing."""
    from swing_lab.tradelog import open_trade, close_trade
    t1 = open_trade(db_conn, "SNDK", 1.0, 100.0, rec_id=4)   # strategy: rec-linked
    close_trade(db_conn, t1, 110.0)
    t2 = open_trade(db_conn, "AAPL", 1.0, 100.0, mode="paper")  # strategy: paper
    close_trade(db_conn, t2, 110.0)
    t3 = open_trade(db_conn, "VOO", 1.0, 100.0)             # non-strategy: bare live
    close_trade(db_conn, t3, 110.0)


def test_load_trades_with_context_excludes_non_strategy(db_conn):
    from swing_lab.db import load_trades_with_context
    _seed_three_closed(db_conn)
    symbols = {r["symbol"] for r in load_trades_with_context(db_conn)}
    assert symbols == {"SNDK", "AAPL"}


def test_load_trade_outcomes_excludes_non_strategy(db_conn, tmp_path, monkeypatch):
    # load_trade_outcomes reads via lib.py's own DB_PATH (imported from config),
    # which the db_conn fixture does not patch — point it at the same tmp file.
    monkeypatch.setattr("swing_lab.dashboard.lib.DB_PATH", tmp_path / "swing.db")
    from swing_lab.dashboard.lib import load_trade_outcomes
    _seed_three_closed(db_conn)
    symbols = set(load_trade_outcomes()["symbol"].tolist())
    assert symbols == {"SNDK", "AAPL"}
