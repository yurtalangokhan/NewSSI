"""Optional dependencies.

Drivers are imported where they are first needed, never at module import, so
the catalog loads with the core dependencies alone. :func:`require_extra` is
the one place that turns a missing driver into a readable error.
"""

from __future__ import annotations

import importlib
from typing import Any

from .errors import MissingExtraError


def optional_module(module: str) -> Any | None:
    """Import ``module`` if it is installed, else ``None``. For code that has a fallback."""
    try:
        return importlib.import_module(module)
    except ImportError:
        return None


def require_extra(module: str, *, extra: str, feature: str | None = None) -> Any:
    """Import ``module``, or raise :class:`MissingExtraError` naming the extra to install.

    ``feature`` is what the caller was trying to do ("postgres source"); it
    defaults to the extra's name.
    """
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise MissingExtraError(feature or f"'{extra}' support", extra) from exc
