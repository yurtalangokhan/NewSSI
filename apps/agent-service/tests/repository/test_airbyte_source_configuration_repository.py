import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

SOURCE_ID = "92e8139c-cf1a-4ad5-b62b-89df7f957f43"


class FakeConnection:
    def __init__(self, configuration):
        self.configuration = configuration
        self.fetchrow = AsyncMock(return_value={"configuration": configuration})
        self.fetchval = AsyncMock(return_value="resolved-secret")
        self.closed = False

    @asynccontextmanager
    async def transaction(self, *, readonly=False):
        assert readonly is True
        yield

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_reads_complete_source_configuration_in_none_mode():
    from repository.airbyte_source_configuration_repository import (
        AirbyteSourceConfigurationRepository,
    )

    connection = FakeConnection(json.dumps({"host": "db", "password": "stored-secret"}))
    connect = AsyncMock(return_value=connection)
    repository = AirbyteSourceConfigurationRepository(
        "postgresql://airbyte-config-db",
        secret_persistence="NONE",
        connect=connect,
    )

    configuration = await repository.get_source_configuration(SOURCE_ID)

    assert configuration == {"host": "db", "password": "stored-secret"}
    query, source_id = connection.fetchrow.await_args.args
    assert "FROM actor" in query
    assert "actor_type = 'source'" in query
    assert "tombstone = FALSE" in query
    assert source_id == SOURCE_ID
    assert connection.fetchrow.await_args.kwargs == {"timeout": 4.0}
    connect.assert_awaited_once_with(
        "postgresql://airbyte-config-db",
        user=None,
        password=None,
        timeout=4.0,
    )
    assert connection.closed is True


@pytest.mark.asyncio
async def test_returns_none_when_saved_source_does_not_exist():
    from repository.airbyte_source_configuration_repository import (
        AirbyteSourceConfigurationRepository,
    )

    connection = FakeConnection(None)
    connection.fetchrow.return_value = None
    repository = AirbyteSourceConfigurationRepository(
        "postgresql://airbyte-config-db",
        secret_persistence="NONE",
        connect=AsyncMock(return_value=connection),
    )

    assert await repository.get_source_configuration(SOURCE_ID) is None
    assert connection.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["VAULT", "AWS_SECRET_MANAGER", "", None])
async def test_rejects_modes_whose_secrets_cannot_be_hydrated_from_actor(mode):
    from repository.airbyte_source_configuration_repository import (
        AirbyteConfigurationUnavailable,
        AirbyteSourceConfigurationRepository,
    )

    connect = AsyncMock()
    repository = AirbyteSourceConfigurationRepository(
        "postgresql://airbyte-config-db",
        secret_persistence=mode,
        connect=connect,
    )

    with pytest.raises(AirbyteConfigurationUnavailable, match="SECRET_PERSISTENCE=NONE"):
        await repository.get_source_configuration(SOURCE_ID)
    connect.assert_not_awaited()


def test_factory_requires_dedicated_airbyte_database_url(monkeypatch):
    from repository.airbyte_source_configuration_repository import (
        AirbyteConfigurationUnavailable,
        get_airbyte_source_configuration_repository,
    )

    monkeypatch.delenv("AIRBYTE_CONFIG_DATABASE_URL", raising=False)
    monkeypatch.setenv("AIRBYTE_SECRET_PERSISTENCE", "NONE")

    with pytest.raises(AirbyteConfigurationUnavailable, match="database URL"):
        get_airbyte_source_configuration_repository()


def test_factory_reads_dedicated_credentials_from_central_env(monkeypatch):
    from repository.airbyte_source_configuration_repository import (
        get_airbyte_source_configuration_repository,
    )

    monkeypatch.setenv("AIRBYTE_CONFIG_DATABASE_URL", "jdbc:postgresql://postgres/airbyte")
    monkeypatch.setenv("AIRBYTE_CONFIG_DATABASE_USER", "airbyte-user")
    monkeypatch.setenv("AIRBYTE_CONFIG_DATABASE_PASSWORD", "test-password")
    monkeypatch.setenv("AIRBYTE_SECRET_PERSISTENCE", "NONE")

    repository = get_airbyte_source_configuration_repository()

    assert repository._database_url == "jdbc:postgresql://postgres/airbyte"
    assert repository._database_user == "airbyte-user"
    assert repository._database_password == "test-password"


@pytest.mark.asyncio
async def test_invalid_database_json_raises_safe_error_without_content():
    from repository.airbyte_source_configuration_repository import (
        AirbyteConfigurationUnavailable,
        AirbyteSourceConfigurationRepository,
    )

    raw_value = '{"password":"must-not-escape"'
    connection = FakeConnection(raw_value)
    repository = AirbyteSourceConfigurationRepository(
        "postgresql://airbyte-config-db",
        secret_persistence="NONE",
        connect=AsyncMock(return_value=connection),
    )

    with pytest.raises(AirbyteConfigurationUnavailable) as error:
        await repository.get_source_configuration(SOURCE_ID)
    assert "must-not-escape" not in str(error.value)


@pytest.mark.asyncio
async def test_resolves_nested_local_secret_references_without_decoding_payload():
    from repository.airbyte_source_configuration_repository import (
        AirbyteSourceConfigurationRepository,
    )

    connection = FakeConnection(
        {"password": {"_secret": "coordinate"}, "nested": [{"token": {"_secret": "coordinate"}}]}
    )
    connection.fetchval.return_value = '"literal-password"'
    repo = AirbyteSourceConfigurationRepository(
        "postgresql://config", secret_persistence="NONE", connect=AsyncMock(return_value=connection)
    )
    result = await repo.get_source_configuration(SOURCE_ID)
    assert result == {"password": '"literal-password"', "nested": [{"token": '"literal-password"'}]}
    assert connection.closed
    assert connection.fetchval.await_args.args[1] == "coordinate"


@pytest.mark.asyncio
async def test_missing_secret_fails_safely_and_closes_connection():
    from repository.airbyte_source_configuration_repository import (
        AirbyteConfigurationUnavailable,
        AirbyteSourceConfigurationRepository,
    )

    connection = FakeConnection({"password": {"_secret": "private-coordinate"}})
    connection.fetchval.return_value = None
    repo = AirbyteSourceConfigurationRepository(
        "postgresql://config", secret_persistence="NONE", connect=AsyncMock(return_value=connection)
    )
    with pytest.raises(AirbyteConfigurationUnavailable) as error:
        await repo.get_source_configuration(SOURCE_ID)
    assert "private-coordinate" not in str(error.value)
    assert connection.closed
