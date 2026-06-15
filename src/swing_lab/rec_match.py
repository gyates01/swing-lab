"""Pure logic: link a trade episode to the recommendation that predicted it.

Trading days are approximated as weekdays (Mon-Fri); market holidays are not
modeled (acceptable for a 5-day matching window). No DB access here.
"""
from datetime import date, datetime, timedelta


def _parse_date(iso: str) -> date:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()


def trading_days_between(start: date, end: date) -> int:
    """Count weekdays strictly after `start` up to and including `end`. 0 if end <= start."""
    if end <= start:
        return 0
    days = 0
    d = start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def find_matching_rec(opened_at_iso: str, candidate_recs: list[dict],
                      window_trading_days: int) -> int | None:
    """Return rec_id of the most recent rec created within the window before the
    episode opened (and not after it), or None."""
    opened = _parse_date(opened_at_iso)
    best = None
    best_created = None
    for rec in candidate_recs:
        created = _parse_date(rec["created_at"])
        if created > opened:
            continue
        if trading_days_between(created, opened) <= window_trading_days:
            if best_created is None or created > best_created:
                best, best_created = rec, created
    return best["rec_id"] if best else None
