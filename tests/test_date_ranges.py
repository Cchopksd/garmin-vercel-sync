from datetime import date

import pytest

from garmin_vercel_sync.date_ranges import period_window


def test_30_day_window_includes_today():
    start, end = period_window("30d", "Asia/Bangkok", today=date(2026, 9, 12))
    assert (start, end) == (date(2026, 8, 14), date(2026, 9, 12))


def test_ytd_starts_on_january_first():
    assert period_window("ytd", "Asia/Bangkok", today=date(2026, 9, 12)) == (
        date(2026, 1, 1),
        date(2026, 9, 12),
    )


def test_unknown_period_is_rejected():
    with pytest.raises(ValueError, match="Unsupported period"):
        period_window("7d", "Asia/Bangkok", today=date(2026, 9, 12))
