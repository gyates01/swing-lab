from swing_lab.reconstruction import reconstruct_episodes


def _fill(symbol, side, shares, price, day, order_id, fees=0.0):
    return {"symbol": symbol, "side": side, "shares": shares, "price": price,
            "fees": fees, "filled_at": f"2026-06-{day:02d}T14:30:00+00:00",
            "order_id": order_id}


def test_simple_round_trip():
    fills = [
        _fill("AAPL", "buy", 10, 150.0, 1, "o1", fees=0.01),
        _fill("AAPL", "sell", 10, 165.0, 5, "o2", fees=0.02),
    ]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 1
    ep = eps[0]
    assert ep["symbol"] == "AAPL"
    assert ep["shares"] == 10
    assert ep["entry_price"] == 150.0
    assert ep["exit_price"] == 165.0
    assert ep["opening_order_id"] == "o1"
    assert ep["broker_order_ids"] == ["o1", "o2"]
    assert round(ep["fees"], 4) == 0.03
    # pnl = 10*165 - 10*150 - fees(0.03) = 149.97
    assert round(ep["pnl"], 2) == 149.97
    assert round(ep["pnl_pct"], 5) == round(149.97 / 1500.0, 5)
    assert ep["opened_at"].startswith("2026-06-01")
    assert ep["closed_at"].startswith("2026-06-05")


def test_scale_in_averages_entry():
    fills = [
        _fill("AAPL", "buy", 10, 100.0, 1, "o1"),
        _fill("AAPL", "buy", 30, 120.0, 2, "o2"),  # weighted avg = 115
        _fill("AAPL", "sell", 40, 130.0, 5, "o3"),
    ]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 1
    assert eps[0]["shares"] == 40
    assert eps[0]["entry_price"] == 115.0
    assert eps[0]["opening_order_id"] == "o1"


def test_partial_then_full_close_is_one_episode():
    fills = [
        _fill("AAPL", "buy", 10, 100.0, 1, "o1"),
        _fill("AAPL", "sell", 4, 110.0, 3, "o2"),   # partial, still net 6
        _fill("AAPL", "sell", 6, 120.0, 5, "o3"),   # flat -> closes
    ]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 1
    ep = eps[0]
    assert ep["shares"] == 10
    # exit avg = (4*110 + 6*120) / 10 = 116
    assert ep["exit_price"] == 116.0
    assert ep["closed_at"] is not None


def test_still_open_position():
    fills = [_fill("AAPL", "buy", 10, 150.0, 1, "o1")]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 1
    ep = eps[0]
    assert ep["exit_price"] is None
    assert ep["closed_at"] is None
    assert ep["pnl"] is None
    assert ep["pnl_pct"] is None
    assert ep["shares"] == 10
    assert ep["entry_price"] == 150.0


def test_back_to_back_episodes_same_symbol():
    fills = [
        _fill("AAPL", "buy", 10, 100.0, 1, "o1"),
        _fill("AAPL", "sell", 10, 110.0, 3, "o2"),   # closes episode 1
        _fill("AAPL", "buy", 5, 120.0, 6, "o3"),     # opens episode 2
        _fill("AAPL", "sell", 5, 130.0, 8, "o4"),    # closes episode 2
    ]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 2
    assert eps[0]["opening_order_id"] == "o1"
    assert eps[1]["opening_order_id"] == "o3"
    assert eps[1]["entry_price"] == 120.0


def test_multiple_symbols_independent():
    fills = [
        _fill("AAPL", "buy", 10, 100.0, 1, "a1"),
        _fill("MSFT", "buy", 5, 200.0, 1, "m1"),
        _fill("AAPL", "sell", 10, 110.0, 3, "a2"),
    ]
    eps = reconstruct_episodes(fills)
    by_symbol = {e["symbol"]: e for e in eps}
    assert by_symbol["AAPL"]["closed_at"] is not None
    assert by_symbol["MSFT"]["closed_at"] is None


def test_fills_sorted_by_time_regardless_of_input_order():
    fills = [
        _fill("AAPL", "sell", 10, 165.0, 5, "o2"),
        _fill("AAPL", "buy", 10, 150.0, 1, "o1"),
    ]
    eps = reconstruct_episodes(fills)
    assert len(eps) == 1
    assert eps[0]["opening_order_id"] == "o1"
    assert eps[0]["entry_price"] == 150.0
