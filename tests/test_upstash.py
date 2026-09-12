import pytest
import requests
from unittest.mock import Mock, patch

from garmin_vercel_sync.upstash import UpstashError, UpstashREST


def test_rejects_truncated_rest_token_before_a_network_request():
    with pytest.raises(UpstashError, match="truncated placeholder"):
        UpstashREST("https://example.upstash.io", "abc…")


def test_rejects_non_https_upstash_url():
    with pytest.raises(UpstashError, match="must start with https"):
        UpstashREST("http://example.upstash.io", "valid-token")


def test_converts_upstash_forbidden_response_to_actionable_error():
    client = UpstashREST("https://example.upstash.io", "valid-token")
    response = Mock(status_code=403)
    with patch(
        "garmin_vercel_sync.upstash.requests.request", return_value=response
    ):
        with pytest.raises(UpstashError, match="rejected the REST credentials"):
            client.set("garmin:oauth:primary", "token")


def test_retries_transient_network_errors():
    client = UpstashREST("https://example.upstash.io", "valid-token")
    response = Mock(status_code=200)
    response.json.return_value = {"result": "value"}
    with (
        patch(
            "garmin_vercel_sync.upstash.requests.request",
            side_effect=[requests.RequestException("busy"), response],
        ),
        patch("garmin_vercel_sync.upstash.time.sleep"),
    ):
        assert client.get("key") == "value"
