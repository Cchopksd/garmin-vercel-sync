from __future__ import annotations

import json
import time
from urllib.parse import quote

import requests


class UpstashError(RuntimeError):
    pass


class UpstashREST:
    def __init__(self, base_url: str, token: str, timeout_s: int = 15):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_s = timeout_s
        self._validate_credentials()

    def _validate_credentials(self) -> None:
        if not self.base_url.startswith("https://"):
            raise UpstashError("UPSTASH_REDIS_REST_URL must start with https://")
        if not self.token or self.token == "replace-me" or "…" in self.token:
            raise UpstashError(
                "UPSTASH_REDIS_REST_TOKEN is missing or contains a truncated placeholder. "
                "Copy the complete REST token from Upstash."
            )
        try:
            self.token.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise UpstashError(
                "UPSTASH_REDIS_REST_TOKEN contains unsupported characters. "
                "Copy the complete REST token from Upstash."
            ) from exc

    def _request(self, method: str, url: str, data: bytes | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        if data is not None:
            headers["Content-Type"] = "text/plain; charset=utf-8"
        for attempt in range(3):
            try:
                response = requests.request(
                    method, url, data=data, headers=headers, timeout=self.timeout_s
                )
                if response.status_code in (401, 403):
                    raise UpstashError(
                        "Upstash rejected the REST credentials. Verify the plain HTTPS REST URL "
                        "and copy the complete REST token from the Upstash console."
                    )
                if response.status_code >= 500:
                    if attempt == 2:
                        raise UpstashError(f"Upstash request failed with HTTP {response.status_code}")
                    raise requests.RequestException("Upstash temporary server error")
                if response.status_code >= 400:
                    raise UpstashError(f"Upstash request failed with HTTP {response.status_code}")
                payload = response.json()
                break
            except requests.RequestException as exc:
                if attempt == 2:
                    raise UpstashError("Upstash request failed after transient network retries") from exc
            time.sleep(0.5 * (attempt + 1))
        if isinstance(payload, dict) and payload.get("error"):
            raise UpstashError(str(payload["error"]))
        return payload

    def get(self, key: str) -> str | None:
        url = f"{self.base_url}/get/{quote(key, safe='')}"
        payload = self._request("GET", url)
        value = payload.get("result")
        return None if value is None else str(value)

    def set(self, key: str, value: str) -> None:
        # Upstash appends the POST body as the final Redis command parameter.
        url = f"{self.base_url}/set/{quote(key, safe='')}"
        payload = self._request("POST", url, value.encode("utf-8"))
        if payload.get("result") != "OK":
            raise UpstashError(f"Unexpected SET response: {payload!r}")
