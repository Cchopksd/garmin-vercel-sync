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


def requested_window(
    *,
    tz_name: str,
    period: str | None = None,
    selected_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[str | None, date, date]:
    """Resolve exactly one period, day, or inclusive custom date range."""
    has_period = period is not None
    has_day = selected_date is not None
    has_range = start_date is not None or end_date is not None
    if sum((has_period, has_day, has_range)) != 1:
        raise ValueError("Provide exactly one of period, date, or start_date and end_date")

    if has_period:
        if not isinstance(period, str):
            raise ValueError("period must be a supported period")
        start, end = period_window(period, tz_name)
        return period, start, end

    if has_day:
        if not isinstance(selected_date, str):
            raise ValueError("date must be YYYY-MM-DD")
        day = date.fromisoformat(selected_date)
        return None, day, day

    if not isinstance(start_date, str) or not isinstance(end_date, str):
        raise ValueError("start_date and end_date must both be YYYY-MM-DD")
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    return None, start, end
