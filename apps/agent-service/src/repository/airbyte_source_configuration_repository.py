"""Read complete Airbyte source configuration for local NONE secret persistence."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import UUID

import asyncpg

from core.env import env


class AirbyteConfigurationUnavailable(RuntimeError):
    """Raised when complete Airbyte source configuration cannot be read safely."""


_SOURCE_CONFIGURATION_QUERY = """
SELECT configuration
FROM actor
WHERE id = $1::uuid
  AND actor_type = 'source'
  AND tombstone = FALSE
"""


def _asyncpg_dsn(database_url: str) -> str:
    return database_url.removeprefix("jdbc:")


class AirbyteSourceConfigurationRepository:
    """Read source JSON directly from the Airbyte 0.50.x config database.

    This path is valid only with ``SECRET_PERSISTENCE=NONE``. In that mode
    Airbyte stores configuration in ``actor.configuration`` and may store local
    secret payloads in ``secrets``; API responses mask secret fields for presentation.
    """

    def __init__(
        self,
        database_url: str,
        *,
        database_user: str | None = None,
        database_password: str | None = None,
        secret_persistence: str | None,
        timeout_seconds: float = 4.0,
        connect: Callable[..., Awaitable[Any]] = asyncpg.connect,
    ) -> None:
        self._database_url = database_url
        self._database_user = database_user
        self._database_password = database_password
        self._secret_persistence = (secret_persistence or "").strip().upper()
        self._timeout_seconds = timeout_seconds
        self._connect = connect

    async def _resolve_secrets(self, connection: Any, value: Any) -> Any:
        if isinstance(value, dict):
            if "_secret" in value:
                coordinate = value["_secret"]
                if not isinstance(coordinate, str) or not coordinate or len(value) != 1:
                    raise AirbyteConfigurationUnavailable("Invalid saved secret reference.")
                payload = await connection.fetchval(
                    "SELECT payload FROM secrets WHERE coordinate = $1",
                    coordinate,
                    timeout=self._timeout_seconds,
                )
                if not isinstance(payload, str):
                    raise AirbyteConfigurationUnavailable("Saved connector secret is unavailable.")
                return payload
            return {
                key: await self._resolve_secrets(connection, item) for key, item in value.items()
            }
        if isinstance(value, list):
            return [await self._resolve_secrets(connection, item) for item in value]
        return value

    async def get_source_configuration(self, source_id: str) -> dict[str, Any] | None:
        if self._secret_persistence != "NONE":
            raise AirbyteConfigurationUnavailable(
                "Complete saved connector configuration is supported only with "
                "AIRBYTE_SECRET_PERSISTENCE=NONE."
            )
        try:
            UUID(source_id)
        except (TypeError, ValueError):
            raise AirbyteConfigurationUnavailable(
                "The saved Airbyte source ID is invalid."
            ) from None

        connection = None
        try:
            connection = await self._connect(
                _asyncpg_dsn(self._database_url),
                user=self._database_user,
                password=self._database_password,
                timeout=self._timeout_seconds,
            )
            async with connection.transaction(readonly=True):
                row = await connection.fetchrow(
                    _SOURCE_CONFIGURATION_QUERY,
                    source_id,
                    timeout=self._timeout_seconds,
                )
                if row is None:
                    return None
                value = row["configuration"]
                if isinstance(value, str):
                    value = json.loads(value)
                if not isinstance(value, Mapping):
                    raise AirbyteConfigurationUnavailable(
                        "The saved Airbyte source configuration has an invalid format."
                    )
                return await self._resolve_secrets(connection, dict(value))
        except AirbyteConfigurationUnavailable:
            raise
        except Exception:
            raise AirbyteConfigurationUnavailable(
                "The saved Airbyte source configuration could not be read."
            ) from None
        finally:
            if connection is not None:
                try:
                    await connection.close()
                except Exception:
                    pass


def get_airbyte_source_configuration_repository() -> AirbyteSourceConfigurationRepository:
    database_url = (env.get("AIRBYTE_CONFIG_DATABASE_URL") or "").strip()
    if not database_url:
        raise AirbyteConfigurationUnavailable(
            "AIRBYTE_CONFIG_DATABASE_URL must provide the Airbyte config database URL."
        )
    return AirbyteSourceConfigurationRepository(
        database_url,
        database_user=env.get("AIRBYTE_CONFIG_DATABASE_USER"),
        database_password=env.get("AIRBYTE_CONFIG_DATABASE_PASSWORD"),
        secret_persistence=env.get("AIRBYTE_SECRET_PERSISTENCE"),
    )
