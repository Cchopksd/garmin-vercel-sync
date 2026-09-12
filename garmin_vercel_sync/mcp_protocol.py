from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Protocol

from .date_ranges import PERIODS, period_window

MCP_PROTOCOL_VERSION = "2025-06-18"


class RowReader(Protocol):
    def fetch_rows(self, start_date: str, end_date: str) -> list[dict[str, Any]]: ...


class DateColumnRowReader(Protocol):
    def fetch_rows_by_date_column(
        self, column: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]: ...


METRIC_TYPES = (
    "daily_stats",
    "heart_rate",
    "sleep",
    "hrv",
    "stress_summary",
    "stress_timeline",
    "body_battery",
    "respiration",
    "spo2",
    "intensity",
    "training_readiness",
    "training_status",
)

TREND_FIELDS = (
    "sleep_score",
    "sleep_total_min",
    "hr_resting_bpm",
    "hrv_last_night_avg_ms",
    "stress_avg",
    "steps",
    "training_readiness_score",
    "training_load",
)


TOOLS = [
    {
        "name": "get_garmin_data",
        "description": "Read Garmin daily health data for a named calendar period.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": sorted(PERIODS),
                    "description": "Calendar period ending today in Asia/Bangkok.",
                }
            },
            "required": ["period"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_garmin_day",
        "description": "Read Garmin health data for one specific calendar date (YYYY-MM-DD).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "format": "date"},
            },
            "required": ["date"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_garmin_activities",
        "description": "Read individual Garmin workouts for a named calendar period.",
        "inputSchema": {
            "type": "object",
            "properties": {"period": {"type": "string", "enum": sorted(PERIODS)}},
            "required": ["period"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_garmin_metric_payload",
        "description": "Read one detailed Garmin metric feed for a bounded calendar period.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "metric_type": {"type": "string", "enum": list(METRIC_TYPES)},
                "period": {"type": "string", "enum": sorted(PERIODS)},
            },
            "required": ["metric_type", "period"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_garmin_trends",
        "description": "Compare average health metrics for a period with the immediately preceding period of equal length.",
        "inputSchema": {
            "type": "object",
            "properties": {"period": {"type": "string", "enum": sorted(PERIODS)}},
            "required": ["period"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_garmin_readiness",
        "description": "Read the compact recovery and training-readiness view for a calendar date; defaults to today in Asia/Bangkok.",
        "inputSchema": {
            "type": "object",
            "properties": {"date": {"type": "string", "format": "date"}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_garmin_alerts",
        "description": "Return rule-based recovery alerts for a date, compared with the preceding 28 days when enough data exists.",
        "inputSchema": {
            "type": "object",
            "properties": {"date": {"type": "string", "format": "date"}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
]


def initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "garmin-health", "version": "0.3.0"},
    }


def _period(arguments: dict[str, Any], tz_name: str) -> tuple[str, date, date]:
    period = arguments.get("period")
    if not isinstance(period, str):
        raise ValueError("period is required")
    start, end = period_window(period, tz_name)
    return period, start, end


def _selected_date(arguments: dict[str, Any], tz_name: str) -> date:
    raw_date = arguments.get("date")
    if raw_date is None:
        return period_window("daily", tz_name)[1]
    if not isinstance(raw_date, str):
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(raw_date)


def _mean(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [row[field] for row in rows if isinstance(row.get(field), (int, float))]
    return round(sum(values) / len(values), 2) if values else None


def _trends(current: list[dict[str, Any]], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trends = []
    for field in TREND_FIELDS:
        current_average = _mean(current, field)
        previous_average = _mean(previous, field)
        if current_average is None or previous_average is None:
            continue
        delta = round(current_average - previous_average, 2)
        trends.append(
            {
                "metric": field,
                "current_average": current_average,
                "previous_average": previous_average,
                "absolute_change": delta,
                "percent_change": round((delta / previous_average) * 100, 1) if previous_average else None,
            }
        )
    return trends


def _alerts(row: dict[str, Any], baseline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    hrv_baseline = _mean(baseline, "hrv_last_night_avg_ms")
    resting_hr_baseline = _mean(baseline, "hr_resting_bpm")
    if hrv_baseline and isinstance(row.get("hrv_last_night_avg_ms"), (int, float)) and row["hrv_last_night_avg_ms"] < hrv_baseline * 0.8:
        alerts.append({"metric": "hrv_last_night_avg_ms", "severity": "warning", "message": "Overnight HRV is more than 20% below the 28-day average."})
    if resting_hr_baseline and isinstance(row.get("hr_resting_bpm"), (int, float)) and row["hr_resting_bpm"] >= resting_hr_baseline + 5:
        alerts.append({"metric": "hr_resting_bpm", "severity": "warning", "message": "Resting heart rate is at least 5 bpm above the 28-day average."})
    if isinstance(row.get("sleep_total_min"), (int, float)) and row["sleep_total_min"] < 360:
        alerts.append({"metric": "sleep_total_min", "severity": "warning", "message": "Sleep was under 6 hours."})
    if isinstance(row.get("stress_avg"), (int, float)) and row["stress_avg"] >= 60:
        alerts.append({"metric": "stress_avg", "severity": "warning", "message": "Average stress was 60 or higher."})
    if isinstance(row.get("training_readiness_score"), (int, float)) and row["training_readiness_score"] <= 25:
        alerts.append({"metric": "training_readiness_score", "severity": "warning", "message": "Training readiness was 25 or lower."})
    return alerts


def tool_result(
    name: str,
    arguments: dict[str, Any],
    database: RowReader,
    tz_name: str,
    activities_database: DateColumnRowReader | None = None,
    metrics_database: DateColumnRowReader | None = None,
) -> dict[str, Any]:
    try:
        if name == "get_garmin_data":
            period, start, end = _period(arguments, tz_name)
            payload = {
                "period": period,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "rows": database.fetch_rows(start.isoformat(), end.isoformat()),
            }
        elif name == "get_garmin_day":
            selected = _selected_date(arguments, tz_name)
            payload = {
                "date": selected.isoformat(),
                "rows": database.fetch_rows(selected.isoformat(), selected.isoformat()),
            }
        elif name == "get_garmin_activities":
            if activities_database is None:
                raise RuntimeError("Activity data is unavailable")
            period, start, end = _period(arguments, tz_name)
            rows = activities_database.fetch_rows_by_date_column("calendar_date", start.isoformat(), end.isoformat())
            payload = {"period": period, "start_date": start.isoformat(), "end_date": end.isoformat(), "rows": rows}
        elif name == "get_garmin_metric_payload":
            if metrics_database is None:
                raise RuntimeError("Detailed metric data is unavailable")
            metric_type = arguments.get("metric_type")
            if metric_type not in METRIC_TYPES:
                raise ValueError("metric_type must be a supported Garmin metric feed")
            period, start, end = _period(arguments, tz_name)
            rows = metrics_database.fetch_rows_by_date_column("calendar_date", start.isoformat(), end.isoformat())
            payload = {"metric_type": metric_type, "period": period, "start_date": start.isoformat(), "end_date": end.isoformat(), "rows": [row for row in rows if row.get("metric_type") == metric_type]}
        elif name == "get_garmin_trends":
            period, start, end = _period(arguments, tz_name)
            days = (end - start).days + 1
            previous_end = start - timedelta(days=1)
            previous_start = previous_end - timedelta(days=days - 1)
            current_rows = database.fetch_rows(start.isoformat(), end.isoformat())
            previous_rows = database.fetch_rows(previous_start.isoformat(), previous_end.isoformat())
            payload = {
                "period": period,
                "current_window": {"start_date": start.isoformat(), "end_date": end.isoformat(), "row_count": len(current_rows)},
                "previous_window": {"start_date": previous_start.isoformat(), "end_date": previous_end.isoformat(), "row_count": len(previous_rows)},
                "trends": _trends(current_rows, previous_rows),
            }
        elif name == "get_garmin_readiness":
            selected = _selected_date(arguments, tz_name)
            rows = database.fetch_rows(selected.isoformat(), selected.isoformat())
            row = rows[0] if rows else None
            payload = {
                "date": selected.isoformat(),
                "available": row is not None,
                "readiness": None if row is None else {field: row.get(field) for field in ("sleep_score", "sleep_total_min", "hrv_last_night_avg_ms", "hr_resting_bpm", "stress_avg", "body_battery_high", "body_battery_low", "training_readiness_score", "training_load")},
            }
        elif name == "get_garmin_alerts":
            selected = _selected_date(arguments, tz_name)
            baseline_start = selected - timedelta(days=28)
            rows = database.fetch_rows(baseline_start.isoformat(), selected.isoformat())
            today_rows = [row for row in rows if row.get("date") == selected.isoformat()]
            baseline = [row for row in rows if row.get("date") != selected.isoformat()]
            payload = {
                "date": selected.isoformat(),
                "baseline_days_available": len(baseline),
                "alerts": [] if not today_rows else _alerts(today_rows[0], baseline),
            }
        else:
            raise LookupError(f"Unknown tool: {name}")
    except (ValueError, LookupError) as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    except Exception as exc:
        return {
            "content": [{"type": "text", "text": f"Data query failed: {type(exc).__name__}"}],
            "isError": True,
        }

    if "rows" in payload:
        payload["row_count"] = len(payload["rows"])
    return {
        "content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}],
        "structuredContent": payload,
    }
