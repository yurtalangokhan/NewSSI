"""ensure_database_exists bootstraps the service role and database like the other services."""

from __future__ import annotations

import pytest


class FakeSettings:
    def __init__(self, admin_user, admin_password):
        self.POSTGRES_ADMIN_USER = admin_user
        self.POSTGRES_ADMIN_PASSWORD = admin_password

    @property
    def tool_postgres_config(self):
        return {
            "user": "tools_service",
            "password": "to'ols",
            "host": "localhost",
            "port": 8124,
            "database": "tools_service",
        }


class FakeConnection:
    def __init__(self, existing_roles, existing_databases, statements):
        self.existing_roles = existing_roles
        self.existing_databases = existing_databases
        self.statements = statements
        self.closed = False

    async def fetchval(self, query, *args):
        if "pg_roles" in query:
            return 1 if args[0] in self.existing_roles else None
        if "pg_database" in query:
            return 1 if args[0] in self.existing_databases else None
        raise AssertionError(query)

    async def execute(self, statement):
        self.statements.append(statement)

    async def close(self):
        self.closed = True


class FakeAsyncpg:
    def __init__(self, existing_roles=(), existing_databases=()):
        self.connections = []
        self.statements = []
        self.existing_roles = set(existing_roles)
        self.existing_databases = set(existing_databases)

    async def connect(self, **kwargs):
        self.connections.append(kwargs)
        connection = FakeConnection(self.existing_roles, self.existing_databases, self.statements)
        self.last_connection = connection
        return connection


async def run(monkeypatch, settings, asyncpg):
    from src.core import database

    monkeypatch.setattr(database, "env", settings)
    monkeypatch.setattr(database, "asyncpg", asyncpg)
    await database.ensure_database_exists()
    assert asyncpg.last_connection.closed
    return asyncpg


@pytest.mark.asyncio
async def test_admin_credentials_create_the_role_and_its_database(monkeypatch):
    asyncpg = await run(monkeypatch, FakeSettings("admin", "adm'in"), FakeAsyncpg())

    assert asyncpg.connections == [
        {
            "user": "admin",
            "password": "adm'in",
            "host": "localhost",
            "port": 8124,
            "database": "postgres",
            "timeout": 5,
        }
    ]
    assert asyncpg.statements == [
        """CREATE ROLE "tools_service" LOGIN PASSWORD 'to''ols'""",
        """CREATE DATABASE "tools_service" OWNER "tools_service\"""",
    ]


@pytest.mark.asyncio
async def test_existing_role_gets_the_configured_password_and_the_database_is_kept(monkeypatch):
    asyncpg = await run(
        monkeypatch,
        FakeSettings("admin", "secret"),
        FakeAsyncpg(existing_roles={"tools_service"}, existing_databases={"tools_service"}),
    )

    assert asyncpg.statements == ["""ALTER ROLE "tools_service" LOGIN PASSWORD 'to''ols'"""]


@pytest.mark.asyncio
async def test_without_admin_credentials_the_service_role_creates_its_database(monkeypatch):
    asyncpg = await run(monkeypatch, FakeSettings(None, None), FakeAsyncpg())

    assert asyncpg.connections[0]["user"] == "tools_service"
    assert asyncpg.connections[0]["password"] == "to'ols"
    assert asyncpg.connections[0]["database"] == "postgres"
    assert asyncpg.statements == ['CREATE DATABASE "tools_service"']
