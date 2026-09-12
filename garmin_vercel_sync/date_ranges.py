from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


PERIODS = {"daily", "30d", "60d", "90d", "180d", "360d", "ytd"}


def period_window(period: str, tz_name: str, today: date | None = None) -> tuple[date, date]:
    """Return inclusive local-calendar boundaries for a supported data period."""
    if period not in PERIODS:
        raise ValueError(f"Unsupported period: {period}")

    end = today or datetime.now(ZoneInfo(tz_name)).date()
    if period == "ytd":
        return date(end.year, 1, 1), end
    if period == "daily":
        return end, end
    days = int(period.removesuffix("d"))
    return end - timedelta(days=days - 1), end
