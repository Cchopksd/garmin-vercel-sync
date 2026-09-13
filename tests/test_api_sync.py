from types import SimpleNamespace
from unittest.mock import patch

from api.index import sync


def test_sync_always_includes_yesterday_when_configured_for_one_day():
    settings = SimpleNamespace(cron_secret="secret", sync_days=1)

    with (
        patch("api.index._settings", return_value=settings),
        patch("api.index._authorize"),
        patch("api.index.sync_recent", return_value={"ok": True}) as sync_recent,
    ):
        assert sync("Bearer secret") == {"ok": True}

    sync_recent.assert_called_once_with(settings, days=2)
