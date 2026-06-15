"""Shared pytest fixtures for Swing Lab tests."""
import pytest


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    """An isolated swing.db seeded by the real init_db() schema."""
    db_file = tmp_path / "swing.db"
    # init_db() binds DB_PATH at import time into the swing_lab.db namespace,
    # so patch it there (patching config.DB_PATH would not take effect).
    monkeypatch.setattr("swing_lab.db.DB_PATH", db_file)
    from swing_lab.db import init_db
    conn = init_db()
    yield conn
    conn.close()
