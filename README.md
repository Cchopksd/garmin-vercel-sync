# Garmin → Supabase on Vercel Hobby

โครงสร้างนี้ทำมาเพื่อเก็บ Garmin health history เองโดยไม่พึ่ง subscription ของ fitness connector:

```text
Garmin Connect
     ↓
Vercel Python Function  ← Vercel Cron (วันละครั้ง)
     ↓
Supabase Postgres  ← history หลัก

Garmin OAuth token
     ↕
Upstash Redis
```

## สิ่งที่เก็บ

เก็บแบบแยกตาราง ไม่ยัดทุกอย่างลง daily row เดียว:

| ตาราง | หน้าที่ |
| --- | --- |
| `garmin_health` | daily summary สำหรับ dashboard/query เร็ว: sleep stages/score, resting-min-max HR, HRV, stress, Body Battery, steps/distance/floors/calories/intensity, SpO₂, respiration, skin temperature (หาก Garmin ส่งมา), VO₂ max, training load/readiness |
| `garmin_activities` | หนึ่งแถวต่อ activity/workout: เวลา, distance, speed, HR, cadence, training effect และ `raw_activity` สำหรับ GPS/metrics เฉพาะชนิดกีฬา |
| `garmin_metric_payloads` | หนึ่งแถวต่อวันต่อ endpoint (`heart_rate`, `sleep`, `hrv`, `spo2`, `respiration`, `stress_timeline`, `body_battery`, training ฯลฯ) ใน `payload` แบบ JSONB จึงไม่ทิ้ง intraday time-series, sleep movement, charge/drain events หรือ field ใหม่จาก Garmin |

ตาราง summary และ payload upsert ซ้ำได้ตามวันที่; activity upsert ด้วย `activity_id`.

`GET /api/data` อ่าน summary, `GET /api/activities` อ่าน workout, และ `GET /api/metric-payloads?metric_type=heart_rate` อ่านข้อมูลดิบแบบละเอียด (ทุก endpoint ต้องส่ง `Authorization: Bearer $CRON_SECRET`).

ข้อจำกัด: wrapper แบบ unofficial นี้ไม่มี endpoint ECG ที่เชื่อถือได้ และ Garmin อาจไม่ส่ง skin temperature, Pulse Ox แบบ all-day, หรือ training metric บางรายการตามรุ่นอุปกรณ์/ภูมิภาค/การตั้งค่า ดังนั้นระบบจะเก็บค่าที่ API ส่งจริงและปล่อยเป็น `null` เมื่อไม่มีข้อมูล ไม่สร้างค่าขึ้นมาเอง.

> `garminconnect` เป็น unofficial Garmin Connect API wrapper ไม่ใช่ Garmin Health API อย่างเป็นทางการ Endpoint อาจเปลี่ยนในอนาคต

## ทำไมแยก Backfill ออกจาก Vercel

Daily cron ดึงเพียง 3 วันล่าสุดเพื่อเก็บวันนี้และแก้ข้อมูล Sleep/HRV ที่ Garmin ประมวลผลย้อนหลัง ส่วนการ backfill หลายเดือน/หลายปีให้รันจากเครื่องตัวเอง ลดความเสี่ยงชน function timeout และ rate limit.

## 1. สร้าง Supabase table

1. สร้าง Supabase project แล้วเปิด SQL Editor
2. รันไฟล์ [`supabase/schema.sql`](supabase/schema.sql)
3. จาก Project Settings → API Keys คัดลอก `Project URL` และ `secret` key

`secret` key bypasses Row Level Security จึงใช้ได้เฉพาะ Vercel environment variables และ local shell ของคุณเท่านั้น ห้ามใส่ใน browser, client app หรือ commit ลง Git.

## 2. สร้าง Upstash Redis Free

สร้าง Redis database แล้ว copyค่า HTTPS REST URL และ Standard REST token จาก Upstash Console.

Local shell (copy the complete Upstash REST token; do not use a shortened value ending in `…`):

```bash
export UPSTASH_REDIS_REST_URL='https://xxxx.upstash.io'
export UPSTASH_REDIS_REST_TOKEN='...'
export GARMIN_TOKEN_REDIS_KEY='garmin:oauth:primary'
```

## 3. Bootstrap Garmin OAuth ครั้งแรก (Local เท่านั้น)

