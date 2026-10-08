"""Bounded structured reads for saved MySQL, SQL Server, and Oracle sources."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import inspect
import re
import ssl
from typing import Any

from error_contract.connectors import (
    ConnectorSqlConfigurationError,
    ConnectorSqlError,
    ConnectorSqlValidationError,
)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")
_MAX_FILTER_FIELDS = 10
_MAX_LIMIT = 100
_CONNECT_TIMEOUT_SECONDS = 5.0
_QUERY_TIMEOUT_SECONDS = 10.0


def _parts(resource: str) -> list[str]:
    parts = resource.split(".")
    if len(parts) not in {1, 2} or any(not _IDENTIFIER.fullmatch(part) for part in parts):
        raise ConnectorSqlValidationError("Resource contains an invalid identifier.")
    return parts


def _filter_items(row_filter: Mapping[str, Any]) -> list[tuple[str, Any]]:
    if len(row_filter) > _MAX_FILTER_FIELDS:
        raise ConnectorSqlValidationError("Filter supports at most 10 fields.")
    result = []
    for field, value in row_filter.items():
        if not _IDENTIFIER.fullmatch(field):
            raise ConnectorSqlValidationError("Filter contains an invalid identifier.")
        if isinstance(value, dict | list | tuple | set):
            raise ConnectorSqlValidationError("Filter values must be scalar.")
        result.append((field, value))
    return result


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConnectorSqlValidationError("Limit must be an integer.")
    return min(max(value, 1), _MAX_LIMIT)


def _required(config: Mapping[str, Any], key: str, *aliases: str) -> Any:
    value = next((config.get(name) for name in (key, *aliases) if config.get(name) is not None), None)
    if value is None or value == "":
        raise ConnectorSqlConfigurationError("Connector configuration is incomplete.")
    return value


async def _close(connection: Any, method: str = "close") -> None:
    try:
        result = getattr(connection, method)()
        if inspect.isawaitable(result):
            await result
    # Best-effort driver cleanup must not replace the primary error, and a
    # failed close() of a dying connection is not worth a log line.
    except Exception:  # noqa: S110
        pass


async def _read_mysql(
    config: Mapping[str, Any], resource: str, row_filter: Mapping[str, Any], limit: int
) -> list[dict[str, Any]]:
    table = ".".join(f"`{part}`" for part in _parts(resource))
    items = _filter_items(row_filter)
    mode = (config.get("ssl_mode") or {}).get("mode", "preferred")
    if mode != "preferred":
        raise ConnectorSqlConfigurationError("This MySQL SSL mode is not supported for live reads.")
    import aiomysql

    connect_args: dict[str, Any] = {
        "host": _required(config, "host"),
        "port": int(config.get("port", 3306)),
        "user": _required(config, "username", "user"),
        "password": _required(config, "password"),
        "db": _required(config, "database"),
        "connect_timeout": _CONNECT_TIMEOUT_SECONDS,
    }
    # aiomysql falls back before authentication when the server lacks TLS.
    # This matches preferred only; required must fail before entering the driver.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = context
    predicates = [f"`{field}` = %s" for field, _value in items]
    where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
    # Identifiers are regex-validated by _parts/_filter_items; values are bound
    # parameters, so the f-string only carries vetted identifiers.
    statement = f"SELECT * FROM {table}{where} LIMIT %s"  # noqa: S608
    values = (*[value for _field, value in items], _limit(limit))
    connection = None
    try:
        connection = await aiomysql.connect(**connect_args)
        async with connection.cursor(aiomysql.cursors.DictCursor) as cursor:
            await asyncio.wait_for(cursor.execute(statement, values), timeout=_QUERY_TIMEOUT_SECONDS)
            rows = await asyncio.wait_for(cursor.fetchall(), timeout=_QUERY_TIMEOUT_SECONDS)
        return [dict(row) for row in rows]
    except ConnectorSqlError:
        raise
    except (aiomysql.Error, TimeoutError, OSError):
        raise ConnectorSqlError("MySQL connector read failed.") from None
    finally:
        if connection is not None:
            await _close(connection)
            if hasattr(connection, "wait_closed"):
                await _close(connection, "wait_closed")


def _mssql_dsn(config: Mapping[str, Any]) -> str:
    method = (config.get("ssl_method") or {}).get("ssl_method", "unencrypted")
    security = {
        "unencrypted": "Encrypt=no",
        "encrypted_trust_server_certificate": "Encrypt=yes;TrustServerCertificate=yes",
    }.get(method)
    if security is None:
        raise ConnectorSqlConfigurationError("This SQL Server SSL mode is not supported for live reads.")
    values = {
        "SERVER": f"{_required(config, 'host')},{int(config.get('port', 1433))}",
        "DATABASE": _required(config, "database"),
        "UID": _required(config, "username", "user"),
        "PWD": _required(config, "password"),
    }
    fields = ["DRIVER={FreeTDS}", "TDS_Version=7.4"]
    fields.extend(key + "={" + value.replace("}", "}}") + "}" for key, value in values.items())
    fields.append(security)
    return ";".join(fields)


async def _read_mssql(
    config: Mapping[str, Any], resource: str, row_filter: Mapping[str, Any], limit: int
) -> list[dict[str, Any]]:
    table = ".".join(f"[{part}]" for part in _parts(resource))
    items = _filter_items(row_filter)
    predicates = [f"[{field}] = ?" for field, _value in items]
    where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
    # Identifier-only interpolation; see the MySQL reader note above.
    statement = f"SELECT TOP (?) * FROM {table}{where}"  # noqa: S608
    values = (_limit(limit), *[value for _field, value in items])
    dsn = _mssql_dsn(config)
    import aioodbc
    import pyodbc

    connection = None
    try:
        connection = await aioodbc.connect(dsn=dsn, timeout=int(_CONNECT_TIMEOUT_SECONDS), autocommit=True)
        async with connection.cursor() as cursor:
            await asyncio.wait_for(cursor.execute(statement, values), timeout=_QUERY_TIMEOUT_SECONDS)
            rows = await asyncio.wait_for(cursor.fetchall(), timeout=_QUERY_TIMEOUT_SECONDS)
            columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in rows]
    except ConnectorSqlError:
        raise
    except (pyodbc.Error, TimeoutError, OSError):
        raise ConnectorSqlError("SQL Server connector read failed.") from None
    finally:
        if connection is not None:
            await _close(connection)


async def _read_oracle(
    config: Mapping[str, Any], resource: str, row_filter: Mapping[str, Any], limit: int
) -> list[dict[str, Any]]:
    encryption = (config.get("encryption") or {}).get("encryption_method", "unencrypted")
    if encryption != "unencrypted":
        raise ConnectorSqlConfigurationError("This Oracle encryption mode is not supported for live reads.")
    connection_data = config.get("connection_data") or {}
    connection_type = connection_data.get("connection_type")
    if connection_type == "service_name":
        dsn_kwargs = {"service_name": _required(connection_data, "service_name")}
    elif connection_type == "sid":
        dsn_kwargs = {"sid": _required(connection_data, "sid")}
    else:
        raise ConnectorSqlConfigurationError("Oracle connection data is not supported for live reads.")
    import oracledb

    dsn = oracledb.makedsn(_required(config, "host"), int(config.get("port", 1521)), **dsn_kwargs)
    table = ".".join(f'"{part}"' for part in _parts(resource))
    items = _filter_items(row_filter)
    predicates = [f'"{field}" = :{index}' for index, (field, _value) in enumerate(items, 1)]
    where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
    # Identifier-only interpolation; see the MySQL reader note above.
    statement = f"SELECT * FROM {table}{where} FETCH FIRST :{len(items) + 1} ROWS ONLY"  # noqa: S608
    values = (*[value for _field, value in items], _limit(limit))
    connection = None
    try:
        connection = await asyncio.wait_for(
            oracledb.connect_async(
                user=_required(config, "username", "user"),
                password=_required(config, "password"),
                dsn=dsn,
            ),
            timeout=_CONNECT_TIMEOUT_SECONDS,
        )
        async with connection.cursor() as cursor:
            await asyncio.wait_for(cursor.execute(statement, values), timeout=_QUERY_TIMEOUT_SECONDS)
            rows = await asyncio.wait_for(cursor.fetchall(), timeout=_QUERY_TIMEOUT_SECONDS)
            columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in rows]
    except ConnectorSqlError:
        raise
    except (oracledb.Error, TimeoutError, OSError):
        raise ConnectorSqlError("Oracle connector read failed.") from None
    finally:
        if connection is not None:
            await _close(connection)


async def read_sql_connector(
    connector_type: str,
    config: Mapping[str, Any],
    resource: str,
    row_filter: Mapping[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    """Read one selected table using identifiers and equality values only."""
    _parts(resource)
    _filter_items(row_filter)
    readers = {
        "source-mysql": _read_mysql,
        "source-mssql": _read_mssql,
        "source-oracle": _read_oracle,
    }
    reader = readers.get(connector_type)
    if reader is None:
        raise ConnectorSqlConfigurationError("SQL connector type is not supported.")
    return await reader(config, resource, row_filter, limit)
