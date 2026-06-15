from swing_lab.rec_match import trading_days_between, find_matching_rec
from datetime import date


def test_trading_days_between_skips_weekends():
    # Mon 2026-06-01 -> Fri 2026-06-05 = 4 trading days
    assert trading_days_between(date(2026, 6, 1), date(2026, 6, 5)) == 4
    # Fri -> next Mon = 1 trading day (Sat/Sun skipped)
    assert trading_days_between(date(2026, 6, 5), date(2026, 6, 8)) == 1
    # same day = 0
    assert trading_days_between(date(2026, 6, 1), date(2026, 6, 1)) == 0


def test_matches_most_recent_rec_in_window():
    recs = [
        {"rec_id": 1, "created_at": "2026-06-01T00:00:00+00:00"},
        {"rec_id": 2, "created_at": "2026-06-03T00:00:00+00:00"},
    ]
    # opened Fri 2026-06-05; both within 5 trading days -> pick most recent (rec 2)
    assert find_matching_rec("2026-06-05T14:30:00+00:00", recs, 5) == 2


def test_rec_outside_window_not_matched():
    recs = [{"rec_id": 1, "created_at": "2026-06-01T00:00:00+00:00"}]
    # opened 2026-06-12 (Fri) -> 9 trading days after rec -> no match
    assert find_matching_rec("2026-06-12T14:30:00+00:00", recs, 5) is None


def test_rec_created_after_open_not_matched():
    recs = [{"rec_id": 1, "created_at": "2026-06-10T00:00:00+00:00"}]
    assert find_matching_rec("2026-06-05T14:30:00+00:00", recs, 5) is None


def test_no_candidates_returns_none():
    assert find_matching_rec("2026-06-05T14:30:00+00:00", [], 5) is None


def test_handles_z_suffix_timestamps():
    recs = [{"rec_id": 7, "created_at": "2026-06-04T00:00:00Z"}]
    assert find_matching_rec("2026-06-05T14:30:00Z", recs, 5) == 7
