def test_execution_constants_exist():
    from swing_lab import config
    assert config.PAPER_STARTING_CASH == 10000.0
    assert config.CASH_RESERVE_PCT == 0.10
    assert config.MAX_OPEN_POSITIONS == 8
    assert config.MAX_ORDERS_PER_DAY == 12
    assert config.MAX_NOTIONAL_PER_DAY_PCT == 0.30
    assert config.EXECUTION_KILL_SWITCH is False
    assert config.EXECUTION_MODE == "paper"
