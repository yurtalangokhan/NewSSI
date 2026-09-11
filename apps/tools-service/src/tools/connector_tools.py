"""Bounded, read-only access to connector instances assigned to an agent."""

from __future__ import annotations

import asyncio
import inspect
import json
import posixpath
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import aioboto3
import asyncpg
import httpx
from wcmatch import glob

from ..connectors.kafka import ConnectorKafkaError, read_kafka_connector
from ..connectors.microsoft import MicrosoftConnectorError, read_microsoft_connector
from ..connectors.sql import ConnectorSqlError, read_sql_connector
from ..core.base import BaseToolCategory
from ..core.settings import get_settings
from ..core.trusted_context import get_current_trusted_context

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 25
_QUERY_TIMEOUT_SECONDS = 10.0
_RESOLVE_TIMEOUT_SECONDS = 20.0
_MAX_RESULT_BYTES = 65_536
_MAX_STRING_LENGTH = 4_096
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_HTTP_CONNECTORS = frozenset({"source-http-request"})
_SEARCH_CONNECTORS = frozenset({"source-elasticsearch", "source-opensearch"})
_MONGO_CONNECTORS = frozenset({"source-mongodb-v2", "source-mongodb"})
_FILE_CONNECTORS = frozenset({"source-s3", "source-sftp-bulk"})
_SQL_CONNECTORS = frozenset({"source-mysql", "source-mssql", "source-oracle"})
_KAFKA_CONNECTORS = frozenset({"source-kafka"})
_MICROSOFT_CONNECTORS = frozenset({"source-microsoft-sharepoint", "source-outlook"})
SUPPORTED_CONNECTOR_TYPES = frozenset(
    {
        "source-postgres",
        *_HTTP_CONNECTORS,
        *_SEARCH_CONNECTORS,
        *_MONGO_CONNECTORS,
        *_FILE_CONNECTORS,
        *_SQL_CONNECTORS,
        *_KAFKA_CONNECTORS,
        *_MICROSOFT_CONNECTORS,
    }
)


class ConnectorAccessError(Exception):
    """A safe connector error whose message contains no resolved configuration."""

    def __init__(self, message: str, category: str) -> None:
        super().__init__(message)
        self.category = category


def _error(message: str, category: str) -> str:
    return json.dumps({"success": False, "error": message, "error_category": category})


def _bounded_limit(limit: int) -> int:
    return min(max(limit, 1), _MAX_LIMIT)


async def _resolve_connector(datasource_id: str, operation: str) -> dict[str, Any]:
    context = get_current_trusted_context()
    if context is None or not context.user_id:
        raise ConnectorAccessError("Connector access requires an authenticated user.", "authorization")

    raw_persona_id = context.binding_references.get("connectors.persona_id")
    try:
        persona_id = int(raw_persona_id) if raw_persona_id is not None else None
    except (TypeError, ValueError) as exc:
        raise ConnectorAccessError("Connector binding is unavailable.", "authorization") from exc
    if persona_id is None:
        raise ConnectorAccessError("Connector binding is unavailable.", "authorization")

    settings = get_settings()
    if not settings.agent_service_url or not settings.internal_service_token:
        raise ConnectorAccessError("Connector service is unavailable.", "configuration")

    try:
        async with httpx.AsyncClient(timeout=_RESOLVE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.agent_service_url}/internal/connector-tools/resolve",
                json={
                    "persona_id": persona_id,
                    "datasource_id": datasource_id,
                    "operation": operation,
                },
                headers={
                    "X-Internal-Service-Token": settings.internal_service_token,
                    "x-user-id": context.user_id,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ConnectorAccessError("Connector authorization failed.", "authorization") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("config"), dict):
        raise ConnectorAccessError("Connector configuration is unavailable.", "configuration")
    return payload


def _quote_identifier(identifier: str) -> str:
    if not _IDENTIFIER.fullmatch(identifier):
        raise ConnectorAccessError("Resource contains an invalid identifier.", "validation")
    return f'"{identifier}"'


def _resource_sql(resource: str) -> str:
    parts = resource.split(".")
    if len(parts) not in {1, 2}:
        raise ConnectorAccessError("Resource must be a table or schema.table name.", "validation")
    return ".".join(_quote_identifier(part) for part in parts)


