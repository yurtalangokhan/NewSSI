"""The metrics half of the service contract must fail closed.

A service that drops the idempotency series from its exposition must fail the
contract check, not silently pass because the rule list drifted. These tests
drive ``check()`` directly with a minimal spec, so they stay valid regardless
of which service is loaded.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "governance"))

from check_service_contract import REQUIRED_METRICS, check  # noqa: E402

_SPEC = {
    "info": {"title": "t", "description": "d", "version": "1"},
    "paths": {},
}

_METRICS_WITH_SERIES = "\n".join(
    f"# HELP {m} help\n# TYPE {m} counter\n{m}{{service=\"s\",route=\"/r\",outcome=\"executed\"}} 1\n"
    for m in REQUIRED_METRICS.values()
)


def _results(metrics_body: str) -> dict:
    return check(_SPEC, metrics_body, "text/plain", 200)


def test_contract_fails_when_the_idempotency_series_are_absent() -> None:
    results = _results("")

    for rule, metric in REQUIRED_METRICS.items():
        if not metric.startswith("idempotency_"):
            continue
        ok, detail = results[f"{rule} {metric}"]
        assert ok is False, f"{metric} missing from the exposition must fail {rule}"
        assert detail == metric


def test_contract_passes_when_the_idempotency_series_are_present() -> None:
    results = _results(_METRICS_WITH_SERIES)

    for rule, metric in REQUIRED_METRICS.items():
        ok, _ = results[f"{rule} {metric}"]
        assert ok is True, f"{metric} is exported but {rule} failed"
