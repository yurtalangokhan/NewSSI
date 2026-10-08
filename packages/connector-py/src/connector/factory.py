"""How the sync runner obtains the connectors of a connection.

The runner only needs "the source and the destination of this connection, ready
to use". Where their classes and configurations come from is the host's
business: the default looks the class up in a registry and validates the
configuration stored on the connection, but a host may resolve secrets at that
moment, hand connectors a shared HTTP client, or return test doubles.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .base import BaseDestination, BaseSource
from .models import Connection
from .registry import ConnectorRegistry


@runtime_checkable
class ConnectorFactory(Protocol):
    """Builds the connectors of one sync run. Called once per job, when it starts running."""

    async def source(self, connection: Connection) -> BaseSource[Any]: ...

    async def destination(self, connection: Connection) -> BaseDestination[Any]: ...


class RegistryConnectorFactory:
    """Class from the registry, configuration from the connection."""

    def __init__(self, registry: ConnectorRegistry, *, allow_hidden: bool = False) -> None:
        self.registry = registry
        self.allow_hidden = allow_hidden

    async def source(self, connection: Connection) -> BaseSource[Any]:
        cls = self.registry.get_source(connection.source_name, allow_hidden=self.allow_hidden)
        return cls.from_config(connection.source_config)

    async def destination(self, connection: Connection) -> BaseDestination[Any]:
        cls = self.registry.get_destination(
            connection.destination_name, allow_hidden=self.allow_hidden
        )
        return cls.from_config(connection.destination_config)
