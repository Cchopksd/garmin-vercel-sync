from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class SupabaseError(RuntimeError):
    pass


class SupabaseREST:
    def __init__(self, base_url: str, service_role_key: str, table: str, timeout_s: int = 20):
        self.base_url = base_url.rstrip("/")
        self.service_role_key = service_role_key
        self.table = table
        self.timeout_s = timeout_s

    def _request(self, request: Request) -> Any:
        request.add_header("apikey", self.service_role_key)
        request.add_header("Authorization", f"Bearer {self.service_role_key}")
        try:
            with urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310 - configured HTTPS URL
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SupabaseError(f"Supabase request failed ({exc.code}): {detail}") from exc
        try:
            return json.loads(body) if body else None
        except json.JSONDecodeError as exc:
            raise SupabaseError("Supabase returned invalid JSON") from exc

    def upsert_rows(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        return self.upsert_rows_on(rows, "date")

    def upsert_rows_on(self, rows: list[dict[str, Any]], key: str) -> tuple[int, int]:
        if not rows:
            return 0, 0

        values = [str(row[key]) for row in rows]
        existing_values = self._existing_values(key, values)
        url = f"{self.base_url}/rest/v1/{quote(self.table, safe='')}?on_conflict={quote(key, safe='')}"
        request = Request(
            url,
            data=json.dumps(rows, separators=(",", ":")).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Prefer", "resolution=merge-duplicates,return=minimal")
        self._request(request)
        updated = sum(value in existing_values for value in values)
        return updated, len(values) - updated

    def fetch_rows(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        return self.fetch_rows_by_date_column("date", start_date, end_date)

    def fetch_rows_by_date_column(self, column: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        query = urlencode(
            {
                "select": "*",
                column: [f"gte.{start_date}", f"lte.{end_date}"],
                "order": f"{column}.asc",
            },
            doseq=True,
        )
        url = f"{self.base_url}/rest/v1/{quote(self.table, safe='')}?{query}"
        payload = self._request(Request(url, method="GET"))
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise SupabaseError("Supabase returned an unexpected data response")
        return payload

    def _existing_values(self, key: str, values: list[str]) -> set[str]:
        quoted_values = ",".join(json.dumps(value) for value in values)
        url = (
            f"{self.base_url}/rest/v1/{quote(self.table, safe='')}"
            f"?select={quote(key, safe='')}&{quote(key, safe='')}=in.({quote(quoted_values, safe=',()')})"
        )
        payload = self._request(Request(url, method="GET"))
        if not isinstance(payload, list):
            raise SupabaseError("Supabase returned an unexpected key lookup response")
        return {str(row[key]) for row in payload if isinstance(row, dict) and row.get(key) is not None}
