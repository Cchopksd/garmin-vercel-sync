from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class MCPAuthError(RuntimeError):
    pass


def validate_supabase_access_token(
    supabase_url: str,
    service_key: str,
    access_token: str,
    allowed_email: str,
    timeout_s: int = 10,
) -> str:
    """Validate an OAuth access token with Supabase and restrict it to one user."""
    request = Request(f"{supabase_url.rstrip('/')}/auth/v1/user", method="GET")
    request.add_header("apikey", service_key)
    request.add_header("Authorization", f"Bearer {access_token}")
    try:
        with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - configured HTTPS URL
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        raise MCPAuthError("Invalid or expired OAuth access token") from exc
    email = payload.get("email") if isinstance(payload, dict) else None
    if not isinstance(email, str) or email.casefold() != allowed_email.casefold():
        raise MCPAuthError("This Google account is not allowed to access Garmin health data")
    return email
