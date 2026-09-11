from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.core.settings import get_settings
from src.core.trusted import TrustedToolContext
from src.core.trusted_context import set_current_trusted_context
from src.tools.connector_tools import (
    SUPPORTED_CONNECTOR_TYPES,
    ConnectorAccessError,
    ConnectorTools,
    _matches_globs,
    _postgres_config,
    _s3_client_factory,
    _s3_read_file,
    _sftp_connection_options,
    connector_list_resources,
    connector_read,
)


def test_supported_connector_catalog_is_explicit():
    assert frozenset(
        {
            "source-elasticsearch",
            "source-http-request",
            "source-kafka",
            "source-microsoft-sharepoint",
            "source-mongodb",
            "source-mongodb-v2",
            "source-mssql",
            "source-mysql",
            "source-opensearch",
            "source-oracle",
            "source-outlook",
            "source-postgres",
            "source-s3",
            "source-sftp-bulk",
        }
    ) == SUPPORTED_CONNECTOR_TYPES


def test_postgres_native_ssl_shape_and_tunnel_fail_closed():
    config = {
        "host": "db",
        "username": "reader",
        "password": "secret",
        "database": "reporting",
        "ssl_mode": {"mode": "require"},
        "tunnel_method": {"tunnel_method": "NO_TUNNEL"},
    }
    assert _postgres_config(config)["ssl"] == "require"

    with pytest.raises(ConnectorAccessError):
        _postgres_config({**config, "ssl_mode": {"mode": "verify-full"}})
    with pytest.raises(ConnectorAccessError):
        _postgres_config(
            {**config, "tunnel_method": {"tunnel_method": "SSH_PASSWORD_AUTH"}}
        )


def test_airbyte_globstar_matches_zero_or_more_directories():
    assert _matches_globs("orders/one.jsonl", ["orders/**/*.jsonl"])
    assert _matches_globs("orders/2026/one.jsonl", ["orders/**/*.jsonl"])
    assert not _matches_globs("private/one.jsonl", ["orders/**/*.jsonl"])


def test_s3_requires_saved_credentials(monkeypatch):
    monkeypatch.setattr("aioboto3.Session", lambda: pytest.fail("must not connect"))
    with pytest.raises(ConnectorAccessError):
        _s3_client_factory({"bucket": "data"})


def test_sftp_private_key_pem_is_imported_not_used_as_a_filename(monkeypatch):
    calls = {}
    parsed_key = object()

    def import_key(value, *, passphrase):
        calls.update(value=value, passphrase=passphrase)
        return parsed_key

    monkeypatch.setattr("asyncssh.import_private_key", import_key)
    options, root = _sftp_connection_options(
        {
            "host": "sftp.internal",
            "username": "reader",
            "folder_path": "/exports",
            "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----...",
            "private_key_passphrase": "phrase",
        }
    )
    assert options["client_keys"] == [parsed_key]
    assert "passphrase" not in options
    assert root == "/exports"
    assert calls["passphrase"] == "phrase"


