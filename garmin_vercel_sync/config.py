from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    cron_secret: str
    upstash_url: str
    upstash_token: str
    garmin_token_key: str
    supabase_url: str
    supabase_secret_key: str
    supabase_table: str
    tz_name: str
    sync_days: int

    @classmethod
    def from_env(cls) -> "Settings":
        sync_days = int(os.getenv("SYNC_DAYS", "3"))
        if sync_days < 1 or sync_days > 14:
            raise ValueError("SYNC_DAYS must be between 1 and 14")

        settings = cls(
            cron_secret=os.getenv("CRON_SECRET", ""),
            upstash_url=os.getenv("UPSTASH_REDIS_REST_URL", "").rstrip("/"),
            upstash_token=os.getenv("UPSTASH_REDIS_REST_TOKEN", ""),
            garmin_token_key=os.getenv("GARMIN_TOKEN_REDIS_KEY", "garmin:oauth:primary"),
            supabase_url=os.getenv("SUPABASE_URL", "").rstrip("/"),
            # SUPABASE_SECRET_KEY is the current Supabase server-side key name.
            # Keep the legacy name as a compatibility fallback for existing deployments.
            supabase_secret_key=os.getenv(
                "SUPABASE_SECRET_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
            ),
            supabase_table=os.getenv("SUPABASE_TABLE", "garmin_health"),
            tz_name=os.getenv("TZ_NAME", "Asia/Bangkok"),
            sync_days=sync_days,
        )
        missing = [
            name
            for name, value in {
                "CRON_SECRET": settings.cron_secret,
                "UPSTASH_REDIS_REST_URL": settings.upstash_url,
                "UPSTASH_REDIS_REST_TOKEN": settings.upstash_token,
                "SUPABASE_URL": settings.supabase_url,
                "SUPABASE_SECRET_KEY": settings.supabase_secret_key,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
        return settings