ใช้ Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python scripts/bootstrap_garmin.py --email 'your-garmin-email@example.com'
```

Script จะถาม Garmin password และ MFA ที่ terminal. Password ไม่ถูกเขียนลงไฟล์หรืออัปโหลดไป Vercel/Upstash; สิ่งที่ส่งไป Upstash คือ OAuth token JSON ที่ Garmin สร้างให้หลัง login.

## 4. ตั้ง Environment Variables บน Vercel

เพิ่มใน Project → Settings → Environment Variables:

```text
CRON_SECRET=<random-long-secret>
UPSTASH_REDIS_REST_URL=https://xxxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=...
GARMIN_TOKEN_REDIS_KEY=garmin:oauth:primary
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=...
SUPABASE_TABLE=garmin_health
TZ_NAME=Asia/Bangkok
SYNC_DAYS=3
```

สร้าง secret ได้เช่น:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

อย่า commit `.env` หรือ Supabase service-role key.

## 5. Deploy Vercel

```bash
npm i -g vercel
vercel
vercel --prod
```

Project ใช้ `api/index.py` เป็น FastAPI entrypoint และ pin Python 3.12 ใน `pyproject.toml`/`.python-version`.

Cron ใน `vercel.json`:

```json
{
  "path": "/api/sync",
  "schedule": "15 18 * * *"
}
```

Vercel cron ใช้ UTC ดังนั้น `18:15 UTC` = `01:15` ของวันถัดไปที่ Bangkok (UTC+7). Daily sync จะคำนวณวันที่จาก `Asia/Bangkok` อีกชั้นหนึ่ง.

## 6. ทดสอบ Production

Health endpoint แบบ public:

```bash
curl https://YOUR-PROJECT.vercel.app/api
```

เช็ก config/token (ต้อง auth):

```bash
curl https://YOUR-PROJECT.vercel.app/api/status \
  -H "Authorization: Bearer $CRON_SECRET"
```

สั่ง sync เอง:

```bash
curl https://YOUR-PROJECT.vercel.app/api/sync \
  -H "Authorization: Bearer $CRON_SECRET"
```

ผลควรคล้าย:

```json
{
  "ok": true,
  "dates": ["2026-09-10", "2026-09-11", "2026-09-12"],
  "updated": 2,
  "inserted": 1,
  "table": "garmin_health"
}
```

## 7. Backfill history จากเครื่อง

ตั้ง env ของ Upstash + Supabase เหมือน Vercel แล้วรัน:

```bash
python scripts/backfill.py --from 2025-01-01 --to 2026-09-12
```

แนะนำเริ่ม 7–30 วันก่อนเพื่อตรวจ schema/ข้อมูล จากนั้นค่อยขยายช่วง. Script upsert ตาม date จึงรันซ้ำได้.

## Security notes

- Garmin password ใช้เฉพาะ local bootstrap และไม่ควรใส่ใน Vercel env
- OAuth token เป็น credential ที่มีสิทธิ์อ่าน Garmin account: ปกป้อง Upstash REST token และ Redis database
- Supabase secret key ถูกเก็บเป็น Vercel secret env เท่านั้น และห้ามส่งไป browser
- `/api/sync` และ `/api/status` ตรวจ `Authorization: Bearer $CRON_SECRET`
- OAuth JSON อยู่ใน `/tmp` ของ Vercel เฉพาะช่วง invocation และ chmod `0600`
- `garminconnect` 0.3.13 ใหม่กว่ารุ่นที่ได้รับผลกระทบจาก CVE-2026-54447 (patched ตั้งแต่ 0.3.5)

## การใช้ข้อมูล

ตาราง `public.garmin_health` เก็บหนึ่งแถวต่อวันและใช้ `date` เป็น primary key. Daily sync และ backfill จึงรันซ้ำได้อย่างปลอดภัย: วันที่ที่มีอยู่แล้วจะถูกอัปเดต ส่วนวันที่ใหม่จะถูกเพิ่ม.

## Troubleshooting

`Garmin OAuth token is missing in Upstash`
: รัน `scripts/bootstrap_garmin.py` ใหม่ และตรวจว่า Vercel ใช้ `GARMIN_TOKEN_REDIS_KEY` เดียวกัน.

`401 Unauthorized`
: header ไม่ตรง `CRON_SECRET`.

`Supabase request failed (401/403)`
: ตรวจ `SUPABASE_URL` และ `SUPABASE_SECRET_KEY`; ต้องใช้ secret key สำหรับงาน server-side นี้.

`Supabase request failed (404)`
: รัน `supabase/schema.sql` แล้วตรวจว่า `SUPABASE_TABLE` ตรงกับชื่อตาราง.

`Sync failed: ...Authentication...`
: OAuth token อาจหมดอายุ/ถูก revoke; bootstrap Garmin ใหม่จาก local.

Garmin endpoint บางตัว fail แต่ยังมี row
: ตั้งใจให้ partial data เขียนได้ แต่ endpoint ที่ fail จะเป็นช่องว่างในวันนั้น และ daily sync 3 วันจะพยายามเติมใหม่ในรอบถัดไป.
