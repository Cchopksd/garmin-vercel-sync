from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import GarminSnapshot


COLUMNS = [
    "date",
    "sleep_score",
    "sleep_total_min",
    "sleep_deep_min",
    "sleep_light_min",
    "sleep_rem_min",
    "sleep_awake_min",
    "sleep_start_utc",
    "sleep_end_utc",
    "hr_resting_bpm",
    "hr_min_bpm",
    "hr_max_bpm",
    "hrv_last_night_avg_ms",
    "hrv_weekly_avg_ms",
    "hrv_5min_high_ms",
    "hrv_status",
    "stress_avg",
    "stress_max",
    "body_battery_charged",
    "body_battery_drained",
    "body_battery_high",
    "body_battery_low",
    "steps",
    "distance_km",
    "active_calories_kcal",
    "total_calories_kcal",
    "moderate_intensity_min",
    "vigorous_intensity_min",
    "floors_climbed",
    "respiration_avg_brpm",
    "respiration_sleep_avg_brpm",
    "spo2_avg_pct",
    "spo2_sleep_avg_pct",
    "skin_temperature_avg_c",
    "training_readiness_score",
    "training_load",
    "vo2_max_running",
    "vo2_max_cycling",
    "source_updated_at_utc",
]


def _dig(obj: Any, *path: str, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _sec_to_min(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 60.0, 1)
    except (TypeError, ValueError):
        return None


def _m_to_km(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 1000.0, 3)
    except (TypeError, ValueError):
        return None


def _epoch_ms_to_utc_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(
            float(value) / 1000.0, tz=timezone.utc
        ).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _body_battery(snapshot: GarminSnapshot) -> dict[str, Any]:
    # Newer get_stats responses already expose the daily aggregate fields.
    stats = snapshot.stats
    result = {
        "charged": stats.get("bodyBatteryChargedValue"),
        "drained": stats.get("bodyBatteryDrainedValue"),
        "high": stats.get("bodyBatteryHighestValue"),
        "low": stats.get("bodyBatteryLowestValue"),
    }

    if all(v is not None for v in result.values()):
        return result

    # Endpoint shapes have changed across Garmin versions/accounts. Fill any
    # missing values from the first matching item without assuming one schema.
    for item in snapshot.body_battery:
        result["charged"] = _first(
            result["charged"], item.get("charged"), item.get("bodyBatteryChargedValue")
        )
        result["drained"] = _first(
            result["drained"], item.get("drained"), item.get("bodyBatteryDrainedValue")
        )
        result["high"] = _first(
            result["high"],
            item.get("highest"),
            item.get("high"),
            item.get("bodyBatteryHighestValue"),
        )
        result["low"] = _first(
            result["low"],
            item.get("lowest"),
            item.get("low"),
            item.get("bodyBatteryLowestValue"),
        )
    return result


def normalize_snapshot(snapshot: GarminSnapshot) -> dict[str, Any]:
    stats = snapshot.stats
    hr = snapshot.heart_rate
    sleep_dto = _dig(snapshot.sleep, "dailySleepDTO", default={}) or {}
    hrv_summary = _dig(snapshot.hrv or {}, "hrvSummary", default={}) or {}
    bb = _body_battery(snapshot)

    sleep_score = _dig(sleep_dto, "sleepScores", "overall", "value")

    stress_avg = _first(
        stats.get("averageStressLevel"),
        snapshot.stress.get("overallStressLevel"),
        snapshot.stress.get("averageStressLevel"),
    )
    stress_max = _first(
        stats.get("maxStressLevel"),
        snapshot.stress.get("maxStressLevel"),
    )

    row = {
        "date": snapshot.date,
        "sleep_score": sleep_score,
        "sleep_total_min": _sec_to_min(sleep_dto.get("sleepTimeSeconds")),
        "sleep_deep_min": _sec_to_min(sleep_dto.get("deepSleepSeconds")),
        "sleep_light_min": _sec_to_min(sleep_dto.get("lightSleepSeconds")),
        "sleep_rem_min": _sec_to_min(sleep_dto.get("remSleepSeconds")),
        "sleep_awake_min": _sec_to_min(sleep_dto.get("awakeSleepSeconds")),
        # Use GMT values deliberately; Garmin has had local-timestamp offset
        # inconsistencies for some regions/accounts.
        "sleep_start_utc": _epoch_ms_to_utc_iso(
            sleep_dto.get("sleepStartTimestampGMT")
        ),
        "sleep_end_utc": _epoch_ms_to_utc_iso(
            sleep_dto.get("sleepEndTimestampGMT")
        ),
        "hr_resting_bpm": _first(
            hr.get("restingHeartRate"), stats.get("restingHeartRate")
        ),
        "hr_min_bpm": _first(hr.get("minHeartRate"), stats.get("minHeartRate")),
        "hr_max_bpm": _first(hr.get("maxHeartRate"), stats.get("maxHeartRate")),
        "hrv_last_night_avg_ms": hrv_summary.get("lastNightAvg"),
        "hrv_weekly_avg_ms": hrv_summary.get("weeklyAvg"),
        "hrv_5min_high_ms": hrv_summary.get("lastNight5MinHigh"),
        "hrv_status": hrv_summary.get("status"),
        "stress_avg": stress_avg,
        "stress_max": stress_max,
        "body_battery_charged": bb["charged"],
        "body_battery_drained": bb["drained"],
        "body_battery_high": bb["high"],
        "body_battery_low": bb["low"],
        "steps": stats.get("totalSteps"),
        "distance_km": _m_to_km(
            _first(stats.get("totalDistanceMeters"), stats.get("wellnessDistanceMeters"))
        ),
        "active_calories_kcal": _first(
            stats.get("activeKilocalories"), stats.get("wellnessActiveKilocalories")
        ),
        "total_calories_kcal": _first(
            stats.get("totalKilocalories"), stats.get("wellnessKilocalories")
        ),
        "moderate_intensity_min": stats.get("moderateIntensityMinutes"),
        "vigorous_intensity_min": stats.get("vigorousIntensityMinutes"),
        "floors_climbed": _first(stats.get("floorsAscended"), stats.get("floorsClimbed")),
        "respiration_avg_brpm": _first(
            snapshot.respiration.get("averageRespirationValue"),
            snapshot.respiration.get("avgRespirationValue"),
        ),
        "respiration_sleep_avg_brpm": _first(
            snapshot.respiration.get("averageSleepRespirationValue"),
            snapshot.respiration.get("avgSleepRespirationValue"),
        ),
        "spo2_avg_pct": _first(snapshot.spo2.get("averageSpO2"), snapshot.spo2.get("avgSpO2")),
        "spo2_sleep_avg_pct": _first(
            snapshot.spo2.get("averageSleepSpO2"), snapshot.spo2.get("avgSleepSpO2")
        ),
        "skin_temperature_avg_c": _first(
            stats.get("averageSkinTemperature"), stats.get("skinTemperature"),
            _dig(snapshot.sleep, "dailySleepDTO", "averageSkinTemperature"),
        ),
        "training_readiness_score": _first(
            (snapshot.training_readiness or {}).get("score"),
            (snapshot.training_readiness or {}).get("trainingReadinessScore"),
        ),
        "training_load": _first(
            snapshot.training_status.get("acuteTrainingLoad"),
            snapshot.training_status.get("trainingLoad"),
        ),
        "vo2_max_running": _first(stats.get("vo2MaxValue"), stats.get("vo2MaxPreciseValue")),
        "vo2_max_cycling": _first(stats.get("cyclingVo2MaxValue"), stats.get("cyclingVo2MaxPreciseValue")),
        "source_updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    return row


def normalize_metric_payloads(snapshot: GarminSnapshot) -> list[dict[str, Any]]:
    """Store each endpoint response in its own row for lossless time-series history.

    Daily summary columns are deliberately not used for streams such as 24/7 HR,
    stress, SpO2, respiration, sleep movement, and Body Battery events.
    """
    payloads: dict[str, Any] = {
        "daily_stats": snapshot.stats,
        "heart_rate": snapshot.heart_rate,
        "sleep": snapshot.sleep,
        "hrv": snapshot.hrv or {},
        "stress_summary": snapshot.stress,
        "stress_timeline": snapshot.all_day_stress,
        "body_battery": snapshot.body_battery,
        "respiration": snapshot.respiration,
        "spo2": snapshot.spo2,
        "intensity": snapshot.intensity,
        "training_readiness": snapshot.training_readiness or {},
        "training_status": snapshot.training_status,
    }
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "payload_id": f"{snapshot.date}:{metric_type}",
            "calendar_date": snapshot.date,
            "metric_type": metric_type,
            "payload": payload,
            "source_updated_at_utc": now,
        }
        for metric_type, payload in payloads.items()
    ]


