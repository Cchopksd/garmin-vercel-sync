# Garmin → Supabase on Vercel Hobby

This project stores your Garmin health history without relying on a fitness-connector subscription:

```text
Garmin Connect
     ↓
Vercel Python Function  ← Vercel Cron (once a day)
     ↓
Supabase Postgres  ← primary history store

Garmin OAuth token
     ↕
Upstash Redis
```

## Stored data

Data is stored in separate tables rather than putting everything into one daily row:

| Table | Purpose |
| --- | --- |
| `garmin_health` | Daily summary for dashboards and fast queries: sleep stages/score, resting/min/max HR, HRV, stress, Body Battery, steps/distance/floors/calories/intensity, SpO₂, respiration, skin temperature (when Garmin provides it), VO₂ max, training load, and readiness. |
| `garmin_activities` | One row per activity/workout: time, distance, speed, heart rate, cadence, training effect, and `raw_activity` for GPS and sport-specific metrics. |
| `garmin_metric_payloads` | One row per day per endpoint (`heart_rate`, `sleep`, `hrv`, `spo2`, `respiration`, `stress_timeline`, `body_battery`, training, etc.) with the original JSON payload. This preserves intraday time series, sleep movement, charge/drain events, and new Garmin fields. |

Summary and metric-payload tables can be safely upserted by date. Activities are upserted by `activity_id`.

`GET /api/data` reads summaries, `GET /api/activities` reads workouts, and `GET /api/metric-payloads?metric_type=heart_rate` reads detailed raw data. Every REST endpoint requires `Authorization: Bearer $CRON_SECRET`.

> `garminconnect` is an unofficial Garmin Connect API wrapper, not the official Garmin Health API. Its endpoints may change in the future.

## MCP tools for AI

The MCP server uses `/mcp` and Supabase OAuth. Set `MCP_ALLOWED_EMAIL` to restrict access to one Google account. Every tool is read-only.

| Tool | Data available to the AI |
| --- | --- |
| `get_garmin_data` | Daily health summaries for a period (`daily`, `30d`, `60d`, `90d`, `180d`, `360d`, `ytd`). |
| `get_garmin_day` | Daily health summary for a single date. |
| `get_garmin_activities` | Workouts: sport, duration, distance, heart rate, cadence, and training effect. |
| `get_garmin_metric_payload` | One selected detailed feed, such as heart rate, sleep, HRV, stress, or Body Battery. |
| `get_garmin_trends` | Period averages compared with the immediately preceding period of equal length. |
| `get_garmin_readiness` | Compact recovery view: sleep, HRV, resting HR, stress, Body Battery, and training readiness. |
| `get_garmin_alerts` | Rule-based alerts using fixed thresholds and the preceding 28-day baseline. |

The tools do not expose OAuth tokens, generic Supabase queries, or write operations. `get_garmin_metric_payload` requires both a supported `metric_type` and a bounded period.

## Why backfill is separate from Vercel

The daily cron only fetches the most recent three days. This captures the current day and lets the service update sleep and HRV data that Garmin processes retrospectively. Backfill for months or years should run from your local machine to reduce the risk of function timeouts and rate limits.

## 1. Create Supabase tables

1. Create a Supabase project and open SQL Editor.
2. Run [`supabase/schema.sql`](supabase/schema.sql).
3. In **Project Settings → API Keys**, copy the Project URL and `secret` key.

The `secret` key bypasses Row Level Security. Use it only in Vercel environment variables and your local shell; never expose it in the browser or commit it to Git.

## 2. Create a free Upstash Redis database

Create a Redis database and copy its HTTPS REST URL and Standard REST token from the Upstash Console.

In your local shell (copy the complete token; do not use a shortened value ending in `…`):

```bash
export UPSTASH_REDIS_REST_URL='https://xxxx.upstash.io'
export UPSTASH_REDIS_REST_TOKEN='...'
export GARMIN_TOKEN_REDIS_KEY='garmin:oauth:primary'
```

## 3. Bootstrap Garmin OAuth for the first time (local only)

