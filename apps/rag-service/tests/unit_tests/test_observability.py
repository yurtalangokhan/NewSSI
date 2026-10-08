"""Rag-service binding tests for the shared observability core.

The mechanism tests live in packages/observability/tests; what is asserted here
is this service's own configuration: the service name stamped on records and
that the binding re-exports the shared core.
"""

from __future__ import annotations

import logging


def test_configure_logging_stamps_the_rag_service_name() -> None:
    from src.shared.observability import configure_logging, get_logger

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging(
            service_name="rag-service", log_level="INFO", log_format="json"
        )

        logger = get_logger("src.server")

        assert logger.name == "src.server"
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        formatter = root.handlers[0].formatter
        assert formatter.__class__.__name__ == "JsonFormatter"
        assert formatter._service_name == "rag-service"
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


def test_binding_reexports_the_shared_core() -> None:
    """The service binding is a thin shim over the shared package, not a copy."""
    import observability

    from src.shared import observability as rag_binding

    assert rag_binding.DependencyRegistry is observability.DependencyRegistry
    assert rag_binding.retry_async is observability.retry_async
    assert rag_binding.sanitize_exception is observability.sanitize_exception
    assert isinstance(rag_binding.dependency_registry, observability.DependencyRegistry)
