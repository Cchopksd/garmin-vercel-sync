from datetime import datetime

from garmin_vercel_sync.sync import date_window


def test_date_window_count():
    values = date_window(3, "Asia/Bangkok")
    assert len(values) == 3
    assert values == sorted(values)