def _postgres_runtime_config(datasource_id: str, config: dict[str, Any]) -> dict[str, Any]:
    """Apply admin-configured transport endpoints without changing source credentials."""
    try:
        endpoints = json.loads(get_settings().connector_postgres_endpoints)
        if not isinstance(endpoints, dict):
            raise ValueError
        override = endpoints.get(datasource_id, {})
        if not isinstance(override, dict) or set(override) - {"host", "port"}:
            raise ValueError
        if "host" in override and (
            not isinstance(override["host"], str) or not override["host"].strip()
        ):
            raise ValueError
        if "port" in override and (
            type(override["port"]) is not int or not 1 <= override["port"] <= 65535
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise ConnectorAccessError(
            "Invalid connector endpoint configuration.", "configuration"
        ) from None
    return {**config, **override}


def _postgres_config(config: dict[str, Any]) -> dict[str, Any]:
    tunnel = config.get("tunnel_method")
    if isinstance(tunnel, dict):
        tunnel = tunnel.get("tunnel_method")
    if tunnel not in {None, "", "NO_TUNNEL"}:
        raise ConnectorAccessError("PostgreSQL SSH tunnels are not supported.", "configuration")
    required = {
        "host": config.get("host"),
        "port": config.get("port", 5432),
        "user": config.get("username") or config.get("user"),
        "password": config.get("password"),
        "database": config.get("database") or config.get("dbname"),
    }
    if any(value is None or value == "" for value in required.values()):
        raise ConnectorAccessError("PostgreSQL connector configuration is incomplete.", "configuration")
    ssl_mode = config.get("ssl_mode")
    if isinstance(ssl_mode, dict):
        ssl_mode = ssl_mode.get("mode")
    if ssl_mode in {"verify-ca", "verify-full"}:
        raise ConnectorAccessError(
            "PostgreSQL certificate-verification settings are not supported.", "configuration"
        )
    if ssl_mode == "require":
        required["ssl"] = "require"
    elif ssl_mode not in {None, "", "disable", "disabled", "unencrypted"}:
        raise ConnectorAccessError("PostgreSQL SSL mode is not supported.", "configuration")
    return required


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return f"<binary:{len(value)} bytes>"
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    if value is not None and value.__class__.__module__.startswith("bson"):
        return str(value)
    return value


def _bounded_value(value: Any) -> tuple[Any, bool]:
    value = _json_value(value)
    if isinstance(value, str) and len(value) > _MAX_STRING_LENGTH:
        return value[:_MAX_STRING_LENGTH], True
    if isinstance(value, dict):
        bounded: dict[str, Any] = {}
        truncated = len(value) > 100
        for key, item in list(value.items())[:100]:
            bounded_item, item_truncated = _bounded_value(item)
            bounded[str(key)] = bounded_item
            truncated = truncated or item_truncated
        return bounded, truncated
    if isinstance(value, list):
        bounded_items = []
        truncated = len(value) > 100
        for item in value[:100]:
            bounded_item, item_truncated = _bounded_value(item)
            bounded_items.append(bounded_item)
            truncated = truncated or item_truncated
        return bounded_items, truncated
    return value, False


def _read_response(datasource_id: str, resource: str, rows: list[Any], limit: int) -> str:
    bounded_rows: list[Any] = []
    truncated = False
    for row in rows:
        bounded_row, row_truncated = _bounded_value(row)
        candidate = {
            "success": True,
            "datasource_id": datasource_id,
            "resource": resource,
            "rows": [*bounded_rows, bounded_row],
            "limit": limit,
            "truncated": truncated or row_truncated,
        }
        if len(json.dumps(candidate).encode()) > _MAX_RESULT_BYTES:
            truncated = True
            break
        bounded_rows.append(bounded_row)
        truncated = truncated or row_truncated
    return json.dumps(
        {
            "success": True,
            "datasource_id": datasource_id,
            "resource": resource,
            "rows": bounded_rows,
            "limit": limit,
            "truncated": truncated or len(bounded_rows) < len(rows),
        }
    )


def _stream_globs(config: dict[str, Any], resource: str) -> list[str]:
    streams = config.get("streams")
    if not isinstance(streams, list):
        raise ConnectorAccessError("File connector stream mappings are unavailable.", "configuration")
    for stream in streams:
        if isinstance(stream, dict) and stream.get("name") == resource:
            raw_globs = stream.get("globs") or stream.get("glob")
            if isinstance(raw_globs, str):
                globs = raw_globs.split("|")
            elif isinstance(raw_globs, list) and all(isinstance(item, str) for item in raw_globs):
                globs = [part for item in raw_globs for part in item.split("|")]
            else:
                raise ConnectorAccessError("File connector stream glob is unavailable.", "configuration")
            if not globs or any(pattern.startswith("/") or ".." in pattern.split("/") for pattern in globs):
                raise ConnectorAccessError("File connector stream glob is invalid.", "configuration")
            return globs
    raise ConnectorAccessError("File connector stream mapping is unavailable.", "configuration")


def _matches_globs(path: str, globs: list[str]) -> bool:
    return any(glob.globmatch(path, pattern, flags=glob.GLOBSTAR | glob.SPLIT) for pattern in globs)


def _glob_prefix(pattern: str) -> str:
    special = min((pattern.find(char) for char in "*?[" if char in pattern), default=len(pattern))
    return pattern[:special].rsplit("/", 1)[0] + "/" if "/" in pattern[:special] else ""


def _s3_client_factory(config: dict[str, Any]) -> Any:
    access_key = config.get("aws_access_key_id")
    secret_key = config.get("aws_secret_access_key")
    if not access_key or not secret_key:
        raise ConnectorAccessError("Saved S3 connector credentials are unavailable.", "configuration")
    if config.get("role_arn"):
        raise ConnectorAccessError("S3 role authentication is not supported.", "configuration")
    endpoint = config.get("endpoint") or config.get("endpoint_url")
    if endpoint and (
        not isinstance(endpoint, str) or urlsplit(endpoint).scheme not in {"http", "https"}
    ):
        raise ConnectorAccessError("S3 connector endpoint is invalid.", "configuration")
    return aioboto3.Session().client(
        "s3",
        aws_access_key_id=access_key or None,
        aws_secret_access_key=secret_key or None,
        region_name=config.get("region_name") or config.get("region"),
        endpoint_url=endpoint or None,
    )


async def _s3_list_files(config: dict[str, Any], resource: str) -> list[dict[str, Any]]:
    bucket = config.get("bucket")
    if not isinstance(bucket, str) or not bucket:
        raise ConnectorAccessError("S3 connector bucket is unavailable.", "configuration")
    globs = _stream_globs(config, resource)
    async def fetch() -> list[dict[str, Any]]:
        files: dict[str, dict[str, Any]] = {}
        async with _s3_client_factory(config) as client:
            for pattern in globs:
                response = await client.list_objects_v2(
                    Bucket=bucket, MaxKeys=1000, Prefix=_glob_prefix(pattern)
                )
                for item in response.get("Contents", []):
                    key = item.get("Key")
                    if isinstance(key, str) and _matches_globs(key, globs):
                        files[key] = {"path": key[:512], "size": int(item.get("Size", 0))}
                        if len(files) >= _MAX_LIMIT:
                            return list(files.values())
        return list(files.values())

    try:
        return await asyncio.wait_for(fetch(), timeout=12.0)
    except ConnectorAccessError:
        raise
    except Exception as exc:
        raise ConnectorAccessError("Connector file listing failed.", "connection") from exc


async def _s3_read_file(
    config: dict[str, Any], resource: str, key: str
) -> tuple[bytes, int, str]:
    bucket = config.get("bucket")
    if not isinstance(bucket, str) or not _matches_globs(key, _stream_globs(config, resource)):
        raise ConnectorAccessError("File is not assigned to this connector stream.", "authorization")
    async def fetch() -> tuple[bytes, int, str]:
        async with _s3_client_factory(config) as client:
            response = await client.get_object(Bucket=bucket, Key=key, Range="bytes=0-65535")
            body = response["Body"]
            try:
                content = await body.read(_MAX_RESULT_BYTES)
            finally:
                closed = body.close()
                if inspect.isawaitable(closed):
                    await closed
            content_range = response.get("ContentRange")
            total_match = (
                re.search(r"/(\d+)$", content_range) if isinstance(content_range, str) else None
            )
            if total_match:
                total_size = int(total_match.group(1))
            else:
                content_length = int(response.get("ContentLength", len(content)))
                total_size = (
                    _MAX_RESULT_BYTES + 1
                    if len(content) >= _MAX_RESULT_BYTES and content_length <= len(content)
                    else content_length
                )
            return content, total_size, str(
                response.get("ContentType", "application/octet-stream")
            )

    try:
        return await asyncio.wait_for(fetch(), timeout=12.0)
    except ConnectorAccessError:
        raise
    except Exception as exc:
        raise ConnectorAccessError("Connector file read failed.", "connection") from exc


def _sftp_connection_options(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    host = config.get("host")
    username = config.get("username") or config.get("user")
    root = config.get("folder_path") or config.get("path")
    credentials = config.get("credentials", {})
    if not isinstance(credentials, dict):
        credentials = {}
    password = config.get("password") or credentials.get("password") or credentials.get(
        "auth_user_password"
    )
    private_key = config.get("private_key") or credentials.get("private_key")
    if not all(isinstance(value, str) and value for value in (host, username, root)):
        raise ConnectorAccessError("SFTP connector configuration is incomplete.", "configuration")
    if not password and not private_key:
        raise ConnectorAccessError("SFTP connector credentials are unavailable.", "configuration")
    options: dict[str, Any] = {
        "host": host,
        "port": int(config.get("port", 22)),
        "username": username,
        "known_hosts": None,
    }
    if password:
        options["password"] = password
    if private_key:
        passphrase = config.get("private_key_passphrase") or credentials.get("private_key_passphrase")
        try:
            import asyncssh

            options["client_keys"] = [
                asyncssh.import_private_key(private_key, passphrase=passphrase)
            ]
        except Exception as exc:
            raise ConnectorAccessError(
                "Saved SFTP private key is invalid.", "configuration"
            ) from exc
    return options, posixpath.normpath(str(root))


async def _sftp_list_files(
    config: dict[str, Any], patterns: list[str]
) -> list[dict[str, Any]]:
    import asyncssh

    options, _root = _sftp_connection_options(config)
    async def collect() -> list[dict[str, Any]]:
        async with (
            asyncssh.connect(**options) as connection,
            connection.start_sftp_client() as sftp,
        ):
            files: dict[str, dict[str, Any]] = {}
            for pattern in patterns:
                for match in await sftp.glob(pattern):
                    path = match.filename if hasattr(match, "filename") else str(match)
                    attrs = getattr(match, "attrs", None)
                    size = getattr(attrs, "size", 0) if attrs is not None else 0
                    files[path] = {"path": path[:512], "size": int(size or 0)}
                    if len(files) >= _MAX_LIMIT:
                        return list(files.values())
            return list(files.values())

    try:
        return await asyncio.wait_for(collect(), timeout=12.0)
    except ConnectorAccessError:
        raise
    except Exception as exc:
        raise ConnectorAccessError("Connector file listing failed.", "connection") from exc


async def _sftp_read_file(config: dict[str, Any], path: str) -> tuple[bytes, int]:
    import asyncssh

    options, root = _sftp_connection_options(config)
    async def fetch() -> tuple[bytes, int]:
        async with (
            asyncssh.connect(**options) as connection,
            connection.start_sftp_client() as sftp,
        ):
            real_root = posixpath.normpath(await sftp.realpath(root))
            real_path = posixpath.normpath(await sftp.realpath(path))
            if (
                real_path != posixpath.normpath(path)
                or not real_path.startswith(real_root.rstrip("/") + "/")
            ):
                raise ConnectorAccessError(
                    "File is not assigned to this connector stream.", "authorization"
                )
            attrs = await sftp.stat(real_path)
            async with sftp.open(real_path, "rb") as file:
                content = await file.read(_MAX_RESULT_BYTES)
            if isinstance(content, str):
                content = content.encode()
            return content, int(attrs.size or len(content))

    try:
        return await asyncio.wait_for(fetch(), timeout=12.0)
    except ConnectorAccessError:
        raise
    except Exception as exc:
        raise ConnectorAccessError("Connector file read failed.", "connection") from exc


def _file_query(query: str | None, key: str) -> str:
    try:
        payload = json.loads(query or "")
    except (json.JSONDecodeError, TypeError) as exc:
        raise ConnectorAccessError(f"File read query must contain a {key}.", "validation") from exc
    value = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value:
        raise ConnectorAccessError(f"File read query must contain a {key}.", "validation")
    return value


async def _read_file_connector(
    connector_type: str, config: dict[str, Any], resource: str, query: str | None
) -> list[dict[str, Any]]:
    if connector_type == "source-s3":
        key = _file_query(query, "key")
        content, size, content_type = await _s3_read_file(config, resource, key)
        return [{
            "path": key,
            "size": size,
            "content_type": content_type,
            "content": content.decode("utf-8", errors="replace"),
            "truncated": size > len(content),
        }]
    path = _file_query(query, "path")
    _options, root = _sftp_connection_options(config)
    globs = [posixpath.join(root, pattern) for pattern in _stream_globs(config, resource)]
    normalized = posixpath.normpath(path)
    if not normalized.startswith(root.rstrip("/") + "/") or not _matches_globs(normalized, globs):
        raise ConnectorAccessError("File is not assigned to this connector stream.", "authorization")
    content, size = await _sftp_read_file(config, normalized)
    return [{
        "path": normalized,
        "size": size,
        "content": content.decode("utf-8", errors="replace"),
        "truncated": size > len(content),
    }]


async def _list_file_resources(
    connector_type: str, config: dict[str, Any], resources: list[str]
) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    async def collect() -> tuple[dict[str, list[dict[str, Any]]], bool]:
        files: dict[str, list[dict[str, Any]]] = {}
        remaining = _MAX_LIMIT
        for resource in resources:
            if remaining == 0:
                return files, True
            if connector_type == "source-s3":
                matches = await _s3_list_files(config, resource)
            else:
                _options, root = _sftp_connection_options(config)
                patterns = [
                    posixpath.join(root, pattern)
                    for pattern in _stream_globs(config, resource)
                ]
                matches = await _sftp_list_files(config, patterns)
            files[resource] = matches[:remaining]
            remaining -= len(files[resource])
            if len(matches) > len(files[resource]):
                return files, True
        return files, False

    try:
        return await asyncio.wait_for(collect(), timeout=15.0)
    except TimeoutError as exc:
        raise ConnectorAccessError("Connector file listing timed out.", "connection") from exc


def _list_response(
    datasource_id: str,
    name: str,
    resources: list[str],
    files: dict[str, list[dict[str, Any]]] | None,
    truncated: bool,
) -> str:
    payload: dict[str, Any] = {
        "success": True,
        "datasource_id": datasource_id,
        "name": name,
        "resources": resources,
        "truncated": truncated,
        **({"files": files} if files is not None else {}),
    }
    while len(json.dumps(payload).encode()) > _MAX_RESULT_BYTES and files:
        last_resource = next((key for key in reversed(files) if files[key]), None)
        if last_resource is None:
            break
        files[last_resource].pop()
        payload["truncated"] = True
    return json.dumps(payload)


async def _read_postgres(
    config: dict[str, Any], resource: str, row_filter: dict[str, Any], limit: int
) -> list[dict[str, Any]]:
    table = _resource_sql(resource)
    if len(row_filter) > 10:
        raise ConnectorAccessError("Filter supports at most 10 fields.", "validation")
    values: list[Any] = []
    predicates: list[str] = []
    for field, value in row_filter.items():
        if isinstance(value, dict | list):
            raise ConnectorAccessError("Filter values must be scalar.", "validation")
        values.append(value)
        predicates.append(f"{_quote_identifier(field)} = ${len(values)}")
    where = f" WHERE {' AND '.join(predicates)}" if predicates else ""
    values.append(limit)
    statement = f"SELECT * FROM {table}{where} LIMIT ${len(values)}"

    connection = None
    try:
        connection = await asyncpg.connect(**_postgres_config(config), timeout=5.0)
        records = await connection.fetch(statement, *values, timeout=_QUERY_TIMEOUT_SECONDS)
        return [{key: _json_value(value) for key, value in dict(record).items()} for record in records]
    except ConnectorAccessError:
        raise
    except Exception as exc:
        raise ConnectorAccessError("Connector read failed.", "connection") from exc
    finally:
        if connection is not None:
            await connection.close()


def _safe_base_url(config: dict[str, Any], *keys: str) -> str:
    raw = next((config.get(key) for key in keys if config.get(key)), None)
    if not isinstance(raw, str):
        raise ConnectorAccessError("HTTP connector endpoint is unavailable.", "configuration")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConnectorAccessError("HTTP connector endpoint is invalid.", "configuration")
    return raw.rstrip("/") + "/"


async def _read_search(
    config: dict[str, Any], resource: str, query: str | None, limit: int
) -> list[dict[str, Any]]:
    base_url = _safe_base_url(config, "endpoint", "url")
    url = urljoin(base_url, f"{quote(resource, safe='')}/_search")
    headers: dict[str, str] = {}
    auth = None
    if isinstance(config.get("api_key"), str):
        headers["Authorization"] = f"ApiKey {config['api_key']}"
    elif config.get("username") is not None and config.get("password") is not None:
        auth = (str(config["username"]), str(config["password"]))
    try:
        async with httpx.AsyncClient(
            timeout=_QUERY_TIMEOUT_SECONDS, follow_redirects=False
        ) as client:
            response = await client.get(
                url,
                params={"q": query or "*", "size": limit},
                headers=headers,
                auth=auth,
            )
            response.raise_for_status()
            payload = response.json()
        hits = payload.get("hits", {}).get("hits", [])
        if not isinstance(hits, list):
            raise ValueError("invalid search response")
        rows = []
        for hit in hits[:limit]:
            source = hit.get("_source", {}) if isinstance(hit, dict) else {}
            row = dict(source) if isinstance(source, dict) else {"value": source}
            if isinstance(hit, dict) and "_id" in hit:
                row = {"_id": hit["_id"], **row}
            rows.append(row)
        return rows
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ConnectorAccessError("Connector read failed.", "connection") from exc


def _http_resource_url(config: dict[str, Any], resource: str) -> str:
    resources = config.get("resources")
    path = resources.get(resource) if isinstance(resources, dict) else None
    if not isinstance(path, str) or urlsplit(path).scheme or path.startswith("//"):
        raise ConnectorAccessError("HTTP resource mapping is unavailable.", "configuration")
    base_url = _safe_base_url(config, "base_url", "url")
    url = urljoin(base_url, path.lstrip("/"))
    if urlsplit(url).netloc != urlsplit(base_url).netloc:
        raise ConnectorAccessError("HTTP resource mapping is invalid.", "configuration")
    return url


async def _read_http(
    config: dict[str, Any], resource: str, row_filter: dict[str, Any], limit: int
) -> list[Any]:
    if len(row_filter) > 10 or any(isinstance(value, dict | list) for value in row_filter.values()):
        raise ConnectorAccessError("HTTP filter supports at most 10 scalar fields.", "validation")
    headers = config.get("headers", {})
    if not isinstance(headers, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in headers.items()
    ):
        raise ConnectorAccessError("HTTP connector headers are invalid.", "configuration")
    try:
        async with httpx.AsyncClient(
            timeout=_QUERY_TIMEOUT_SECONDS, follow_redirects=False
        ) as client:
            response = await client.get(
                _http_resource_url(config, resource),
                params={**row_filter, "limit": limit},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, list):
            return payload[:limit]
        if isinstance(payload, dict):
            for key in ("items", "data", "results"):
                if isinstance(payload.get(key), list):
                    return payload[key][:limit]
            return [payload]
        raise ValueError("invalid HTTP response")
    except ConnectorAccessError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ConnectorAccessError("Connector read failed.", "connection") from exc


def _mongo_client_factory(config: dict[str, Any]) -> Any:
    from pymongo import AsyncMongoClient

    uri = config.get("connection_string") or config.get("connection_uri") or config.get("url")
    if isinstance(uri, dict):
        uri = uri.get("connection_string") or uri.get("connection_uri")
    if not isinstance(uri, str) or not uri.startswith(("mongodb://", "mongodb+srv://")):
        raise ConnectorAccessError("MongoDB connector configuration is incomplete.", "configuration")
    return AsyncMongoClient(uri, serverSelectionTimeoutMS=5000, socketTimeoutMS=10000)


def _mongo_database(config: dict[str, Any], resource_parts: list[str]) -> str:
    database = config.get("database") or config.get("database_name")
    raw_configurations = config.get("database_configurations")
    configured: set[str] = set()
    if isinstance(raw_configurations, list):
        for item in raw_configurations:
            value = item.get("database") if isinstance(item, dict) else item
            if isinstance(value, str) and value:
                configured.add(value)
    if database is None and len(resource_parts) == 2:
        database = resource_parts[0]
    if not isinstance(database, str) or not database:
        raise ConnectorAccessError("MongoDB connector configuration is incomplete.", "configuration")
    if configured and database not in configured:
        raise ConnectorAccessError("MongoDB resource namespace is invalid.", "configuration")
    return database


async def _read_mongodb(
    config: dict[str, Any], resource: str, row_filter: dict[str, Any], limit: int
) -> list[dict[str, Any]]:
    resource_parts = resource.split(".")
    if len(resource_parts) not in {1, 2} or not all(
        _IDENTIFIER.fullmatch(part) for part in resource_parts
    ):
        raise ConnectorAccessError("MongoDB resource name is invalid.", "validation")
    if len(row_filter) > 10 or any(isinstance(value, dict | list) for value in row_filter.values()):
        raise ConnectorAccessError("MongoDB filter supports at most 10 scalar fields.", "validation")
    database = _mongo_database(config, resource_parts)
    if len(resource_parts) == 2 and resource_parts[0] != database:
        raise ConnectorAccessError("MongoDB resource namespace is invalid.", "configuration")
    collection = resource_parts[-1]
    client = None
    try:
        client = _mongo_client_factory(config)

        cursor = client[database][collection].find(row_filter).limit(limit)
        documents = await asyncio.wait_for(cursor.to_list(length=limit), timeout=12.0)
        return [_json_value(document) for document in documents]
    except ConnectorAccessError:
        raise
    except Exception as exc:
        raise ConnectorAccessError("Connector read failed.", "connection") from exc
    finally:
        if client is not None:
            await client.close()


async def connector_list_resources(datasource_id: str) -> str:
    """List selected streams for one assigned data source.

    S3 and SFTP responses also include bounded file selectors grouped by stream.
    Use those selectors in ``connector_read``. No connector credentials are returned.
    """
    try:
        resolved = await _resolve_connector(datasource_id, "list_resources")
        resources = resolved.get("streams", [])
        if not isinstance(resources, list) or not all(isinstance(item, str) for item in resources):
            raise ConnectorAccessError("Connector resources are unavailable.", "configuration")
        bounded_resources = [item[:512] for item in resources[:_MAX_LIMIT]]
        files: dict[str, list[dict[str, Any]]] | None = None
        files_truncated = False
        connector_type = resolved.get("connector_type")
        if connector_type in _FILE_CONNECTORS:
            files, files_truncated = await _list_file_resources(
                str(connector_type), resolved["config"], bounded_resources
            )
        return _list_response(
            datasource_id,
            str(resolved.get("name", "")),
            bounded_resources,
            files,
            files_truncated
            or len(resources) > len(bounded_resources)
            or any(len(item) > 512 for item in resources[:_MAX_LIMIT]),
        )
    except ConnectorAccessError as exc:
        return _error(str(exc), exc.category)


async def connector_read(
    datasource_id: str,
    resource: str,
    query: str | None = None,
    filter: dict[str, Any] | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> str:
    """Read bounded data from one selected connector stream.

    SQL and MongoDB use scalar equality values in ``filter`` and reject free-form query
    text. Elasticsearch and OpenSearch use ``query`` as search text. S3 query is JSON
    ``{"key":"path/in/bucket"}``; SFTP query is JSON ``{"path":"/saved/root/file"}``.
    SharePoint query is JSON ``{"drive_id":"id","path":"relative/file"}``, or empty
    to list matching files. Outlook ``messages_details`` uses a message ID in ``query``.
    Kafka accepts neither query nor filter and returns a recent non-committing sample.
    Limit is clamped to 1 through 100, and every output is capped at 64 KiB.
    """
    try:
        resolved = await _resolve_connector(datasource_id, "read")
        streams = resolved.get("streams", [])
        if resource not in streams:
            raise ConnectorAccessError("Resource is not assigned to this agent.", "authorization")
        connector_type = resolved.get("connector_type")
        bounded_limit = _bounded_limit(limit)
        if connector_type == "source-postgres":
            if query:
                raise ConnectorAccessError(
                    "Free-form SQL is not supported; use the structured filter.", "validation"
                )
            rows = await _read_postgres(
                _postgres_runtime_config(datasource_id, resolved["config"]),
                resource,
                filter or {},
                bounded_limit,
            )
        elif connector_type in _SEARCH_CONNECTORS:
            if filter:
                raise ConnectorAccessError(
                    "Search connectors accept query text instead of structured filters.", "validation"
                )
            rows = await _read_search(resolved["config"], resource, query, bounded_limit)
        elif connector_type in _HTTP_CONNECTORS:
            if query:
                raise ConnectorAccessError(
                    "HTTP connectors accept structured query parameters in filter.", "validation"
                )
            rows = await _read_http(resolved["config"], resource, filter or {}, bounded_limit)
        elif connector_type in _MONGO_CONNECTORS:
            if query:
                raise ConnectorAccessError(
                    "Free-form MongoDB queries are not supported; use the structured filter.",
                    "validation",
                )
            rows = await _read_mongodb(resolved["config"], resource, filter or {}, bounded_limit)
        elif connector_type in _FILE_CONNECTORS:
            if filter:
                raise ConnectorAccessError(
                    "File connectors accept a file selector in query.", "validation"
                )
            rows = await _read_file_connector(
                str(connector_type), resolved["config"], resource, query
            )
        elif connector_type in _SQL_CONNECTORS:
            if query:
                raise ConnectorAccessError(
                    "Free-form SQL is not supported; use the structured filter.", "validation"
                )
            try:
                rows = await read_sql_connector(
                    str(connector_type),
                    resolved["config"],
                    resource,
                    filter or {},
                    bounded_limit,
                )
            except ConnectorSqlError as exc:
                message = str(exc)
                category = (
                    "configuration"
                    if "configuration" in message or "mode" in message
                    else "connection"
                )
                raise ConnectorAccessError(message, category) from exc
        elif connector_type in _KAFKA_CONNECTORS:
            if query or filter:
                raise ConnectorAccessError(
                    "Kafka reads don't accept query or filter values.", "validation"
                )
            try:
                rows = await read_kafka_connector(
                    resolved["config"], resource, bounded_limit
                )
            except ConnectorKafkaError as exc:
                raise ConnectorAccessError(str(exc), "connection") from exc
        elif connector_type in _MICROSOFT_CONNECTORS:
            if filter:
                raise ConnectorAccessError(
                    "Microsoft connectors don't accept structured filters.", "validation"
                )
            try:
                rows = await read_microsoft_connector(
                    str(connector_type),
                    resolved["config"],
                    resource,
                    query=query or "",
                    limit=bounded_limit,
                )
            except MicrosoftConnectorError as exc:
                raise ConnectorAccessError(str(exc), "connection") from exc
        else:
            raise ConnectorAccessError("Connector type is not supported for direct reads.", "unsupported")
        return _read_response(datasource_id, resource, rows, bounded_limit)
    except ConnectorAccessError as exc:
        return _error(str(exc), exc.category)


class ConnectorTools(BaseToolCategory):
    @property
    def name(self) -> str:
        return "connector"

    @property
    def description(self) -> str:
        return "Read bounded data from connector instances assigned to the active agent."

    @property
    def label(self) -> str:
        return "Connector Data"

    def register_tools(self, mcp: Any) -> None:
        mcp.tool()(connector_list_resources)
        mcp.tool()(connector_read)
