"""Shared environment configuration for the Agentic AI services.

Importing this package has no side effects: ``load_environment`` is exposed
from :mod:`config_manager.manager` without running it. The accessor attributes
(``env``, ``ConfigManager``) load the central file on first access.
"""

from .manager import load_environment

__all__ = [
    "DEFAULT_ALLOWED_ORIGIN",
    "ConfigManager",
    "env",
    "load_environment",
    "parse_allowed_origins",
]


def __getattr__(name: str):
    if name in {
        "DEFAULT_ALLOWED_ORIGIN",
        "ConfigManager",
        "env",
        "parse_allowed_origins",
    }:
        from . import accessor

        return getattr(accessor, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
