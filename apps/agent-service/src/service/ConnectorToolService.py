"""Saved connector assignments and internal credential resolution."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from i18n import t
from pydantic import TypeAdapter

from models.connector_tools import ConnectorBinding

# Must match the tools-service connector adapter catalogue.
SUPPORTED_CONNECTORS = frozenset(
    {
        "source-postgres",
        "source-elasticsearch",
        "source-opensearch",
        "source-http-request",
        "source-mongodb-v2",
        "source-mongodb",
        "source-mysql",
        "source-mssql",
        "source-oracle",
        "source-s3",
        "source-sftp-bulk",
        "source-kafka",
        "source-microsoft-sharepoint",
        "source-outlook",
    }
)
OPERATIONS = ("list_resources", "read")


def _sharepoint_available(config: dict[str, Any]) -> bool:
    # Match the tools-service Microsoft adapter's supported native variants.
    credentials = config.get("credentials") or {}
    if (
        config.get("search_scope") != "ACCESSIBLE_DRIVES"
        or not isinstance(credentials, dict)
        or credentials.get("auth_type") not in {"Client", "Service"}
        or not config.get("streams")
    ):
        return False
    site_url = config.get("site_url") or ""
    if not isinstance(site_url, str):
        return False
    site_url = site_url.strip()
    if not site_url:
        return True
    parsed = urlsplit(site_url)
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").endswith(".sharepoint.com")
        and parsed.path.startswith("/sites/")
        and ".." not in parsed.path.split("/")
        and parsed.port in {None, 443}
        and bool(parsed.path.removeprefix("/sites/").strip("/"))
        and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
    )


def _contains_unresolved_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return "_secret" in value or any(_contains_unresolved_secret(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_unresolved_secret(v) for v in value)
    return isinstance(value, str) and len(value) >= 3 and set(value) == {"*"}


async def _can_assign(user_id: str) -> bool:
    if user_id == "dev-user":
        return True
    from service.AuthorizationClient import get_authorization_client

    return await get_authorization_client().has_permission(user_id, "datasource:read")


class ConnectorToolService:
    """Use saved instance identifiers; never accept caller-supplied credentials."""

    def __init__(
        self,
        repo: Any,
        mappings: Any,
        client: Any,
        check_permission: Any = _can_assign,
        configuration_reader: Any = None,
    ):
        self.repo = repo
        self.mappings = mappings
        self.client = client
        self.check_permission = check_permission
        self.configuration_reader = configuration_reader

    async def _is_available(self, row: dict[str, Any]) -> bool:
        connector_type = row["cmetadata"].get("connector_type", "")
        if connector_type not in SUPPORTED_CONNECTORS:
            return False
        mapping = await self.mappings.get(str(row["uuid"]))
        if not mapping:
            return False
        if connector_type in {"source-http-request", "source-microsoft-sharepoint", "source-mysql"}:
            # Custom REST connectors need an explicit resource map; a type
            # label alone does not make an arbitrary Airbyte source callable.
            try:
                source = await self.client.get_source(mapping["airbyte_source_id"])
                config = source.get("connectionConfiguration") or {}
                if connector_type == "source-microsoft-sharepoint":
                    return _sharepoint_available(config)
                if connector_type == "source-mysql":
                    return (config.get("ssl_mode") or {}).get("mode", "preferred") == "preferred"
                resources = config.get("resources")
                return bool(config.get("base_url") or config.get("url")) and bool(
                    isinstance(resources, dict)
                    and resources
                    and all(isinstance(path, str) for path in resources.values())
                )
            except Exception:
                return False
        return True

    async def list_options(self) -> list[dict[str, Any]]:
        options = []
        for row in await self.repo.list_datasource_collections():
            connector_type = row["cmetadata"].get("connector_type", "")
            supported = await self._is_available(row)
            options.append(
                {
                    "id": str(row["uuid"]),
                    "name": row["name"],
                    "connector_type": connector_type,
                    "operations": list(OPERATIONS) if supported else [],
                    "unavailable_reason": None
                    if supported
                    else t(
                        "connectors.unsupported",
                        default="Live tools are not available for this connector.",
                    ),
                }
            )
        return options

    async def describe_bindings(self, bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        described = []
        for binding in bindings:
            row = await self.repo.get_collection(binding["datasource_id"])
            described.append(
                {
                    **binding,
                    "name": row["name"] if row else "Unavailable connector",
                    "connector_type": row["cmetadata"].get("connector_type", "") if row else "",
                }
            )
        return described

    async def validate_bindings(
        self, bindings: list[dict[str, Any]], *, base_agent: str | None, user_id: str
    ) -> list[dict[str, Any]]:
        if not bindings:
            return []
        if base_agent != "configurable-mcp-agent":
            raise ValueError(
                t(
                    "connectors.base_required",
                    default="Connectors require a configurable MCP agent.",
                )
            )
        if not await self.check_permission(user_id):
            raise PermissionError(
                t("connectors.assignment_denied", default="Connector assignment is not permitted.")
            )
        parsed = TypeAdapter(list[ConnectorBinding]).validate_python(bindings)
        if len(parsed) > 32 or len({b.datasource_id for b in parsed}) != len(parsed):
            raise ValueError(
                t("connectors.invalid_bindings", default="Select at most 32 distinct connectors.")
            )
        for binding in parsed:
            row = await self.repo.get_collection(binding.datasource_id)
            if not row or not await self._is_available(row):
                raise ValueError(
                    t(
                        "connectors.unavailable",
                        default="Selected connector is not available for live tools.",
                    )
                )
        return [binding.model_dump() for binding in parsed]

    async def resolve(
        self, persona: dict[str, Any], datasource_id: str, operation: str
    ) -> dict[str, Any]:
        if (
            persona.get("base_agent") != "configurable-mcp-agent"
            or not any(
                b.get("datasource_id") == datasource_id and operation in b.get("operations", [])
                for b in persona.get("connector_bindings") or []
            )
            or operation not in OPERATIONS
        ):
            raise PermissionError(
                t(
                    "connectors.not_assigned",
                    default="Connector operation is not assigned to this agent.",
                )
            )
        row = await self.repo.get_collection(datasource_id)
        mapping = await self.mappings.get(datasource_id)
        if (
            not row
            or not mapping
            or row["cmetadata"].get("connector_type") not in SUPPORTED_CONNECTORS
        ):
            raise ValueError(
                t(
                    "connectors.unavailable",
                    default="Selected connector is not available for live tools.",
                )
            )
        try:
            source = await self.client.get_source(mapping["airbyte_source_id"])
            connection = await self.client.get_connection(mapping["airbyte_connection_id"])
        except Exception:
            raise ValueError(
                t(
                    "connectors.source_unavailable",
                    default="The saved connector could not be resolved.",
                )
            ) from None
        config = source.get("connectionConfiguration")
        if (
            isinstance(config, dict)
            and _contains_unresolved_secret(config)
            and self.configuration_reader
        ):
            try:
                config = await self.configuration_reader(mapping["airbyte_source_id"])
            except Exception:
                raise ValueError(
                    t(
                        "connectors.credentials_unavailable",
                        default="Saved connector credentials are unavailable for live tools.",
                    )
                ) from None
        if not isinstance(config, dict) or _contains_unresolved_secret(config):
            raise ValueError(
                t(
                    "connectors.credentials_unavailable",
                    default="Saved connector credentials are unavailable for live tools.",
                )
            )
        selected_names = row["cmetadata"].get("streams")
        streams = []
        for item in connection.get("syncCatalog", {}).get("streams", []):
            stream = item.get("stream", {})
            name = stream.get("name")
            if not name or not item.get("config", {}).get("selected", False):
                continue
            if selected_names and name not in selected_names:
                continue
            namespace = stream.get("namespace")
            streams.append(f"{namespace}.{name}" if namespace else name)
        return {
            "id": datasource_id,
            "name": row["name"],
            "connector_type": row["cmetadata"]["connector_type"],
            "config": config,
            "streams": streams,
        }


def get_connector_tool_service() -> ConnectorToolService:
    from core.db.repositories.datasource_repo import DatasourceRepository
    from repository.airbyte_mapping_repository import AirbyteMappingDB
    from service.AirbyteApiClientService import get_airbyte_client

    async def read_configuration(source_id: str) -> dict[str, Any] | None:
        from repository.airbyte_source_configuration_repository import (
            get_airbyte_source_configuration_repository,
        )

        return await get_airbyte_source_configuration_repository().get_source_configuration(
            source_id
        )

    return ConnectorToolService(
        DatasourceRepository(),
        AirbyteMappingDB,
        get_airbyte_client(),
        configuration_reader=read_configuration,
    )
