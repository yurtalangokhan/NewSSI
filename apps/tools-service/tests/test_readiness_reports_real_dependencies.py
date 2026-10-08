"""Readiness must reflect something that was actually checked.

`dependency_registry` had no producer anywhere in the service: nothing ever
called record_ok or record_degraded, so `readiness_payload` reported
"ready" over an empty dependency map. An orchestrator watching that endpoint
would route traffic to an instance whose dependencies had never been probed —
a green light that means nothing.
"""

from __future__ import annotations

import pytest

from src.core.observability import (
    DependencyPolicy,
    dependency_registry,
    readiness_payload,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    dependency_registry._states.clear()
    yield
    dependency_registry._states.clear()


def test_an_unprobed_service_is_not_reported_as_ready():
    payload = readiness_payload(service_name="tools-service")

    assert payload["dependencies"] == {}
    assert payload["status"] == "not_ready"


def test_a_recorded_dependency_shows_up():
    dependency_registry.record_ok("tool-registry", policy=DependencyPolicy.REQUIRED)

    payload = readiness_payload(service_name="tools-service")

    assert payload["dependencies"]["tool-registry"]["status"] == "ok"
    assert payload["status"] == "ready"


def test_a_degraded_required_dependency_keeps_the_service_out_of_rotation():
    dependency_registry.record_ok("tool-registry", policy=DependencyPolicy.REQUIRED)
    dependency_registry.record_degraded("redis", hint="connection refused")

    payload = readiness_payload(service_name="tools-service")

    assert payload["dependencies"]["redis"]["hint"] == "connection refused"
