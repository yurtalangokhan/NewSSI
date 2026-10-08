from types import SimpleNamespace

import pytest

from service.chat_runs.settings import ChatRunSettings


def _source(**overrides):
    values = {
        "CHAT_RUN_REPLAY_TTL_SECONDS": 1800,
        "CHAT_RUN_LEASE_TTL_SECONDS": 10.0,
        "CHAT_RUN_HEARTBEAT_SECONDS": 2.0,
        "CHAT_RUN_MAX_EVENTS": 50000,
        "CHAT_RUN_CANCEL_GRACE_SECONDS": 5.0,
        "CHAT_RUN_SHUTDOWN_GRACE_SECONDS": 20.0,
        "CHAT_RUN_REAPER_INTERVAL_SECONDS": 10.0,
        "CHAT_RUN_MAX_DURATION_SECONDS": 3600,
        "STREAM_HEARTBEAT_SECONDS": 15.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_from_env_maps_every_key():
    settings = ChatRunSettings.from_env(_source())
    assert settings.replay_ttl_seconds == 1800
    assert settings.sse_heartbeat_seconds == 15.0
    assert settings.max_events == 50000


def test_replay_window_defaults_to_ten_minutes():
    assert ChatRunSettings().replay_ttl_seconds == 600


@pytest.mark.parametrize("ttl", [599, 1801, 0])
def test_replay_ttl_outside_ten_to_thirty_minutes_fails_fast(ttl):
    with pytest.raises(ValueError, match="replay_ttl_seconds"):
        ChatRunSettings.from_env(_source(CHAT_RUN_REPLAY_TTL_SECONDS=ttl))


def test_lease_must_outlive_two_heartbeats():
    with pytest.raises(ValueError, match="lease_ttl_seconds"):
        ChatRunSettings.from_env(
            _source(CHAT_RUN_LEASE_TTL_SECONDS=4.0, CHAT_RUN_HEARTBEAT_SECONDS=2.0)
        )


@pytest.mark.parametrize(
    "key",
    [
        "CHAT_RUN_HEARTBEAT_SECONDS",
        "CHAT_RUN_REAPER_INTERVAL_SECONDS",
        "CHAT_RUN_MAX_DURATION_SECONDS",
    ],
)
def test_intervals_must_be_positive(key):
    with pytest.raises(ValueError):
        ChatRunSettings.from_env(_source(**{key: 0}))


def test_max_events_has_a_floor():
    with pytest.raises(ValueError, match="max_events"):
        ChatRunSettings.from_env(_source(CHAT_RUN_MAX_EVENTS=999))
