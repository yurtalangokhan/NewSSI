"""Agent-service binding tests for the shared observability core.

The mechanism tests live in packages/observability/tests; what is asserted here
is this service's own configuration: the service name stamped on records, the
env-backed log format default, and that the binding re-exports the shared core.
"""

from __future__ import annotations

import logging

import pytest


def test_configure_logging_stamps_the_agent_service_name() -> None:
    from core.observability.observability import configure_logging, get_logger

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging(service_name="agent-service", log_level="INFO", log_format="json")

        logger = get_logger("app")

        assert logger.name == "app"
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        formatter = root.handlers[0].formatter
        assert formatter.__class__.__name__ == "JsonFormatter"
        assert formatter._service_name == "agent-service"
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


def test_settings_expose_operator_friendly_log_format(monkeypatch) -> None:
    """The built-in default is human-readable; the central .env may override it."""
    from config_manager import env

    monkeypatch.delenv("LOG_FORMAT", raising=False)
    assert env.LOG_FORMAT == "text"


def test_binding_reexports_the_shared_core() -> None:
    """The service binding is a thin shim over the shared package, not a copy."""
    import observability
    from core.observability import observability as agent_binding
    from core.observability.logger import logger_config

    assert agent_binding.DependencyRegistry is observability.DependencyRegistry
    assert agent_binding.retry_async is observability.retry_async
    assert agent_binding.sanitize_exception is observability.sanitize_exception
    assert isinstance(agent_binding.dependency_registry, observability.DependencyRegistry)
    # The logger binding maps agent env names onto one shared configuration.
    assert logger_config().service_name == "agent-service"


def test_the_historical_dict_entry_point_still_maps_onto_the_one_binding() -> None:
    """The compatibility shim forwards, so there is a single mapping to reason about."""
    import observability
    from core.observability.logger import configure_logging, logger_config

    config = logger_config(overrides={"LOG_LEVEL": "DEBUG", "LOG_FORMAT": "json"})

    assert config.level == "DEBUG"
    assert config.is_json() is True
    assert config.service_name == "agent-service"

    configure_logging({"LOG_LEVEL": "WARNING"})

    assert observability.current_config().level == "WARNING"
    observability.shutdown()


def test_retry_policy_resolves_the_shared_startup_policy() -> None:
    """Startup retries read configs/resilience.yaml through the shared core."""
    from observability import RetryPolicy

    policy = RetryPolicy.for_dependency("postgres")
    assert (policy.attempts, policy.initial_delay_seconds, policy.max_delay_seconds) == (
        5,
        0.5,
        8.0,
    )


@pytest.mark.asyncio
async def test_retry_async_default_policy_comes_from_the_shared_policy() -> None:
    """No explicit policy: the shared startup policy applies, not a hardcoded one."""
    from core.observability.observability import retry_async

    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 5:
            raise ConnectionError("connection refused")
        return "ok"

    result = await retry_async(
        operation,
        operation_name="connect",
        dependency="postgres",
    )

    assert result == "ok"
    assert attempts == 5
