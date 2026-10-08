"""Compatibility shim for the historical agent-service logger entry point.

The service's real binding is :mod:`core.observability.observability`. This
module stays because ``core/__init__`` and ``core/observability/__init__`` re-export
from here, and because an embedding script may still pass a config dict. It
forwards to the one binding rather than configuring logging a second way.
"""

from __future__ import annotations

import logging
from typing import Any

from observability import configure, get_logger as _package_get_logger, is_configured

from core.observability.observability import logger_config

__all__ = ["configure_logging", "get_logger", "logger_config"]


def configure_logging(config: dict[str, Any] | None = None) -> None:
    """Configure logging from a config dict keyed by this service's env names.

    Accepted keys are the ones the service already used: ``SERVICE_NAME``,
    ``LOG_LEVEL``, ``LOG_FORMAT``, ``LOG_OUTPUT``, ``LOG_FILE_PATH``,
    ``LOG_MAX_SIZE``, and ``LOG_BACKUP_COUNT``. Anything absent falls back to the
    environment; the binding owns that mapping, so this shim does not restate it.
    """
    configure(logger_config(overrides=config or {}))


def get_logger(name: str, extra_context: dict[str, Any] | None = None) -> logging.Logger:
    """Return a logger, configuring from the environment on first use.

    A module is imported before the application configures logging, so the first
    call configures the service rather than dropping the records written before
    startup finished.
    """
    if not is_configured():
        configure_logging()
    return _package_get_logger(name, extra_context)
