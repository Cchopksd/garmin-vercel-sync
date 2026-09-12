from datetime import date

import pytest

from garmin_vercel_sync.date_ranges import period_window, requested_window


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


def test_custom_date_range_is_inclusive():
    period, start, end = requested_window(
        tz_name="Asia/Bangkok", start_date="2026-07-03", end_date="2026-07-15"
    )
    assert (period, start, end) == (None, date(2026, 7, 3), date(2026, 7, 15))


def test_single_date_and_period_cannot_be_combined():
    with pytest.raises(ValueError, match="exactly one"):
        requested_window(tz_name="Asia/Bangkok", period="30d", selected_date="2026-07-03")
