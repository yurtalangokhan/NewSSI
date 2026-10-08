"""The policy file is the source of truth; code must not drift from it."""

import textwrap

import pytest

from security import (
    get_circuit_breaker,
    load_resilience_config,
    reset_policy_cache,
    retry_policy_for,
)


@pytest.fixture(autouse=True)
def _clean_policy():
    reset_policy_cache()
    yield
    reset_policy_cache()


def _write_policy(tmp_path, body: str):
    path = tmp_path / "resilience.yaml"
    path.write_text(textwrap.dedent(body))
    return str(path)


def test_repository_policy_declares_the_documented_keys() -> None:
    config = load_resilience_config()

    retry = config["defaults"]["retry"]
    breaker = config["defaults"]["circuitBreaker"]
    assert retry["maxAttempts"] >= 1
    assert {"initialSeconds", "multiplier", "maxSeconds"} <= set(retry["backoff"])
    assert {"failureThreshold", "resetTimeoutSeconds"} <= set(breaker)


def test_dependency_overrides_win_over_defaults(tmp_path) -> None:
    path = _write_policy(tmp_path, """
        defaults:
          retry:
            maxAttempts: 3
            backoff: {initialSeconds: 0.2, multiplier: 2.0, maxSeconds: 2.0}
          circuitBreaker: {failureThreshold: 5, resetTimeoutSeconds: 30}
        dependencies:
          keycloak:
            retry:
              maxAttempts: 2
    """)
    load_resilience_config(path)

    assert retry_policy_for("keycloak")["max_attempts"] == 2
    assert retry_policy_for("user-service")["max_attempts"] == 3


def test_partial_backoff_override_keeps_the_sibling_defaults(tmp_path) -> None:
    """A dependency overriding only one backoff field must keep the policy
    file's own defaults for the others -- not the package's hardcoded
    fallback constants. _section's shallow {**defaults, **override} merge
    replaces the whole nested "backoff" dict wholesale the moment the
    override supplies even one of its keys, silently dropping the sibling
    fields the file's own `defaults.retry.backoff` declared.
    """
    path = _write_policy(tmp_path, """
        defaults:
          retry:
            maxAttempts: 3
            backoff: {initialSeconds: 1.0, multiplier: 3.0, maxSeconds: 20.0}
          circuitBreaker: {failureThreshold: 5, resetTimeoutSeconds: 30}
        dependencies:
          slow-dep:
            retry:
              backoff: {maxSeconds: 5.0}
    """)
    load_resilience_config(path)

    result = retry_policy_for("slow-dep")

    assert result["max_backoff"] == 5.0  # the override
    assert result["initial_backoff"] == 1.0  # the file's own default, not the package's 0.2
    assert result["multiplier"] == 3.0  # the file's own default, not the package's 2.0


def test_circuit_breaker_uses_the_dependency_override(tmp_path) -> None:
    path = _write_policy(tmp_path, """
        defaults:
          circuitBreaker: {failureThreshold: 5, resetTimeoutSeconds: 30}
        dependencies:
          rag-service:
            circuitBreaker: {failureThreshold: 2, resetTimeoutSeconds: 7}
    """)
    load_resilience_config(path)

    breaker = get_circuit_breaker("rag-service")
    assert breaker.failure_threshold == 2
    assert breaker.reset_timeout_seconds == 7


def test_breaker_reads_the_policy_even_when_load_was_never_called() -> None:
    """A caller that only asks for a breaker must still get configured values."""
    breaker = get_circuit_breaker("user-service")

    expected = load_resilience_config()["defaults"]["circuitBreaker"]["failureThreshold"]
    assert breaker.failure_threshold == expected


def test_the_same_breaker_instance_is_shared_per_dependency() -> None:
    assert get_circuit_breaker("user-service") is get_circuit_breaker("user-service")


def test_policy_contains_no_scanner_appeasement_keys() -> None:
    """Keys that exist only to match a scanner's regex are not configuration.

    They change no behaviour, drift from the keys the code reads, and turn the
    policy file into a place where the fix is faked rather than made.
    """
    import pathlib

    import yaml

    root = pathlib.Path(__file__).resolve().parents[3]
    raw = yaml.safe_load((root / "configs" / "resilience.yaml").read_text())

    defaults = raw["defaults"]
    assert "maxRetryAttempts" not in defaults["retry"]
    assert "waitDuration" not in defaults["retry"]["backoff"]
    assert "circuitbreaker" not in defaults["circuitBreaker"]
