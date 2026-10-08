"""Connector registry with pluggable discovery and runtime visibility.

Registration paths (all can be combined):

* ``@registry.register`` decorator or ``registry.register(cls)``
* ``registry.load_entry_points()`` – discovers third-party connectors that
  declare ``[project.entry-points."connector.sources"]`` /
  ``"connector.destinations"`` in their own ``pyproject.toml``. New connectors
  therefore need no change in this package or in the consuming service.

Visibility is delegated to a :class:`VisibilityPolicy`; the registry itself
only knows *what exists*.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from importlib.metadata import entry_points
from typing import TypeVar, overload

from .base import BaseConnector, BaseDestination, BaseSource
from .errors import (
    ConnectorDisabledError,
    ConnectorError,
    ConnectorNotFoundError,
    DuplicateConnectorError,
)
from .models import ConnectorInfo, ConnectorKind, ConnectorSpec
from .visibility import AllowAllPolicy, RuntimeOverrides, VisibilityPolicy, default_policy

logger = logging.getLogger("connector.registry")

C = TypeVar("C", bound=type[BaseConnector])

SOURCE_ENTRY_POINT_GROUP = "connector.sources"
DESTINATION_ENTRY_POINT_GROUP = "connector.destinations"


class ConnectorRegistry:
    def __init__(
        self,
        policy: VisibilityPolicy | None = None,
        overrides: RuntimeOverrides | None = None,
    ) -> None:
        """``overrides`` is what :meth:`set_enabled` flips at runtime. Without a
        ``policy`` it becomes the first layer of the default one; with a layered
        ``policy`` that already contains a ``RuntimeOverrides`` source, that one
        is found and need not be passed again."""
        self._lock = threading.RLock()
        self._sources: dict[str, type[BaseSource]] = {}
        self._destinations: dict[str, type[BaseDestination]] = {}
        if policy is None:
            policy = (
                default_policy(overrides=overrides) if overrides is not None else AllowAllPolicy()
            )
        elif overrides is None:
            overrides = next(
                (s for s in getattr(policy, "sources", ()) if isinstance(s, RuntimeOverrides)),
                None,
            )
        self.overrides = overrides
        self.policy: VisibilityPolicy = policy

    # ---- registration -----------------------------------------------------

    @overload
    def register(self, cls: C, *, replace: bool = False) -> C: ...

    @overload
    def register(self, cls: None = None, *, replace: bool = False) -> Callable[[C], C]: ...

    def register(self, cls: C | None = None, *, replace: bool = False) -> C | Callable[[C], C]:
        """Register a connector class. Usable as ``registry.register(cls)``,
        ``@registry.register`` or ``@registry.register(replace=True)``."""

        def _do(target: C) -> C:
            self._validate_class(target)
            table = self._table_for(target.kind())
            name = target.name()
            with self._lock:
                if name in table and not replace and table[name] is not target:
                    raise DuplicateConnectorError(name)
                table[name] = target
            return target

        return _do(cls) if cls is not None else _do

    def unregister(self, name: str, kind: ConnectorKind) -> None:
        with self._lock:
            self._table_for(kind).pop(name, None)

    def load_entry_points(self, *, replace: bool = False, strict: bool = False) -> int:
        """Import connectors advertised through package entry points. Returns the number loaded.

        An entry point that cannot be imported or registered (a plugin built for
        another version, a name that is already taken) is logged and skipped: one
        broken plugin must not take the whole catalog down. ``strict=True``
        raises instead, which is what a test of the catalog wants.
        """
        loaded = 0
        for group in (SOURCE_ENTRY_POINT_GROUP, DESTINATION_ENTRY_POINT_GROUP):
            for ep in entry_points(group=group):
                try:
                    self.register(ep.load(), replace=replace)
                except Exception:
                    if strict:
                        raise
                    logger.exception(
                        "connector entry point %s = %s could not be loaded", ep.name, ep.value
                    )
                    continue
                loaded += 1
        return loaded

    # ---- lookup -----------------------------------------------------------

    def get_source(self, name: str, *, allow_hidden: bool = False) -> type[BaseSource]:
        return self._get(name, ConnectorKind.SOURCE, allow_hidden)  # type: ignore[return-value]

    def get_destination(self, name: str, *, allow_hidden: bool = False) -> type[BaseDestination]:
        return self._get(name, ConnectorKind.DESTINATION, allow_hidden)  # type: ignore[return-value]

    def get(
        self, name: str, kind: ConnectorKind, *, allow_hidden: bool = False
    ) -> type[BaseConnector]:
        return self._get(name, kind, allow_hidden)

    def list(
        self, kind: ConnectorKind | None = None, *, include_hidden: bool = False
    ) -> list[ConnectorInfo]:
        """Catalog entries with the current visibility verdict applied."""
        infos: list[ConnectorInfo] = []
        for cls in self._iter(kind):
            verdict = self.policy.evaluate(cls.definition)
            if not verdict.visible and not include_hidden:
                continue
            infos.append(
                ConnectorInfo(
                    **cls.definition.model_dump(),
                    is_available=verdict.visible,
                    unavailable_reason=verdict.reason,
                    has_icon=_has_icon(cls),
                )
            )
        return sorted(infos, key=lambda i: (i.kind.value, i.display_name.lower()))

    def spec(self, name: str, kind: ConnectorKind, *, allow_hidden: bool = False) -> ConnectorSpec:
        return self._get(name, kind, allow_hidden).spec()

    def icon(self, name: str, kind: ConnectorKind, *, allow_hidden: bool = False) -> str | None:
        """SVG markup for a connector (serve with ``image/svg+xml``), or ``None``."""
        return self._get(name, kind, allow_hidden).icon_svg()

    def is_visible(self, name: str, kind: ConnectorKind) -> bool:
        cls = self._lookup(name, kind)
        return self.policy.evaluate(cls.definition).visible

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._sources or name in self._destinations

    def __len__(self) -> int:
        with self._lock:
            return len(self._sources) + len(self._destinations)

    # ---- runtime visibility helpers ----------------------------------------

    def set_enabled(self, name: str, enabled: bool) -> None:
        """Flip a connector at runtime. Requires ``overrides`` to be configured."""
        if self.overrides is None:
            raise ConnectorError("registry has no RuntimeOverrides; pass overrides=...")
        self.overrides.set_enabled(name, enabled)

    # ---- internals --------------------------------------------------------

    def _get(self, name: str, kind: ConnectorKind, allow_hidden: bool) -> type[BaseConnector]:
        cls = self._lookup(name, kind)
        if not allow_hidden:
            verdict = self.policy.evaluate(cls.definition)
            if not verdict.visible:
                raise ConnectorDisabledError(name, verdict.reason)
        return cls

    def _lookup(self, name: str, kind: ConnectorKind) -> type[BaseConnector]:
        with self._lock:
            cls = self._table_for(kind).get(name)
        if cls is None:
            raise ConnectorNotFoundError(name, kind.value)
        return cls

    def _iter(self, kind: ConnectorKind | None) -> Iterator[type[BaseConnector]]:
        with self._lock:
            if kind in (None, ConnectorKind.SOURCE):
                yield from list(self._sources.values())
            if kind in (None, ConnectorKind.DESTINATION):
                yield from list(self._destinations.values())

    def _table_for(self, kind: ConnectorKind) -> dict[str, type[BaseConnector]]:
        return self._sources if kind is ConnectorKind.SOURCE else self._destinations  # type: ignore[return-value]

    @staticmethod
    def _validate_class(cls: type) -> None:
        if not isinstance(cls, type) or not issubclass(cls, BaseConnector):
            raise TypeError(f"{cls!r} is not a BaseConnector subclass")
        if "definition" not in vars(cls) and not hasattr(cls, "definition"):
            raise TypeError(f"{cls.__name__} must define a `definition` class attribute")
        kind = cls.definition.kind
        if kind is ConnectorKind.SOURCE and not issubclass(cls, BaseSource):
            raise TypeError(f"{cls.__name__} declares kind=source but is not a BaseSource")
        if kind is ConnectorKind.DESTINATION and not issubclass(cls, BaseDestination):
            raise TypeError(
                f"{cls.__name__} declares kind=destination but is not a BaseDestination"
            )


def _has_icon(cls: type[BaseConnector]) -> bool:
    """True when the connector bundles an icon or overrides ``icon_svg``."""
    if cls.definition.icon:
        return True
    return cls.icon_svg.__func__ is not BaseConnector.icon_svg.__func__  # type: ignore[attr-defined]


# A process-wide default registry for services that want a single catalog.
default_registry = ConnectorRegistry(overrides=RuntimeOverrides())
