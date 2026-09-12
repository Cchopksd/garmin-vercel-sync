import json
from unittest.mock import patch

import pytest

from garmin_vercel_sync.mcp_auth import MCPAuthError, validate_supabase_access_token


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_accepts_the_configured_google_email():
    with patch("garmin_vercel_sync.mcp_auth.urlopen", return_value=_Response({"email": "Me@Example.com"})):
        assert validate_supabase_access_token("https://example.supabase.co", "key", "token", "me@example.com") == "Me@Example.com"


def test_rejects_a_different_google_email():
    with patch("garmin_vercel_sync.mcp_auth.urlopen", return_value=_Response({"email": "other@example.com"})):
        with pytest.raises(MCPAuthError, match="not allowed"):
            validate_supabase_access_token("https://example.supabase.co", "key", "token", "me@example.com")
