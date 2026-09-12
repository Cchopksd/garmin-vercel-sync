#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

from garmin_vercel_sync.garmin_client import GarminSession, fetch_snapshot
from garmin_vercel_sync.normalize import normalize_activities, normalize_metric_payloads, normalize_snapshot
from garmin_vercel_sync.supabase import SupabaseREST
from garmin_vercel_sync.upstash import UpstashREST


def dates_between(start: date, end: date):
    current = start
    while current <= end:
        yield current.isoformat()
        current += timedelta(days=1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Garmin health history into Supabase from your local machine.")
    parser.add_argument("--from", dest="date_from", required=True)
    parser.add_argument("--to", dest="date_to", required=True)
    parser.add_argument("--batch-size", type=int, default=14)
    args = parser.parse_args()

    start = date.fromisoformat(args.date_from)
    end = date.fromisoformat(args.date_to)
    if start > end:
        raise SystemExit("--from must be <= --to")

    required = [
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
    ]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SystemExit("Missing env: " + ", ".join(missing))

    redis = UpstashREST(os.environ["UPSTASH_REDIS_REST_URL"], os.environ["UPSTASH_REDIS_REST_TOKEN"])
    redis_key = os.getenv("GARMIN_TOKEN_REDIS_KEY", "garmin:oauth:primary")
    database = SupabaseREST(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
        os.getenv("SUPABASE_TABLE", "garmin_health"),
    )

    pending = []
    pending_activities = []
    pending_payloads = []
    total_updated = total_inserted = 0
    with GarminSession(redis, redis_key) as session:
        assert session.client is not None
        for day in dates_between(start, end):
            print(f"fetch {day}")
            snapshot = fetch_snapshot(session.client, day)
            pending.append(normalize_snapshot(snapshot))
            pending_activities.extend(normalize_activities(snapshot))
            pending_payloads.extend(normalize_metric_payloads(snapshot))
            if len(pending) >= args.batch_size:
                updated, inserted = database.upsert_rows(pending)
                total_updated += updated
                total_inserted += inserted
                pending.clear()
                if pending_activities:
                    SupabaseREST(
                        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"], "garmin_activities"
                    ).upsert_rows_on(pending_activities, "activity_id")
                    pending_activities.clear()
                if pending_payloads:
                    SupabaseREST(
                        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"], "garmin_metric_payloads"
                    ).upsert_rows_on(pending_payloads, "payload_id")
                    pending_payloads.clear()
        if pending:
            updated, inserted = database.upsert_rows(pending)
            total_updated += updated
            total_inserted += inserted
        if pending_activities:
            SupabaseREST(
                os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"], "garmin_activities"
            ).upsert_rows_on(pending_activities, "activity_id")
        if pending_payloads:
            SupabaseREST(
                os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"], "garmin_metric_payloads"
            ).upsert_rows_on(pending_payloads, "payload_id")

    print(f"done: updated={total_updated}, inserted={total_inserted}")


if __name__ == "__main__":
    main()
