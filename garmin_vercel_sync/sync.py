from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Settings
from .garmin_client import GarminSession, fetch_snapshot
from .normalize import normalize_activities, normalize_metric_payloads, normalize_snapshot
from .supabase import SupabaseREST
from .upstash import UpstashREST


def date_window(days: int, tz_name: str) -> list[str]:
    today = datetime.now(ZoneInfo(tz_name)).date()
    start = today - timedelta(days=days - 1)
    return [(start + timedelta(days=i)).isoformat() for i in range(days)]


def sync_recent(settings: Settings, days: int | None = None) -> dict:
    redis = UpstashREST(settings.upstash_url, settings.upstash_token)
    requested_days = settings.sync_days if days is None else days
    if requested_days < 1 or requested_days > 62:
        raise ValueError("Sync days must be between 1 and 62")
    dates = date_window(requested_days, settings.tz_name)

    rows = []
    activity_rows = []
    payload_rows = []
    with GarminSession(redis, settings.garmin_token_key) as session:
        assert session.client is not None
        for date in dates:
            snapshot = fetch_snapshot(session.client, date)
            rows.append(normalize_snapshot(snapshot))
            activity_rows.extend(normalize_activities(snapshot))
            payload_rows.extend(normalize_metric_payloads(snapshot))

    database = SupabaseREST(
        settings.supabase_url,
        settings.supabase_secret_key,
        settings.supabase_table,
    )
    updated, inserted = database.upsert_rows(rows)
    activity_updated = activity_inserted = 0
    if activity_rows:
        activities_database = SupabaseREST(
            settings.supabase_url, settings.supabase_secret_key, "garmin_activities"
        )
        activity_updated, activity_inserted = activities_database.upsert_rows_on(
            activity_rows, "activity_id"
        )
    payload_updated = payload_inserted = 0
    if payload_rows:
        payload_database = SupabaseREST(
            settings.supabase_url, settings.supabase_secret_key, "garmin_metric_payloads"
        )
        payload_updated, payload_inserted = payload_database.upsert_rows_on(payload_rows, "payload_id")
    return {
        "ok": True,
        "dates": dates,
        "updated": updated,
        "inserted": inserted,
        "activities_updated": activity_updated,
        "activities_inserted": activity_inserted,
        "metric_payloads_updated": payload_updated,
        "metric_payloads_inserted": payload_inserted,
        "table": settings.supabase_table,
    }
