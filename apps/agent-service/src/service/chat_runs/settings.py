"""Chat-run tunables, validated once at startup so a bad value fails fast."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REPLAY_TTL_MIN_SECONDS = 600
REPLAY_TTL_MAX_SECONDS = 1800
MAX_EVENTS_FLOOR = 1000


@dataclass(frozen=True, slots=True)
class ChatRunSettings:
    replay_ttl_seconds: int = 600
    lease_ttl_seconds: float = 10.0
    heartbeat_seconds: float = 2.0
    max_events: int = 50_000
    cancel_grace_seconds: float = 5.0
    shutdown_grace_seconds: float = 20.0
    reaper_interval_seconds: float = 10.0
    max_duration_seconds: int = 3600
    sse_heartbeat_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not REPLAY_TTL_MIN_SECONDS <= self.replay_ttl_seconds <= REPLAY_TTL_MAX_SECONDS:
            raise ValueError(f"replay_ttl_seconds must be within {REPLAY_TTL_MIN_SECONDS}..{REPLAY_TTL_MAX_SECONDS}")
        for name in (
            "heartbeat_seconds",
            "reaper_interval_seconds",
            "max_duration_seconds",
            "sse_heartbeat_seconds",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("cancel_grace_seconds", "shutdown_grace_seconds"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")
        if self.lease_ttl_seconds <= 2 * self.heartbeat_seconds:
            raise ValueError("lease_ttl_seconds must exceed two heartbeats")
        if self.max_events < MAX_EVENTS_FLOOR:
            raise ValueError(f"max_events must be at least {MAX_EVENTS_FLOOR}")

    @classmethod
    def from_env(cls, source: Any) -> ChatRunSettings:
        return cls(
            replay_ttl_seconds=source.CHAT_RUN_REPLAY_TTL_SECONDS,
            lease_ttl_seconds=source.CHAT_RUN_LEASE_TTL_SECONDS,
            heartbeat_seconds=source.CHAT_RUN_HEARTBEAT_SECONDS,
            max_events=source.CHAT_RUN_MAX_EVENTS,
            cancel_grace_seconds=source.CHAT_RUN_CANCEL_GRACE_SECONDS,
            shutdown_grace_seconds=source.CHAT_RUN_SHUTDOWN_GRACE_SECONDS,
            reaper_interval_seconds=source.CHAT_RUN_REAPER_INTERVAL_SECONDS,
            max_duration_seconds=source.CHAT_RUN_MAX_DURATION_SECONDS,
            sse_heartbeat_seconds=source.STREAM_HEARTBEAT_SECONDS,
        )
