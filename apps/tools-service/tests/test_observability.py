"""Tools-service binding tests for the shared observability core.

The mechanism tests live in packages/observability/tests; what is asserted here
is this service's own configuration: the service name stamped on records and
that the binding re-exports the shared core.
"""

from __future__ import annotations

import logging


def test_configure_logging_stamps_the_tools_service_name() -> None:
    from core.observability import configure_logging, get_logger

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging(service_name="tools-service", log_level="INFO", log_format="json")

        logger = get_logger("core.registry")

        assert logger.name == "core.registry"
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        formatter = root.handlers[0].formatter
        assert formatter.__class__.__name__ == "JsonFormatter"
        assert formatter._service_name == "tools-service"
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


def test_binding_reexports_the_shared_core() -> None:
    """The service binding is a thin shim over the shared package, not a copy."""
    import observability

    from core import observability as tools_binding

    assert tools_binding.DependencyRegistry is observability.DependencyRegistry
    assert tools_binding.retry_async is observability.retry_async
    assert tools_binding.sanitize_exception is observability.sanitize_exception
    assert isinstance(tools_binding.dependency_registry, observability.DependencyRegistry)
