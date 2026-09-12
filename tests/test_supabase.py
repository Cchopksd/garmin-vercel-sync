import json
from unittest.mock import patch

from garmin_vercel_sync.supabase import SupabaseREST


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_upsert_rows_counts_existing_dates_and_sends_merge_preference():
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        if request.method == "GET":
            return _Response([{"date": "2026-09-11"}])
        return _Response(None)

    database = SupabaseREST("https://example.supabase.co", "service-key", "garmin_health")
    with patch("garmin_vercel_sync.supabase.urlopen", side_effect=fake_urlopen):
        updated, inserted = database.upsert_rows(
            [{"date": "2026-09-11", "steps": 100}, {"date": "2026-09-12", "steps": 200}]
        )

    assert (updated, inserted) == (1, 1)
    assert requests[0].get_header("Apikey") == "service-key"
    assert requests[1].get_header("Prefer") == "resolution=merge-duplicates,return=minimal"
    assert json.loads(requests[1].data) == [
        {"date": "2026-09-11", "steps": 100},
        {"date": "2026-09-12", "steps": 200},
    ]


def test_fetch_rows_filters_and_orders_dates():
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return _Response([{"date": "2026-09-11", "steps": 200}])

    database = SupabaseREST("https://example.supabase.co", "service-key", "garmin_health")
    with patch("garmin_vercel_sync.supabase.urlopen", side_effect=fake_urlopen):
        rows = database.fetch_rows("2026-09-01", "2026-09-12")

    assert rows == [{"date": "2026-09-11", "steps": 200}]
    assert "date=gte.2026-09-01" in requests[0].full_url
    assert "date=lte.2026-09-12" in requests[0].full_url
    assert "order=date.asc" in requests[0].full_url


def test_upsert_and_fetch_support_separate_table_keys_and_date_columns():
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        if request.method == "GET":
            return _Response([{"activity_id": "42"}])
        return _Response(None)

    database = SupabaseREST("https://example.supabase.co", "service-key", "garmin_activities")
    with patch("garmin_vercel_sync.supabase.urlopen", side_effect=fake_urlopen):
        assert database.upsert_rows_on([{"activity_id": "42"}], "activity_id") == (1, 0)
        database.fetch_rows_by_date_column("calendar_date", "2026-09-01", "2026-09-12")

    assert "on_conflict=activity_id" in requests[1].full_url
    assert "calendar_date=gte.2026-09-01" in requests[2].full_url
