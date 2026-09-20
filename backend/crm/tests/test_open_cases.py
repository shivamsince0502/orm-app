"""Open-case eligibility (D8) — pure predicate, no DB, injected today."""

from datetime import date
from types import SimpleNamespace

import pytest

from crm.services.ranking import is_open_case

TODAY = date(2026, 9, 15)


@pytest.mark.parametrize(
    "kept_open,occurred_dates,created_at,expected",
    [
        # interaction this month -> in
        (False, [date(2026, 9, 1), date(2026, 9, 14)], date(2026, 1, 5), True),
        # previous-month-only interactions -> out
        (False, [date(2026, 8, 31)], date(2026, 1, 5), False),
        # created this month -> in
        (False, [], date(2026, 9, 2), True),
        # kept_open carryover from earlier months -> in
        (True, [date(2026, 5, 1)], date(2025, 11, 3), True),
        # kept_open wins even with zero interactions
        (True, [], date(2025, 1, 1), True),
        # exact month-boundary day (the 1st) counts
        (False, [date(2026, 9, 1)], date(2026, 1, 5), True),
        # end-of-previous-month only -> out
        (False, [date(2026, 8, 30)], date(2026, 1, 5), False),
        # old interactions + old created_at -> out
        (False, [date(2026, 6, 1), date(2026, 7, 9)], date(2026, 5, 12), False),
    ],
)
def test_open_case_rule(kept_open, occurred_dates, created_at, expected):
    interactions = [SimpleNamespace(occurred_at=d) for d in occurred_dates]
    assert is_open_case(kept_open, interactions, created_at, TODAY) is expected
