from garmin_vercel_sync.mcp_protocol import MCP_PROTOCOL_VERSION, TOOLS, initialize_result, tool_result


class _Database:
    def fetch_rows(self, start_date, end_date):
        return [{"date": start_date, "steps": 100}]


def test_initialize_advertises_tools_capability():
    result = initialize_result()
    assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert [tool["name"] for tool in TOOLS] == ["get_garmin_data", "get_garmin_day"]


def test_data_tool_returns_structured_period_rows():
    result = tool_result("get_garmin_data", {"period": "daily"}, _Database(), "Asia/Bangkok")
    assert result["structuredContent"]["period"] == "daily"
    assert result["structuredContent"]["row_count"] == 1


def test_unknown_tool_returns_mcp_tool_error():
    result = tool_result("delete_everything", {}, _Database(), "Asia/Bangkok")
    assert result["isError"] is True
