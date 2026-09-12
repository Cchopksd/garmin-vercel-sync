from garmin_vercel_sync.mcp_protocol import MCP_PROTOCOL_VERSION, TOOLS, initialize_result, tool_result


class _Database:
    def fetch_rows(self, start_date, end_date):
        return [{"date": start_date, "steps": 100, "sleep_score": 80, "hrv_last_night_avg_ms": 50}]


class _DateColumnDatabase:
    def fetch_rows_by_date_column(self, column, start_date, end_date):
        if column == "calendar_date":
            return [{"calendar_date": start_date, "metric_type": "heart_rate", "payload": {"value": 60}}]
        return []


def test_initialize_advertises_tools_capability():
    result = initialize_result()
    assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert [tool["name"] for tool in TOOLS] == [
        "get_garmin_data",
        "get_garmin_day",
        "get_garmin_activities",
        "get_garmin_metric_payload",
        "get_garmin_trends",
        "get_garmin_readiness",
        "get_garmin_alerts",
    ]


def test_data_tool_returns_structured_period_rows():
    result = tool_result("get_garmin_data", {"period": "daily"}, _Database(), "Asia/Bangkok")
    assert result["structuredContent"]["period"] == "daily"
    assert result["structuredContent"]["row_count"] == 1


def test_data_tool_accepts_a_single_date():
    result = tool_result("get_garmin_data", {"date": "2026-07-03"}, _Database(), "Asia/Bangkok")
    payload = result["structuredContent"]
    assert payload["period"] is None
    assert payload["start_date"] == "2026-07-03"


def test_unknown_tool_returns_mcp_tool_error():
    result = tool_result("delete_everything", {}, _Database(), "Asia/Bangkok")
    assert result["isError"] is True


def test_metric_tool_returns_only_the_requested_feed():
    result = tool_result(
        "get_garmin_metric_payload",
        {"metric_type": "heart_rate", "period": "daily"},
        _Database(),
        "Asia/Bangkok",
        metrics_database=_DateColumnDatabase(),
    )
    assert result["structuredContent"]["row_count"] == 1
    assert result["structuredContent"]["rows"][0]["metric_type"] == "heart_rate"


def test_metric_tool_accepts_a_custom_date_range():
    result = tool_result(
        "get_garmin_metric_payload",
        {"metric_type": "heart_rate", "start_date": "2026-07-03", "end_date": "2026-07-15"},
        _Database(),
        "Asia/Bangkok",
        metrics_database=_DateColumnDatabase(),
    )
    assert result["structuredContent"]["end_date"] == "2026-07-15"


def test_readiness_defaults_to_today_and_returns_compact_fields():
    result = tool_result("get_garmin_readiness", {}, _Database(), "Asia/Bangkok")
    readiness = result["structuredContent"]["readiness"]
    assert readiness["sleep_score"] == 80
    assert "steps" not in readiness


def test_activities_accepts_a_custom_date_range_and_type_filter():
    result = tool_result(
        "get_garmin_activities",
        {"start_date": "2026-07-03", "end_date": "2026-07-15", "activity_type": "running"},
        _Database(),
        "Asia/Bangkok",
        activities_database=_DateColumnDatabase(),
    )
    payload = result["structuredContent"]
    assert payload["start_date"] == "2026-07-03"
    assert payload["row_count"] == 0
