from types import SimpleNamespace
from unittest.mock import AsyncMock

from connector import ConfiguredCatalog, ConfiguredStream, Stream
import pytest

from service.orchestration.connector_tool_contract import (
    SUPPORTED_CONNECTORS,
    to_tool_connector,
)

ID = "e22ef0bf-3c16-4591-a254-7c48cb16fc55"
OTHER = "e22ef0bf-3c16-4591-a254-7c48cb16fc56"
CATALOG = ConfiguredCatalog(
    streams=[ConfiguredStream(stream=Stream(name="sales.orders", namespace="sales"))]
).model_dump(mode="json")
PERSONA = {
    "base_agent": "configurable-mcp-agent",
    "connector_bindings": [{"datasource_id": ID, "operations": ["read"]}],
}


def service(connector="postgres", config=None):
    from service.orchestration.connector_tool_service import ConnectorToolService

    row = {
        "uuid": ID,
        "name": "Reporting",
        "cmetadata": {"connector_type": connector, "streams": ["sales.orders"]},
    }
    repo = SimpleNamespace(
        get_collection=AsyncMock(return_value=row),
        list_datasource_collections=AsyncMock(return_value=[row]),
    )
    connections = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "datasource_id": ID,
                "connector_name": connector,
                "config_id": "config-1",
                "owner_user_id": "owner-1",
                "catalog": CATALOG,
            }
        )
    )
    if config is None:
        config = {
            "host": "db",
            "port": 5432,
            "username": "reader",
            "password": "test-only-secret",
            "database": "sales",
        }
    read_config = AsyncMock(return_value=config)
    return ConnectorToolService(repo, connections, read_config, AsyncMock(return_value=True))


@pytest.mark.asyncio
async def test_options_only_list_saved_instances_without_credentials():
    svc = service()
    result = await svc.list_options()
    assert result == [
        {
            "id": ID,
            "name": "Reporting",
            "connector_type": "postgres",
            "operations": ["list_resources", "read"],
            "unavailable_reason": None,
        }
    ]
    svc.read_config.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("connector", ["sharepoint", "outlook", "confluence", "source-postgres"])
async def test_connectors_without_a_live_adapter_are_unavailable(connector):
    option = (await service(connector).list_options())[0]
    assert option["operations"] == []
    assert option["unavailable_reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config,available",
    [
        ({"bootstrap_servers": "k:9092", "topics": ["t"]}, True),
        ({"bootstrap_servers": "k:9092", "topics": ["t"], "ssl_ca_pem": "-----BEGIN"}, False),
    ],
)
async def test_availability_of_config_dependent_connectors_is_decided_by_the_config(config, available):
    svc = service("kafka", config)
    assert bool((await svc.list_options())[0]["operations"]) is available
    svc.read_config.assert_awaited_once_with("owner-1", "config-1")


@pytest.mark.asyncio
async def test_rejects_unknown_instances_and_incompatible_base():
    svc = service()
    svc.repo.get_collection.return_value = None
    with pytest.raises(ValueError, match="not available"):
        await svc.validate_bindings(
            [{"datasource_id": ID, "operations": ["read"]}],
            base_agent="configurable-mcp-agent",
            user_id="user-1",
        )
    with pytest.raises(ValueError, match="configurable MCP"):
        await svc.validate_bindings(
            [{"datasource_id": ID, "operations": ["read"]}], base_agent="chatbot", user_id="user-1"
        )


@pytest.mark.asyncio
async def test_resolve_checks_saved_operation_before_reading_credentials():
    svc = service()
    persona = {
        "base_agent": "configurable-mcp-agent",
        "connector_bindings": [
            {"datasource_id": ID, "operations": ["list_resources"]},
        ],
    }
    with pytest.raises(PermissionError):
        await svc.resolve(persona, ID, "read")
    with pytest.raises(PermissionError):
        await svc.resolve(persona, OTHER, "list_resources")
    svc.read_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_hands_tools_service_its_adapter_shape_and_the_selected_streams():
    svc = service()
    result = await svc.resolve(PERSONA, ID, "read")

    assert result["connector_type"] == "source-postgres"
    assert result["config"] == {
        "host": "db",
        "port": 5432,
        "username": "reader",
        "password": "test-only-secret",
        "database": "sales",
        "ssl_mode": {"mode": "disable"},
    }
    assert result["streams"] == ["sales.orders"]
    svc.read_config.assert_awaited_once_with("owner-1", "config-1")


@pytest.mark.asyncio
async def test_resolve_reports_missing_credentials_without_exposing_anything():
    svc = service()
    svc.read_config.return_value = None
    with pytest.raises(ValueError, match="credentials"):
        await svc.resolve(PERSONA, ID, "read")

    svc.read_config.side_effect = RuntimeError("user-service said: password=hunter2")
    with pytest.raises(ValueError, match="could not be resolved") as error:
        await svc.resolve(PERSONA, ID, "read")
    assert "hunter2" not in str(error.value)


@pytest.mark.asyncio
async def test_assigning_connectors_requires_datasource_permission():
    svc = service()
    svc.check_permission.return_value = False
    with pytest.raises(PermissionError):
        await svc.validate_bindings(
            [{"datasource_id": ID, "operations": ["read"]}],
            base_agent="configurable-mcp-agent",
            user_id="user-1",
        )


@pytest.mark.asyncio
async def test_chat_binding_descriptions_include_names_without_source_configuration():
    svc = service()
    described = await svc.describe_bindings([{"datasource_id": ID, "operations": ["read"]}])
    assert described == [
        {
            "datasource_id": ID,
            "operations": ["read"],
            "name": "Reporting",
            "connector_type": "postgres",
        }
    ]
    svc.read_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_saved_collection_without_a_connection_is_unavailable():
    svc = service()
    svc.connections.get.return_value = None
    option = (await svc.list_options())[0]
    assert option["operations"] == []
    assert option["unavailable_reason"]
    with pytest.raises(ValueError, match="not available"):
        await svc.resolve(PERSONA, ID, "read")


