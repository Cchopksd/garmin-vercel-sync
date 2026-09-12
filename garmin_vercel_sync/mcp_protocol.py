from __future__ import annotations

import json
from datetime import date
from typing import Any, Protocol

from .date_ranges import PERIODS, period_window

MCP_PROTOCOL_VERSION = "2025-06-18"


class RowReader(Protocol):
    def fetch_rows(self, start_date: str, end_date: str) -> list[dict[str, Any]]: ...


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
]


def initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "garmin-health", "version": "0.3.0"},
    }


def tool_result(name: str, arguments: dict[str, Any], database: RowReader, tz_name: str) -> dict[str, Any]:
    try:
        if name == "get_garmin_data":
            period = arguments.get("period")
            if not isinstance(period, str):
                raise ValueError("period is required")
            start, end = period_window(period, tz_name)
            payload = {
                "period": period,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "rows": database.fetch_rows(start.isoformat(), end.isoformat()),
            }
        elif name == "get_garmin_day":
            raw_date = arguments.get("date")
            if not isinstance(raw_date, str):
                raise ValueError("date is required")
            selected = date.fromisoformat(raw_date)
            payload = {
                "date": selected.isoformat(),
                "rows": database.fetch_rows(selected.isoformat(), selected.isoformat()),
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

    payload["row_count"] = len(payload["rows"])
    return {
        "content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}],
        "structuredContent": payload,
    }
