from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from src.connectors.sql import ConnectorSqlError, read_sql_connector


@pytest.mark.asyncio
async def test_mysql_uses_airbyte_config_and_parameterized_equality_filter(monkeypatch):
    calls = {}

    class Cursor:
        async def execute(self, statement, values):
            calls.update(statement=statement, values=values)

        async def fetchall(self):
            return [{"id": 1, "status": "paid"}]

    class Connection:
        @asynccontextmanager
        async def cursor(self, _cursor_type):
            yield Cursor()

        def close(self):
            calls["close_called"] = True

        async def wait_closed(self):
            calls["closed"] = True

    async def connect(**kwargs):
        calls["connect"] = kwargs
        return Connection()

    driver = SimpleNamespace(
        connect=connect,
        cursors=SimpleNamespace(DictCursor=object()),
    )
    monkeypatch.setitem(__import__("sys").modules, "aiomysql", driver)

    rows = await read_sql_connector(
        "source-mysql",
        {
            "host": "mysql",
            "port": 3306,
            "database": "reporting",
            "username": "reader",
            "password": "secret",
            "ssl_mode": {"mode": "preferred"},
        },
        "sales.orders",
        {"status": "paid"},
        25,
    )

    assert rows == [{"id": 1, "status": "paid"}]
    assert calls["statement"] == ("SELECT * FROM `sales`.`orders` WHERE `status` = %s LIMIT %s")
    assert calls["values"] == ("paid", 25)
    assert calls["connect"]["db"] == "reporting"
    assert calls["connect"]["ssl"].verify_mode == __import__("ssl").CERT_NONE
    assert calls["closed"] is True


@pytest.mark.asyncio
async def test_mssql_uses_bounded_query_and_airbyte_ssl_shape(monkeypatch):
    calls = {}

    class Cursor:
        description = [("id",), ("status",)]

        async def execute(self, statement, values):
            calls.update(statement=statement, values=values)

        async def fetchall(self):
            return [(1, "paid")]

    class Connection:
        @asynccontextmanager
        async def cursor(self):
            yield Cursor()

        async def close(self):
            calls["closed"] = True

    async def connect(**kwargs):
        calls["connect"] = kwargs
        return Connection()

    monkeypatch.setitem(__import__("sys").modules, "aioodbc", SimpleNamespace(connect=connect))

    rows = await read_sql_connector(
        "source-mssql",
        {
            "host": "sqlserver",
            "port": 1433,
            "database": "reporting",
            "username": "reader",
            "password": "secret",
            "ssl_method": {"ssl_method": "encrypted_trust_server_certificate"},
        },
        "dbo.orders",
        {"status": "paid"},
        10,
    )

    assert rows == [{"id": 1, "status": "paid"}]
    assert calls["statement"] == ("SELECT TOP (?) * FROM [dbo].[orders] WHERE [status] = ?")
    assert calls["values"] == (10, "paid")
    assert "Encrypt=yes" in calls["connect"]["dsn"]
    assert "TrustServerCertificate=yes" in calls["connect"]["dsn"]
    assert type(calls["connect"]["timeout"]) is int


def test_mssql_escapes_saved_odbc_values():
    from src.connectors.sql import _mssql_dsn

    dsn = _mssql_dsn(
        {
            "host": "sqlserver",
            "database": "reporting",
            "username": "reader",
            "password": "secret;}value",
        }
    )
    assert "PWD={secret;}}value}" in dsn


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("connection_data", "dsn_kwargs"),
    [
        (
            {"connection_type": "service_name", "service_name": "FREEPDB1"},
            {"service_name": "FREEPDB1"},
        ),
        ({"connection_type": "sid", "sid": "XE"}, {"sid": "XE"}),
    ],
)
async def test_oracle_supports_airbyte_service_name_and_sid(
    monkeypatch, connection_data, dsn_kwargs
):
    calls = {}

    class Cursor:
        description = [("ID",), ("STATUS",)]

        async def execute(self, statement, values):
            calls.update(statement=statement, values=values)

        async def fetchall(self):
            return [(1, "paid")]

    class Connection:
        @asynccontextmanager
        async def cursor(self):
            yield Cursor()

        async def close(self):
            calls["closed"] = True

    def makedsn(host, port, **kwargs):
        calls["makedsn"] = (host, port, kwargs)
        return "oracle-dsn"

    async def connect_async(**kwargs):
        calls["connect"] = kwargs
        return Connection()

    monkeypatch.setitem(
        __import__("sys").modules,
        "oracledb",
        SimpleNamespace(makedsn=makedsn, connect_async=connect_async),
    )

    rows = await read_sql_connector(
        "source-oracle",
        {
            "host": "oracle",
            "port": 1521,
            "connection_data": connection_data,
            "username": "reader",
            "password": "secret",
            "encryption": {"encryption_method": "unencrypted"},
        },
        "SALES.ORDERS",
        {"STATUS": "paid"},
        5,
    )

    assert rows == [{"ID": 1, "STATUS": "paid"}]
    assert calls["statement"] == (
        'SELECT * FROM "SALES"."ORDERS" WHERE "STATUS" = :1 FETCH FIRST :2 ROWS ONLY'
    )
    assert calls["values"] == ("paid", 5)
    assert calls["makedsn"] == ("oracle", 1521, dsn_kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("connector_type", "config"),
    [
        ("source-mysql", {"ssl_mode": {"mode": "verify_identity"}}),
        ("source-mssql", {"ssl_method": {"ssl_method": "encrypted_verify_certificate"}}),
        ("source-oracle", {"encryption": {"encryption_method": "client_nne"}}),
    ],
)
async def test_incompatible_security_modes_fail_closed(connector_type, config):
    complete = {
        "host": "db",
        "database": "reporting",
        "username": "reader",
        "password": "secret",
        **config,
    }
    if connector_type == "source-oracle":
        complete["connection_data"] = {
            "connection_type": "service_name",
            "service_name": "FREEPDB1",
        }

    with pytest.raises(ConnectorSqlError, match="not supported"):
        await read_sql_connector(connector_type, complete, "sales.orders", {}, 10)


@pytest.mark.asyncio
async def test_rejects_invalid_identifiers_and_non_scalar_filters():
    with pytest.raises(ConnectorSqlError, match="identifier"):
        await read_sql_connector("source-mysql", {}, "orders; DROP TABLE users", {}, 10)
    with pytest.raises(ConnectorSqlError, match="scalar"):
        await read_sql_connector("source-mysql", {}, "orders", {"id": [1]}, 10)


@pytest.mark.asyncio
async def test_mysql_required_tls_rejected_before_driver_connection(monkeypatch):
    async def connect(**kwargs):
        pytest.fail("required mode must never enter a driver which can silently downgrade")

    monkeypatch.setitem(__import__("sys").modules, "aiomysql", SimpleNamespace(connect=connect))
    with pytest.raises(ConnectorSqlError, match="not supported"):
        await read_sql_connector(
            "source-mysql",
            {
                "host": "db",
                "database": "reporting",
                "username": "reader",
                "password": "secret",
                "ssl_mode": {"mode": "required"},
            },
            "orders",
            {},
            10,
        )