class _Response:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _env(monkeypatch) -> None:
    values = {
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": "8003",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "tools",
        "POSTGRES_PASSWORD": "tools",
        "POSTGRES_DB": "tools",
        "USER_SERVICE_URL": "http://user-service:8000",
        "AGENT_SERVICE_URL": "http://agent-service:8001/",
        "INTERNAL_SERVICE_TOKEN": "internal-secret",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clear_context():
    yield
    set_current_trusted_context(None)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_list_resources_resolves_binding_without_exposing_config(monkeypatch):
    calls = {}

    class Client:
        def __init__(self, *, timeout):
            calls["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, json, headers):
            calls.update(url=url, payload=json, headers=headers)
            return _Response(
                {
                    "id": "ds-1",
                    "name": "Reporting",
                    "connector_type": "source-postgres",
                    "streams": ["public.orders", "public.customers"],
                    "config": {"password": "never-visible"},
                }
            )

    _env(monkeypatch)
    monkeypatch.setattr("src.tools.connector_tools.httpx.AsyncClient", Client)
    set_current_trusted_context(
        TrustedToolContext(
            user_id="user-1",
            binding_references={"connectors.persona_id": "42"},
        )
    )

    result = json.loads(await connector_list_resources("ds-1"))

    assert result == {
        "success": True,
        "datasource_id": "ds-1",
        "name": "Reporting",
        "resources": ["public.orders", "public.customers"],
        "truncated": False,
    }
    assert calls["url"] == "http://agent-service:8001/internal/connector-tools/resolve"
    assert calls["payload"] == {
        "persona_id": 42,
        "datasource_id": "ds-1",
        "operation": "list_resources",
    }
    assert calls["headers"] == {
        "X-Internal-Service-Token": "internal-secret",
        "x-user-id": "user-1",
    }
    assert "never-visible" not in json.dumps(result)


@pytest.mark.asyncio
async def test_list_resources_is_bounded(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {
            "name": "Large catalog",
            "config": {},
            "streams": [f"public.table_{index}" for index in range(150)],
        }

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)

    result = json.loads(await connector_list_resources("ds"))

    assert len(result["resources"]) == 100
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_file_listing_has_one_global_output_bound(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {
            "name": "files",
            "connector_type": "source-s3",
            "config": {},
            "streams": [f"stream_{index}" for index in range(100)],
        }

    async def list_files(_config, resource):
        return [
            {"path": f"{resource}/{'x' * 480}/{index}.jsonl", "size": 1}
            for index in range(100)
        ]

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools._s3_list_files", list_files)

    encoded = await connector_list_resources("ds")

    assert len(encoded.encode()) <= 65_536
    assert json.loads(encoded)["truncated"] is True


@pytest.mark.asyncio
async def test_postgres_read_is_bounded_and_restricted_to_selected_stream(monkeypatch):
    captured = {}

    async def resolve(*_args, **_kwargs):
        return {
            "id": "ds-1",
            "name": "Reporting",
            "connector_type": "source-postgres",
            "streams": ["public.orders"],
            "config": {
                "host": "db",
                "port": 5432,
                "username": "reader",
                "password": "secret",
                "database": "reporting",
            },
        }

    class Connection:
        async def fetch(self, statement, *values, timeout):
            captured.update(statement=statement, values=values, timeout=timeout)
            return [{"id": 1, "status": "paid"}]

        async def close(self):
            captured["closed"] = True

    async def connect(**config):
        captured["config"] = config
        return Connection()

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools.asyncpg.connect", connect)
    monkeypatch.setattr(
        "src.tools.connector_tools.get_settings",
        lambda: SimpleNamespace(connector_postgres_endpoints="{}"),
    )

    result = json.loads(
        await connector_read("ds-1", "public.orders", filter={"status": "paid"}, limit=9999)
    )

    assert result["success"] is True
    assert result["rows"] == [{"id": 1, "status": "paid"}]
    assert result["limit"] == 100
    assert captured["statement"] == (
        'SELECT * FROM "public"."orders" WHERE "status" = $1 LIMIT $2'
    )
    assert captured["values"] == ("paid", 100)
    assert captured["closed"] is True

    denied = json.loads(await connector_read("ds-1", "public.payments"))
    assert denied["success"] is False
    assert denied["error_category"] == "authorization"


@pytest.mark.asyncio
async def test_read_rejects_query_and_hides_raw_connection_error(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {
            "id": "ds-1",
            "name": "Reporting",
            "connector_type": "source-postgres",
            "streams": ["public.orders"],
            "config": {
                "host": "db",
                "username": "reader",
                "password": "top-secret",
                "database": "reporting",
            },
        }

    async def connect(**_config):
        raise RuntimeError("password=top-secret host=db")

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools.asyncpg.connect", connect)
    monkeypatch.setattr(
        "src.tools.connector_tools.get_settings",
        lambda: SimpleNamespace(connector_postgres_endpoints="{}"),
    )

    rejected = json.loads(
        await connector_read("ds-1", "public.orders", query="DROP TABLE orders")
    )
    assert rejected["error_category"] == "validation"

    failed = await connector_read("ds-1", "public.orders")
    assert "top-secret" not in failed
    assert "host=db" not in failed
    assert json.loads(failed)["error_category"] == "connection"


def test_connector_category_registers_common_runtime_tools():
    registered = []

    class MCP:
        def tool(self):
            def decorator(function):
                registered.append(function.__name__)
                return function

            return decorator

    category = ConnectorTools()
    category.register_tools(MCP())

    assert category.name == "connector"
    assert registered == ["connector_list_resources", "connector_read"]


@pytest.mark.asyncio
async def test_elasticsearch_read_keeps_configured_origin_and_bounds_hits(monkeypatch):
    calls = {}

    async def resolve(*_args, **_kwargs):
        return {
            "connector_type": "source-elasticsearch",
            "streams": ["orders"],
            "config": {
                "endpoint": "https://search.internal:9200/",
                "username": "reader",
                "password": "secret",
            },
        }

    class Client:
        def __init__(self, **kwargs):
            calls["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **kwargs):
            calls.update(url=url, request=kwargs)
            return _Response({"hits": {"hits": [{"_id": "1", "_source": {"total": 12}}]}})

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools.httpx.AsyncClient", Client)

    result = json.loads(await connector_read("ds", "orders", query="paid", limit=500))

    assert result["rows"] == [{"_id": "1", "total": 12}]
    assert calls["url"] == "https://search.internal:9200/orders/_search"
    assert calls["request"]["params"] == {"q": "paid", "size": 100}
    assert calls["client"]["follow_redirects"] is False


@pytest.mark.asyncio
async def test_http_request_read_uses_only_configured_resource_path(monkeypatch):
    calls = {}

    async def resolve(*_args, **_kwargs):
        return {
            "connector_type": "source-http-request",
            "streams": ["orders"],
            "config": {
                "base_url": "https://api.internal/v1/",
                "resources": {"orders": "reports/orders"},
                "headers": {"Authorization": "Bearer hidden"},
            },
        }

    class Client:
        def __init__(self, **kwargs):
            calls["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **kwargs):
            calls.update(url=url, request=kwargs)
            return _Response({"items": [{"id": 1}]})

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools.httpx.AsyncClient", Client)

    result = json.loads(
        await connector_read("ds", "orders", filter={"status": "paid"}, limit=4)
    )

    assert result["rows"] == [{"id": 1}]
    assert calls["url"] == "https://api.internal/v1/reports/orders"
    assert calls["request"]["params"] == {"status": "paid", "limit": 4}
    assert calls["request"]["headers"] == {"Authorization": "Bearer hidden"}


@pytest.mark.asyncio
async def test_mongodb_read_uses_selected_collection_and_bounded_filter(monkeypatch):
    calls = {}

    async def resolve(*_args, **_kwargs):
        return {
            "connector_type": "source-mongodb-v2",
            "streams": ["reporting.orders"],
            "config": {
                "connection_string": "mongodb://reader:secret@mongo:27017",
                "database": "reporting",
            },
        }

    class Cursor:
        def limit(self, limit):
            calls["limit"] = limit
            return self

        async def to_list(self, *, length):
            assert length == 100
            return [{"_id": 7, "status": "paid"}]

    class Collection:
        def find(self, row_filter):
            calls["filter"] = row_filter
            return Cursor()

    class Client:
        def __getitem__(self, database):
            calls["database"] = database
            return {"orders": Collection()}

        async def close(self):
            calls["closed"] = True

    def factory(config):
        calls["config"] = config
        return Client()

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools._mongo_client_factory", factory)

    result = json.loads(
        await connector_read("ds", "reporting.orders", filter={"status": "paid"}, limit=200)
    )

    assert result["rows"] == [{"_id": 7, "status": "paid"}]
    assert calls["database"] == "reporting"
    assert calls["filter"] == {"status": "paid"}
    assert calls["limit"] == 100
    assert calls["closed"] is True


@pytest.mark.asyncio
async def test_mongodb_v2_uses_native_database_configurations(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {
            "connector_type": "source-mongodb-v2",
            "streams": ["reporting.orders"],
            "config": {
                "connection_string": {"connection_string": "mongodb://mongo:27017"},
                "database_configurations": [{"database": "reporting"}],
            },
        }

    calls = {}

    class Cursor:
        def limit(self, _limit):
            return self

        async def to_list(self, *, length):
            return []

    class Collection:
        def find(self, _filter):
            return Cursor()

    class Client:
        def __getitem__(self, database):
            calls["database"] = database
            return {"orders": Collection()}

        async def close(self):
            pass

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools._mongo_client_factory", lambda _config: Client())

    result = json.loads(await connector_read("ds", "reporting.orders"))

    assert result["success"] is True
    assert calls["database"] == "reporting"


@pytest.mark.asyncio
async def test_read_response_size_is_bounded(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {
            "connector_type": "source-http-request",
            "streams": ["records"],
            "config": {"base_url": "https://api.internal/", "resources": {"records": "r"}},
        }

    async def read(*_args, **_kwargs):
        return [{"payload": "x" * 100_000}]

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools._read_http", read)

    result = await connector_read("ds", "records")

    assert len(result.encode()) <= 65_536
    assert json.loads(result)["truncated"] is True


@pytest.mark.asyncio
async def test_mysql_dispatches_to_bounded_sql_adapter(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {
            "connector_type": "source-mysql",
            "streams": ["sales.orders"],
            "config": {"password": "hidden"},
        }

    calls = {}

    async def read(connector_type, config, resource, row_filter, limit):
        calls.update(
            connector_type=connector_type,
            config=config,
            resource=resource,
            row_filter=row_filter,
            limit=limit,
        )
        return [{"id": 1}]

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools.read_sql_connector", read)

    result = json.loads(
        await connector_read("ds", "sales.orders", filter={"status": "paid"}, limit=200)
    )

    assert result["rows"] == [{"id": 1}]
    assert calls == {
        "connector_type": "source-mysql",
        "config": {"password": "hidden"},
        "resource": "sales.orders",
        "row_filter": {"status": "paid"},
        "limit": 100,
    }


@pytest.mark.asyncio
async def test_kafka_dispatches_selected_topic_without_filters(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {
            "connector_type": "source-kafka",
            "streams": ["orders"],
            "config": {"bootstrap_servers": "kafka:9092"},
        }

    calls = {}

    async def read(config, topic, limit):
        calls.update(config=config, topic=topic, limit=limit)
        return [{"partition": 0, "offset": 4, "value": {"id": 1}}]

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools.read_kafka_connector", read)

    result = json.loads(await connector_read("ds", "orders", limit=200))

    assert result["rows"][0]["offset"] == 4
    assert calls == {
        "config": {"bootstrap_servers": "kafka:9092"},
        "topic": "orders",
        "limit": 100,
    }


@pytest.mark.asyncio
async def test_s3_lists_and_reads_only_keys_matching_selected_stream_globs(monkeypatch):
    async def resolve(_datasource_id, _operation):
        return {
            "connector_type": "source-s3",
            "streams": ["orders"],
            "config": {
                "bucket": "company-data",
                "aws_access_key_id": "key",
                "aws_secret_access_key": "secret",
                "endpoint": "http://minio:9000",
                "streams": [{"name": "orders", "globs": ["orders/**/*.jsonl"]}],
            },
        }

    class Body:
        async def read(self, _size):
            return b'{"id":1}\n'

        async def close(self):
            return None

    class Client:
        async def list_objects_v2(self, **kwargs):
            assert kwargs == {"Bucket": "company-data", "MaxKeys": 1000, "Prefix": "orders/"}
            return {
                "Contents": [
                    {"Key": "orders/2026/one.jsonl", "Size": 9},
                    {"Key": "private/secret.jsonl", "Size": 99},
                ]
            }

        async def get_object(self, **kwargs):
            assert kwargs == {
                "Bucket": "company-data",
                "Key": "orders/2026/one.jsonl",
                "Range": "bytes=0-65535",
            }
            return {"Body": Body(), "ContentLength": 9, "ContentType": "application/jsonl"}

    class ClientContext:
        async def __aenter__(self):
            return Client()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr(
        "src.tools.connector_tools._s3_client_factory", lambda _config: ClientContext()
    )

    listed = json.loads(await connector_list_resources("ds"))
    assert listed["files"] == {
        "orders": [{"path": "orders/2026/one.jsonl", "size": 9}]
    }

    read = json.loads(
        await connector_read(
            "ds", "orders", query=json.dumps({"key": "orders/2026/one.jsonl"})
        )
    )
    assert read["rows"][0]["content"] == '{"id":1}\n'

    denied = json.loads(
        await connector_read("ds", "orders", query=json.dumps({"key": "private/secret.jsonl"}))
    )
    assert denied["error_category"] == "authorization"


@pytest.mark.asyncio
async def test_s3_range_read_uses_content_range_total_for_truncation(monkeypatch):
    class Body:
        async def read(self, _size):
            return b"x" * 65_536

        async def close(self):
            return None

    class Client:
        async def get_object(self, **_kwargs):
            return {
                "Body": Body(),
                "ContentLength": 65_536,
                "ContentRange": "bytes 0-65535/100000",
                "ContentType": "text/plain",
            }

    class Context:
        async def __aenter__(self):
            return Client()

        async def __aexit__(self, *_args):
            return None

    config = {
        "bucket": "data",
        "streams": [{"name": "files", "globs": ["**"]}],
    }
    monkeypatch.setattr("src.tools.connector_tools._s3_client_factory", lambda _config: Context())

    content, size, content_type = await _s3_read_file(config, "files", "large.txt")

    assert len(content) == 65_536
    assert size == 100_000
    assert content_type == "text/plain"


@pytest.mark.asyncio
async def test_sftp_lists_and_reads_only_paths_under_selected_stream_glob(monkeypatch):
    async def resolve(_datasource_id, _operation):
        return {
            "connector_type": "source-sftp-bulk",
            "streams": ["invoices"],
            "config": {
                "host": "sftp.internal",
                "port": 22,
                "username": "reader",
                "password": "secret",
                "folder_path": "/exports",
                "streams": [{"name": "invoices", "globs": ["invoices/**/*.csv"]}],
            },
        }

    async def list_files(_config, patterns):
        assert patterns == ["/exports/invoices/**/*.csv"]
        return [{"path": "/exports/invoices/2026/one.csv", "size": 12}]

    async def read_file(_config, path):
        assert path == "/exports/invoices/2026/one.csv"
        return b"id,total\n1,9", 12

    monkeypatch.setattr("src.tools.connector_tools._resolve_connector", resolve)
    monkeypatch.setattr("src.tools.connector_tools._sftp_list_files", list_files)
    monkeypatch.setattr("src.tools.connector_tools._sftp_read_file", read_file)

    listed = json.loads(await connector_list_resources("ds"))
    assert listed["files"]["invoices"][0]["path"] == "/exports/invoices/2026/one.csv"

    read = json.loads(
        await connector_read(
            "ds", "invoices", query=json.dumps({"path": "/exports/invoices/2026/one.csv"})
        )
    )
    assert read["rows"][0]["content"] == "id,total\n1,9"

    denied = json.loads(
        await connector_read("ds", "invoices", query=json.dumps({"path": "/etc/passwd"}))
    )
    assert denied["error_category"] == "authorization"
