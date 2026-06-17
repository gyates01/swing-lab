"""Manual trade-entry subcommands are removed; the CLI rejects them."""
import sys
import pytest


def _run_cli(monkeypatch, tmp_path, argv):
    # Point the DB at a tmp file so that, before removal, a parsed `log open`
    # would write to a throwaway DB instead of the real data/swing.db.
    monkeypatch.setattr("swing_lab.db.DB_PATH", tmp_path / "swing.db")
    monkeypatch.setattr(sys, "argv", ["swing-lab"] + argv)
    from swing_lab.cli import main
    main()


def test_log_open_subcommand_removed(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, tmp_path, ["log", "open", "AAPL", "1", "100"])


def test_log_close_subcommand_removed(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, tmp_path, ["log", "close", "1", "100"])