Use Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python scripts/bootstrap_garmin.py --email 'your-garmin-email@example.com'
```

The script prompts for your Garmin password and MFA in the terminal. It does not write the password to disk or upload it to Vercel or Upstash. Upstash only receives OAuth-token JSON created by Garmin after login.

## 4. Configure Vercel environment variables

Add these in **Project → Settings → Environment Variables**:

```text
CRON_SECRET=<random-long-secret>
UPSTASH_REDIS_REST_URL=https://xxxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=...
GARMIN_TOKEN_REDIS_KEY=garmin:oauth:primary
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=...
SUPABASE_PUBLISHABLE_KEY=...
MCP_ALLOWED_EMAIL=your-google-email@example.com
SUPABASE_TABLE=garmin_health
TZ_NAME=Asia/Bangkok
SYNC_DAYS=3
```

Generate a secret, for example:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Never commit `.env` files or Supabase service-role keys.

## 5. Deploy to Vercel

```bash
npm i -g vercel
vercel
vercel --prod
```

The project uses `api/index.py` as its FastAPI entrypoint and pins Python 3.12 in `pyproject.toml` and `.python-version`.

The cron in `vercel.json` runs at:

```json
{
  "path": "/api/sync",
  "schedule": "0 1 * * *"
}
```

Vercel cron schedules use UTC. The application independently calculates dates in `Asia/Bangkok`.

## 6. Test production

Public health endpoint:

```bash
curl https://YOUR-PROJECT.vercel.app/api
```

Check configuration and token status (authentication required):

```bash
curl https://YOUR-PROJECT.vercel.app/api/status \
  -H "Authorization: Bearer $CRON_SECRET"
```

Run a sync manually:

```bash
curl https://YOUR-PROJECT.vercel.app/api/sync \
  -H "Authorization: Bearer $CRON_SECRET"
```

Expected response:

```json
{
  "ok": true,
  "dates": ["2026-09-10", "2026-09-11", "2026-09-12"],
  "updated": 2,
  "inserted": 1,
  "table": "garmin_health"
}
```

## 7. Backfill history locally

Set the same Upstash and Supabase environment variables as Vercel, then run:

```bash
python scripts/backfill.py --from 2025-01-01 --to 2026-09-12
```

Start with 7–30 days to validate the schema and data, then expand the range. The script upserts by date, so it is safe to rerun.

## Security notes

- Use the Garmin password only for the local bootstrap; do not put it in Vercel environment variables.
- The OAuth token can read your Garmin account. Protect the Upstash REST token and Redis database.
- Store the Supabase secret key only as a Vercel server-side secret; never send it to the browser.
- `/api/sync`, `/api/backfill`, `/api/data`, `/api/activities`, `/api/metric-payloads`, and `/api/status` require `Authorization: Bearer $CRON_SECRET`.
- MCP uses a Supabase OAuth access token and verifies the email against `MCP_ALLOWED_EMAIL`.
- OAuth JSON exists in Vercel `/tmp` only during an invocation and uses permissions `0600`.
- `garminconnect` 0.3.13 is newer than the version affected by CVE-2026-54447, which was fixed in 0.3.5.

## Data usage

`public.garmin_health` stores one row per day, with `date` as the primary key. Daily sync and backfill are idempotent: existing days are updated and new days are inserted.

## Troubleshooting

`Garmin OAuth token is missing in Upstash`
: Run `scripts/bootstrap_garmin.py` again and confirm Vercel uses the same `GARMIN_TOKEN_REDIS_KEY`.

`401 Unauthorized`
: The authorization header does not match `CRON_SECRET`.

`Supabase request failed (401/403)`
: Check `SUPABASE_URL` and `SUPABASE_SECRET_KEY`. Server-side operations require the secret key.

`Supabase request failed (404)`
: Run `supabase/schema.sql` and confirm `SUPABASE_TABLE` matches the table name.

`Sync failed: ...Authentication...`
: The OAuth token may be expired or revoked. Bootstrap Garmin again from your local machine.

Some Garmin endpoints fail but a row is still stored
: This is intentional: partial data is saved, failed endpoint fields are left blank for that day, and the daily three-day sync attempts to fill them again on the next run.
