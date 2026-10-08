"""User-service binding tests for the shared observability core.

The mechanism tests live in packages/observability/tests; what is asserted here
is this service's own configuration: the service name stamped on records, the
quieted HTTP client loggers, app wiring, and pseudonymised identifiers.
"""

from __future__ import annotations

import logging


def test_configure_logging_stamps_the_user_service_name() -> None:
    from src.core.observability import configure_logging, get_logger

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging(service_name="user-service", log_level="INFO", log_format="json")

        logger = get_logger("src.main")

        assert logger.name == "src.main"
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        formatter = root.handlers[0].formatter
        assert formatter.__class__.__name__ == "JsonFormatter"
        assert formatter._service_name == "user-service"
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


def test_configure_logging_quiets_http_client_access_logs() -> None:
    from src.core.observability import configure_logging

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_httpx_level = logging.getLogger("httpx").level
    original_httpcore_level = logging.getLogger("httpcore").level
    try:
        configure_logging(service_name="user-service", log_level="INFO")

        assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
        assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)
        logging.getLogger("httpx").setLevel(original_httpx_level)
        logging.getLogger("httpcore").setLevel(original_httpcore_level)


def test_create_app_configures_service_logging(monkeypatch) -> None:
    from src import main

    calls: list[dict[str, str]] = []

    def fake_configure_logging(**kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(main, "configure_logging", fake_configure_logging, raising=False)

    main.create_app()

    assert calls == [
        {
            "service_name": "user-service",
            "log_level": main.env.LOG_LEVEL,
        }
    ]


def test_pseudonym_is_stable_and_not_reversible_from_the_log() -> None:
    from src.core.observability import pseudonym

    assert pseudonym("Ada.Yilmaz@Example.COM ") == pseudonym("ada.yilmaz@example.com")
    assert pseudonym(None) == "anonymous"
    assert pseudonym("") == "anonymous"
    value = pseudonym("ada.yilmaz@example.com")
    assert value.startswith("user:")
    assert "ada" not in value


def test_binding_reexports_the_shared_core() -> None:
    """The service binding is a thin shim over the shared package, not a copy."""
    import observability

    from src.core import observability as user_binding

    assert user_binding.DependencyRegistry is observability.DependencyRegistry
    assert user_binding.retry_async is observability.retry_async
    assert user_binding.sanitize_exception is observability.sanitize_exception
    assert isinstance(user_binding.dependency_registry, observability.DependencyRegistry)
