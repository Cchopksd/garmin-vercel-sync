from garmin_vercel_sync.models import GarminSnapshot
from garmin_vercel_sync.normalize import COLUMNS, normalize_activities, normalize_metric_payloads, normalize_snapshot, row_values


def test_normalize_snapshot():
    snap = GarminSnapshot(
        date="2026-09-12",
        stats={
            "totalSteps": 9730,
            "totalDistanceMeters": 6543.2,
            "activeKilocalories": 420,
            "totalKilocalories": 2250,
            "restingHeartRate": 45,
            "minHeartRate": 43,
            "maxHeartRate": 115,
            "averageStressLevel": 17,
            "maxStressLevel": 98,
            "bodyBatteryChargedValue": 81,
            "bodyBatteryDrainedValue": 24,
            "bodyBatteryHighestValue": 93,
            "bodyBatteryLowestValue": 62,
            "moderateIntensityMinutes": 20,
            "vigorousIntensityMinutes": 12,
        },
        heart_rate={"restingHeartRate": 45, "minHeartRate": 43, "maxHeartRate": 115},
        sleep={
            "dailySleepDTO": {
                "sleepTimeSeconds": 7 * 3600 + 30 * 60,
                "deepSleepSeconds": 70 * 60,
                "lightSleepSeconds": 260 * 60,
                "remSleepSeconds": 120 * 60,
                "awakeSleepSeconds": 25 * 60,
                "sleepStartTimestampGMT": 1789153200000,
                "sleepEndTimestampGMT": 1789180200000,
                "sleepScores": {"overall": {"value": 84}},
            }
        },
        hrv={
            "hrvSummary": {
                "lastNightAvg": 56,
                "weeklyAvg": 53,
                "lastNight5MinHigh": 79,
                "status": "BALANCED",
            }
        },
        stress={"overallStressLevel": 19},
        body_battery=[],
    )

    row = normalize_snapshot(snap)
    assert row["date"] == "2026-09-12"
    assert row["sleep_score"] == 84
    assert row["sleep_total_min"] == 450.0
    assert row["sleep_deep_min"] == 70.0
    assert row["hr_resting_bpm"] == 45
    assert row["hrv_last_night_avg_ms"] == 56
    assert row["stress_avg"] == 17
    assert row["body_battery_charged"] == 81
    assert row["steps"] == 9730
    assert row["distance_km"] == 6.543
    assert len(row_values(row)) == len(COLUMNS)


def test_missing_data_becomes_blank_cells():
    snap = GarminSnapshot(
        date="2026-09-11",
        stats={},
        heart_rate={},
        sleep={},
        hrv=None,
        stress={},
        body_battery=[],
    )
    row = normalize_snapshot(snap)
    values = row_values(row)
    assert row["sleep_score"] is None
    assert "" in values


def test_normalizes_vitals_and_activity_without_dropping_raw_data():
    snap = GarminSnapshot(
        date="2026-09-12", stats={"floorsAscended": 9, "vo2MaxValue": 51}, heart_rate={}, sleep={},
        hrv=None, stress={}, body_battery=[],
        respiration={"averageRespirationValue": 14, "averageSleepRespirationValue": 12},
        spo2={"averageSpO2": 97, "averageSleepSpO2": 96},
        training_readiness={"score": 78}, training_status={"acuteTrainingLoad": 425},
        activities=[{"activityId": 123, "activityName": "Morning Run", "distance": 5000}],
    )
    row = normalize_snapshot(snap)
    assert row["respiration_avg_brpm"] == 14
    assert row["spo2_sleep_avg_pct"] == 96
    payload = normalize_metric_payloads(snap)
    assert next(item for item in payload if item["metric_type"] == "respiration")["payload"] == snap.respiration
    activity = normalize_activities(snap)[0]
    assert activity["activity_id"] == "123"
    assert activity["raw_activity"]["activityName"] == "Morning Run"
