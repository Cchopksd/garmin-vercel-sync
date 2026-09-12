from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from garminconnect import Garmin

from .models import GarminSnapshot
from .upstash import UpstashREST

TOKEN_FILENAME = "garmin_tokens.json"


def _safe_dict(call, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        value = call()
        return value if isinstance(value, dict) else (default or {})
    except Exception as exc:
        print(f"warning: Garmin endpoint failed: {type(exc).__name__}: {exc}")
        return default or {}


def _safe_list(call) -> list[dict[str, Any]]:
    try:
        value = call()
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []
    except Exception as exc:
        print(f"warning: Garmin endpoint failed: {type(exc).__name__}: {exc}")
        return []


def _activities_with_details(client: Garmin, date: str) -> list[dict[str, Any]]:
    """Fetch activity streams as well as summary fields when Garmin exposes them."""
    activities = _safe_list(lambda: client.get_activities_by_date(date, date))
    for activity in activities:
        activity_id = activity.get("activityId") or activity.get("id")
        if activity_id is not None:
            activity["activityDetails"] = _safe_dict(
                lambda activity_id=activity_id: client.get_activity_details(str(activity_id))
            )
    return activities


def fetch_snapshot(client: Garmin, date: str) -> GarminSnapshot:
    return GarminSnapshot(
        date=date,
        stats=_safe_dict(lambda: client.get_stats(date)),
        heart_rate=_safe_dict(lambda: client.get_heart_rates(date)),
        sleep=_safe_dict(lambda: client.get_sleep_data(date)),
        hrv=_safe_dict(lambda: client.get_hrv_data(date), default={}) or None,
        stress=_safe_dict(lambda: client.get_stress_data(date)),
        body_battery=_safe_list(lambda: client.get_body_battery(date, date)),
        respiration=_safe_dict(lambda: client.get_respiration_data(date)),
        spo2=_safe_dict(lambda: client.get_spo2_data(date)),
        intensity=_safe_dict(lambda: client.get_intensity_minutes_data(date)),
        all_day_stress=_safe_dict(lambda: client.get_all_day_stress(date)),
        training_readiness=_safe_dict(
            lambda: client.get_morning_training_readiness(date), default={}
        ) or None,
        training_status=_safe_dict(lambda: client.get_training_status(date)),
        activities=_activities_with_details(client, date),
    )


class GarminSession:
    """Materialize Garmin OAuth JSON only in a temporary directory."""

    def __init__(self, redis: UpstashREST, redis_key: str):
        self.redis = redis
        self.redis_key = redis_key
        self._temp: tempfile.TemporaryDirectory[str] | None = None
        self.token_dir: Path | None = None
        self.client: Garmin | None = None

    def __enter__(self) -> "GarminSession":
        token_json = self.redis.get(self.redis_key)
        if not token_json:
            raise RuntimeError(
                "Garmin OAuth token is missing in Upstash. Run scripts/bootstrap_garmin.py locally first."
            )

        self._temp = tempfile.TemporaryDirectory(prefix="garmin-oauth-")
        self.token_dir = Path(self._temp.name)
        token_file = self.token_dir / TOKEN_FILENAME
        token_file.write_text(token_json, encoding="utf-8")
        os.chmod(token_file, 0o600)

        client = Garmin()
        client.login(str(self.token_dir))
        self.client = client
        return self

    def persist(self) -> None:
        if not self.token_dir:
            return
        token_file = self.token_dir / TOKEN_FILENAME
        if token_file.exists():
            self.redis.set(self.redis_key, token_file.read_text(encoding="utf-8"))

    def __exit__(self, exc_type, exc, tb) -> None:
        # garminconnect persists refreshed tokens to its tokenstore. Copy the
        # resulting JSON back to Upstash before /tmp disappears.
        try:
            self.persist()
        finally:
            if self._temp:
                self._temp.cleanup()
