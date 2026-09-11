from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ID = "e22ef0bf-3c16-4591-a254-7c48cb16fc55"
OTHER = "e22ef0bf-3c16-4591-a254-7c48cb16fc56"


def service():
    from service.ConnectorToolService import ConnectorToolService

    row = {
        "uuid": ID,
        "name": "Reporting",
        "cmetadata": {
            "connector_type": "source-postgres",
            "streams": ["orders"],
        },
    }
    repo = SimpleNamespace(
        get_collection=AsyncMock(return_value=row),
        list_datasource_collections=AsyncMock(return_value=[row]),
    )
    mappings = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "airbyte_source_id": "source-1",
                "airbyte_connection_id": "connection-1",
            }
        )
    )
    client = SimpleNamespace(
        get_source=AsyncMock(
            return_value={
                "connectionConfiguration": {
                    "host": "db",
                    "port": 5432,
                    "password": "test-only-secret",
                }
            }
        ),
        get_connection=AsyncMock(
            return_value={
                "syncCatalog": {
                    "streams": [
                        {
                            "stream": {"name": "orders", "namespace": "sales"},
                            "config": {"selected": True},
                        }
                    ]
                }
            }
        ),
    )
    return ConnectorToolService(repo, mappings, client, AsyncMock(return_value=True))


@pytest.mark.asyncio
async def test_options_only_list_saved_instances_without_credentials():
    result = await service().list_options()
    assert result == [
        {
            "id": ID,
            "name": "Reporting",
            "connector_type": "source-postgres",
            "operations": ["list_resources", "read"],
            "unavailable_reason": None,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "connector_type", ["source-kafka", "source-microsoft-sharepoint", "source-outlook"]
)
async def test_options_include_saved_kafka_and_microsoft_instances(connector_type):
    svc = service()
    svc.repo.list_datasource_collections.return_value[0]["cmetadata"]["connector_type"] = (
        connector_type
    )
    svc.client.get_source.return_value = {
        "connectionConfiguration": {
            "search_scope": "ACCESSIBLE_DRIVES",
            "site_url": "",
            "credentials": {"auth_type": "Client"},
            "streams": [{"name": "files"}],
        }
    }
    result = await svc.list_options()
    assert result[0]["operations"] == ["list_resources", "read"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["SHARED_ITEMS", "ALL", None])
async def test_sharepoint_unsupported_search_scope_is_unavailable(scope):
    svc = service()
    svc.repo.list_datasource_collections.return_value[0]["cmetadata"]["connector_type"] = (
        "source-microsoft-sharepoint"
    )
    svc.client.get_source.return_value = {
        "connectionConfiguration": {
            "search_scope": scope,
            "credentials": {"auth_type": "Client"},
            "streams": [{"name": "files"}],
        }
    }
    assert (await svc.list_options())[0]["operations"] == []


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
    svc.client.get_source.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_reuses_saved_source_and_catalog_namespace():
    svc = service()
    result = await svc.resolve(
        {
            "base_agent": "configurable-mcp-agent",
            "connector_bindings": [
                {"datasource_id": ID, "operations": ["read"]},
            ],
        },
        ID,
        "read",
    )
    assert result["config"]["password"] == "test-only-secret"
    assert result["streams"] == ["sales.orders"]
    svc.client.get_source.assert_awaited_once_with("source-1")


@pytest.mark.asyncio
async def test_resolve_rejects_masked_credentials_without_exposing_config():
    svc = service()
    svc.client.get_source.return_value = {"connectionConfiguration": {"password": "**********"}}
    with pytest.raises(ValueError, match="credentials") as error:
        await svc.resolve(
            {
                "base_agent": "configurable-mcp-agent",
                "connector_bindings": [
                    {"datasource_id": ID, "operations": ["read"]},
                ],
            },
            ID,
            "read",
        )
    assert "**********" not in str(error.value)


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
async def test_masked_api_config_reuses_complete_saved_airbyte_configuration():
    svc = service()
    svc.client.get_source.return_value = {"connectionConfiguration": {"password": "**********"}}
    svc.configuration_reader = AsyncMock(return_value={"password": "existing-test-secret"})
    result = await svc.resolve(
        {
            "base_agent": "configurable-mcp-agent",
            "connector_bindings": [
                {"datasource_id": ID, "operations": ["read"]},
            ],
        },
        ID,
        "read",
    )
    assert result["config"] == {"password": "existing-test-secret"}
    svc.configuration_reader.assert_awaited_once_with("source-1")


@pytest.mark.asyncio
async def test_chat_binding_descriptions_include_names_without_source_configuration():
    svc = service()
    described = await svc.describe_bindings([{"datasource_id": ID, "operations": ["read"]}])
    assert described == [
        {
            "datasource_id": ID,
            "operations": ["read"],
            "name": "Reporting",
            "connector_type": "source-postgres",
        }
    ]
    svc.client.get_source.assert_not_awaited()


@pytest.mark.asyncio
async def test_custom_http_connector_without_resource_map_is_not_advertised():
    svc = service()
    svc.repo.list_datasource_collections.return_value[0]["cmetadata"]["connector_type"] = (
        "source-http-request"
    )
    options = await svc.list_options()
    assert options[0]["operations"] == []
    assert options[0]["unavailable_reason"]


@pytest.mark.asyncio
async def test_saved_collection_without_airbyte_mapping_is_unavailable():
    svc = service()
    svc.mappings.get.return_value = None
    option = (await svc.list_options())[0]
    assert option["operations"] == []
    assert option["unavailable_reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,available", [("preferred", True), ("required", False)])
async def test_mysql_tls_eligibility_matches_runtime(mode, available):
    svc = service()
    svc.repo.list_datasource_collections.return_value[0]["cmetadata"]["connector_type"] = (
        "source-mysql"
    )
    svc.client.get_source.return_value = {"connectionConfiguration": {"ssl_mode": {"mode": mode}}}
    assert bool((await svc.list_options())[0]["operations"]) is available