# ---------------------------------------------------------------------------
# connector-py configuration -> tools-service adapter contract
# ---------------------------------------------------------------------------


def test_every_supported_connector_has_a_translator():
    assert SUPPORTED_CONNECTORS == {
        "postgres",
        "mysql",
        "mssql",
        "mongodb",
        "elasticsearch",
        "opensearch",
        "kafka",
        "s3",
        "minio",
        "sftp",
        "http_json",
    }
    assert to_tool_connector("confluence", {}) is None


def test_sql_translations_match_what_the_adapters_read():
    postgres = to_tool_connector("postgres", {"host": "h", "username": "u", "database": "d", "ssl": True})
    assert postgres.config["ssl_mode"] == {"mode": "require"}

    mysql = to_tool_connector("mysql", {"host": "h", "username": "u", "password": "p", "database": "d"})
    assert mysql.connector_type == "source-mysql" and mysql.config["ssl_mode"] == {"mode": "preferred"}

    base = {"host": "h", "username": "u", "password": "p", "database": "d"}
    assert to_tool_connector("mssql", {**base, "encrypt": False}).config["ssl_method"] == {
        "ssl_method": "unencrypted"
    }
    trusting = to_tool_connector("mssql", {**base, "encrypt": True, "trust_server_certificate": True})
    assert trusting.config["ssl_method"] == {"ssl_method": "encrypted_trust_server_certificate"}
    assert to_tool_connector("mssql", {**base, "encrypt": True}) is None, "verification is not implemented"
    assert to_tool_connector("mssql", {**base, "username": None, "encrypt": False}) is None


def test_document_and_search_translations():
    mongo = to_tool_connector("mongodb", {"connection_string": "mongodb://u:p@h/d", "database": "d"})
    assert mongo.connector_type == "source-mongodb-v2" and mongo.config["database"] == "d"

    with_key = to_tool_connector("elasticsearch", {"url": "https://es:9200", "api_key": "abc"})
    assert with_key.config == {"endpoint": "https://es:9200", "api_key": "abc"}
    basic = to_tool_connector("opensearch", {"url": "https://os:9200", "username": "u", "password": "p"})
    assert basic.connector_type == "source-opensearch"
    assert basic.config == {"endpoint": "https://os:9200", "username": "u", "password": "p"}


def test_kafka_translation_builds_the_jaas_string_the_adapter_parses():
    sasl = to_tool_connector(
        "kafka",
        {
            "bootstrap_servers": "k1:9092,k2:9092",
            "security_protocol": "SASL_SSL",
            "sasl_mechanism": "SCRAM-SHA-256",
            "sasl_username": "svc",
            "sasl_password": "p w",
        },
    )
    assert sasl.config == {
        "bootstrap_servers": "k1:9092,k2:9092",
        "protocol": {
            "security_protocol": "SASL_SSL",
            "sasl_mechanism": "SCRAM-SHA-256",
            "sasl_jaas_config": 'username="svc" password="p w"',
        },
    }
    assert to_tool_connector("kafka", {"security_protocol": "SASL_SSL", "sasl_username": "svc"}) is None
    quoted = {"security_protocol": "SASL_SSL", "sasl_username": "svc", "sasl_password": 'a"b'}
    assert to_tool_connector("kafka", quoted) is None


def test_object_store_translations_prefix_the_stream_globs():
    s3 = to_tool_connector(
        "s3",
        {
            "bucket": "b",
            "prefix": "docs/",
            "region": "eu-west-1",
            "aws_access_key_id": "AK",
            "aws_secret_access_key": "SK",
            "streams": [{"name": "reports", "glob": "**/*.csv"}],
        },
    )
    assert s3.connector_type == "source-s3" and s3.config["region_name"] == "eu-west-1"
    assert s3.config["streams"] == [{"name": "reports", "globs": ["docs/**/*.csv"]}]
    assert to_tool_connector("s3", {"bucket": "b"}) is None
    temporary = {"bucket": "b", "aws_access_key_id": "AK", "aws_session_token": "T"}
    assert to_tool_connector("s3", temporary) is None

    minio = to_tool_connector(
        "minio", {"bucket": "b", "endpoint": "minio:9000", "access_key": "AK", "secret_key": "SK"}
    )
    assert minio.connector_type == "source-s3" and minio.config["endpoint"] == "http://minio:9000"
    assert minio.config["streams"] == [{"name": "files", "globs": ["**"]}]


def test_sftp_and_http_translations():
    sftp = to_tool_connector(
        "sftp", {"host": "h", "username": "u", "password": "p", "paths": ["/data"], "glob": "**/*.json"}
    )
    assert sftp.connector_type == "source-sftp-bulk"
    assert sftp.config["folder_path"] == "/data" and sftp.config["password"] == "p"
    assert sftp.config["streams"] == [{"name": "files", "globs": ["**/*.json"]}]
    assert to_tool_connector("sftp", {"host": "h", "paths": ["/a", "/b"]}) is None

    http = to_tool_connector(
        "http_json",
        {"url": "https://api.acme.com/v1/items?active=1", "stream_name": "items", "bearer_token": "tok"},
    )
    assert http.connector_type == "source-http-request"
    assert http.config == {
        "base_url": "https://api.acme.com",
        "resources": {"items": "/v1/items?active=1"},
        "headers": {"Authorization": "Bearer tok"},
    }
    assert to_tool_connector("http_json", {"url": "https://api.acme.com/x", "method": "POST"}) is None