def normalize_activities(snapshot: GarminSnapshot) -> list[dict[str, Any]]:
    """Return one lossless, idempotent row for each Garmin activity on a day."""
    rows: list[dict[str, Any]] = []
    for activity in snapshot.activities:
        activity_id = _first(activity.get("activityId"), activity.get("id"))
        if activity_id is None:
            continue
        rows.append(
            {
                "activity_id": str(activity_id),
                "calendar_date": snapshot.date,
                "activity_name": activity.get("activityName"),
                "activity_type": _first(
                    _dig(activity, "activityType", "typeKey"), activity.get("activityType")
                ),
                "start_time_utc": _first(activity.get("startTimeGMT"), activity.get("startTimeLocal")),
                "duration_sec": activity.get("duration"),
                "distance_m": activity.get("distance"),
                "average_hr_bpm": activity.get("averageHR"),
                "max_hr_bpm": activity.get("maxHR"),
                "average_speed_mps": activity.get("averageSpeed"),
                "max_speed_mps": activity.get("maxSpeed"),
                "average_cadence_rpm": activity.get("averageRunningCadenceInStepsPerMinute"),
                "training_effect_aerobic": activity.get("aerobicTrainingEffect"),
                "training_effect_anaerobic": activity.get("anaerobicTrainingEffect"),
                "raw_activity": activity,
                "source_updated_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def row_values(row: dict[str, Any]) -> list[Any]:
    # Retained for callers that need the stable column order used by the schema.
    return ["" if row.get(col) is None else row.get(col) for col in COLUMNS]
