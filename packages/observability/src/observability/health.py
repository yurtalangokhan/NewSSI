"""Startup dependency health: policy classes, registry, and readiness payload.

A service records each dependency's startup state here; the readiness endpoint
turns the registry into the operator payload. The registry is deliberately a
per-service instance (created in the service binding), so tests never share
state across services.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class DependencyPolicy(StrEnum):
    """Policy class for a startup dependency."""

    REQUIRED = "required"
    DEGRADED = "degraded"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class DependencyStatus:
    """Immutable snapshot of one dependency's startup state."""

    name: str
    policy: DependencyPolicy
    status: str
    hint: str | None = None
    checked_at: str | None = None

    @property
    def ready(self) -> bool:
        """Whether this dependency allows the service to serve requests."""
        if self.status == "ok":
            return True
        if self.status == "degraded":
            return self.policy is not DependencyPolicy.REQUIRED
        return False


class DependencyRegistry:
    """In-memory registry of startup dependency states."""

    def __init__(self) -> None:
        """Initialise the dependency state store."""
        self._states: dict[str, DependencyStatus] = {}
        self._lock = threading.Lock()

    def record(self, status: DependencyStatus) -> None:
        """Store or replace the state for one dependency."""
        with self._lock:
            self._states[status.name] = status

    def record_ok(self, name: str, *, policy: DependencyPolicy = DependencyPolicy.REQUIRED) -> None:
        """Record a healthy dependency state."""
        self.record(
            DependencyStatus(
                name=name,
                policy=policy,
                status="ok",
                checked_at=datetime.now(UTC).isoformat(),
            )
        )

    def record_degraded(self, name: str, *, hint: str | None = None) -> None:
        """Record a degraded dependency state."""
        self.record(
            DependencyStatus(
                name=name,
                policy=DependencyPolicy.DEGRADED,
                status="degraded",
                hint=hint,
                checked_at=datetime.now(UTC).isoformat(),
            )
        )

    def get(self, name: str) -> DependencyStatus | None:
        """Return the current state for one dependency."""
        with self._lock:
            return self._states.get(name)

    def snapshot(self) -> dict[str, DependencyStatus]:
        """Return a copy of all recorded dependency states."""
        with self._lock:
            return dict(self._states)

    def ready(self) -> bool:
        """True when every required dependency has been checked and is usable.

        An empty registry is *not* ready: ``all([])`` is True, so before
        anything recorded a state this reported a green readiness over a
        dependency map nobody had ever filled in.
        """
        with self._lock:
            if not self._states:
                return False
            return all(
                status.ready
                for status in self._states.values()
                if status.policy is DependencyPolicy.REQUIRED
            )


class DependencyStartupError(RuntimeError):
    """Clean startup error for dependency failures."""

    def __init__(self, *, dependency: str, operation_name: str, remediation: str) -> None:
        super().__init__(
            f"{dependency} is unavailable during startup {operation_name}. {remediation}"
        )
        self.dependency = dependency
        self.operation_name = operation_name
        self.remediation = remediation


def readiness_payload(registry: DependencyRegistry, *, service_name: str) -> dict[str, object]:
    """Build the readiness response payload from a dependency registry."""
    dependencies = {
        name: {
            "status": status.status,
            "required": status.policy is DependencyPolicy.REQUIRED,
            "hint": status.hint,
        }
        for name, status in registry.snapshot().items()
    }
    ready = registry.ready()
    return {
        "status": "ready" if ready else "not_ready",
        "service": service_name,
        "dependencies": dependencies,
    }
