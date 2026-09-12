create table if not exists public.garmin_health (
  date date primary key,
  sleep_score numeric,
  sleep_total_min numeric,
  sleep_deep_min numeric,
  sleep_light_min numeric,
  sleep_rem_min numeric,
  sleep_awake_min numeric,
  sleep_start_utc timestamptz,
  sleep_end_utc timestamptz,
  hr_resting_bpm numeric,
  hr_min_bpm numeric,
  hr_max_bpm numeric,
  hrv_last_night_avg_ms numeric,
  hrv_weekly_avg_ms numeric,
  hrv_5min_high_ms numeric,
  hrv_status text,
  stress_avg numeric,
  stress_max numeric,
  body_battery_charged numeric,
  body_battery_drained numeric,
  body_battery_high numeric,
  body_battery_low numeric,
  steps numeric,
  distance_km numeric,
  active_calories_kcal numeric,
  total_calories_kcal numeric,
  moderate_intensity_min numeric,
  vigorous_intensity_min numeric,
  floors_climbed numeric,
  respiration_avg_brpm numeric,
  respiration_sleep_avg_brpm numeric,
  spo2_avg_pct numeric,
  spo2_sleep_avg_pct numeric,
  skin_temperature_avg_c numeric,
  training_readiness_score numeric,
  training_load numeric,
  vo2_max_running numeric,
  vo2_max_cycling numeric,
  source_updated_at_utc timestamptz not null
);

-- Safe to run on an existing installation made with an earlier schema.
alter table public.garmin_health add column if not exists floors_climbed numeric;
alter table public.garmin_health add column if not exists respiration_avg_brpm numeric;
alter table public.garmin_health add column if not exists respiration_sleep_avg_brpm numeric;
alter table public.garmin_health add column if not exists spo2_avg_pct numeric;
alter table public.garmin_health add column if not exists spo2_sleep_avg_pct numeric;
alter table public.garmin_health add column if not exists skin_temperature_avg_c numeric;
alter table public.garmin_health add column if not exists training_readiness_score numeric;
alter table public.garmin_health add column if not exists training_load numeric;
alter table public.garmin_health add column if not exists vo2_max_running numeric;
alter table public.garmin_health add column if not exists vo2_max_cycling numeric;

-- Lossless source payloads are intentionally separate from query-friendly
-- daily summaries. Each Garmin endpoint has one row per local calendar date.
create table if not exists public.garmin_metric_payloads (
  payload_id text primary key,
  calendar_date date not null,
  metric_type text not null check (metric_type in (
    'daily_stats', 'heart_rate', 'sleep', 'hrv', 'stress_summary',
    'stress_timeline', 'body_battery', 'respiration', 'spo2', 'intensity',
    'training_readiness', 'training_status'
  )),
  payload jsonb not null,
  source_updated_at_utc timestamptz not null,
  unique (calendar_date, metric_type)
);

create index if not exists garmin_metric_payloads_date_type_idx
  on public.garmin_metric_payloads (calendar_date desc, metric_type);

create table if not exists public.garmin_activities (
  activity_id text primary key,
  calendar_date date not null,
  activity_name text,
  activity_type text,
  start_time_utc timestamptz,
  duration_sec numeric,
  distance_m numeric,
  average_hr_bpm numeric,
  max_hr_bpm numeric,
  average_speed_mps numeric,
  max_speed_mps numeric,
  average_cadence_rpm numeric,
  training_effect_aerobic numeric,
  training_effect_anaerobic numeric,
  raw_activity jsonb not null default '{}'::jsonb,
  source_updated_at_utc timestamptz not null
);

create index if not exists garmin_activities_calendar_date_idx
  on public.garmin_activities (calendar_date desc);

alter table public.garmin_health enable row level security;
alter table public.garmin_activities enable row level security;
alter table public.garmin_metric_payloads enable row level security;
