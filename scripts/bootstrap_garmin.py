#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import os
import tempfile
from pathlib import Path

from garminconnect import Garmin

from garmin_vercel_sync.upstash import UpstashREST


def main() -> None:
    parser = argparse.ArgumentParser(description="Login to Garmin locally and upload OAuth token JSON to Upstash.")
    parser.add_argument("--email", default=os.getenv("GARMIN_EMAIL"))
    parser.add_argument("--upstash-url", default=os.getenv("UPSTASH_REDIS_REST_URL"))
    parser.add_argument("--upstash-token", default=os.getenv("UPSTASH_REDIS_REST_TOKEN"))
    parser.add_argument("--redis-key", default=os.getenv("GARMIN_TOKEN_REDIS_KEY", "garmin:oauth:primary"))
    args = parser.parse_args()

    email = args.email or input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (never uploaded by this script): ")
    if not args.upstash_url or not args.upstash_token:
        raise SystemExit("Set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN first.")

    with tempfile.TemporaryDirectory(prefix="garmin-bootstrap-") as temp:
        token_dir = Path(temp)
        client = Garmin(email, password, prompt_mfa=lambda: input("Garmin MFA code: ").strip())
        client.login(str(token_dir))
        token_file = token_dir / "garmin_tokens.json"
        if not token_file.exists():
            raise SystemExit("Garmin login succeeded but garmin_tokens.json was not created.")
        UpstashREST(args.upstash_url, args.upstash_token).set(
            args.redis_key,
            token_file.read_text(encoding="utf-8"),
        )
    print(f"Garmin OAuth token uploaded to Upstash key: {args.redis_key}")


if __name__ == "__main__":
    main()
