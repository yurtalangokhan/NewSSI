"""Saved connector assignments and internal credential resolution."""

from __future__ import annotations

from typing import Any

from connector import ConfiguredCatalog
from localization import t
from pydantic import TypeAdapter

from core.exceptions import BadRequestError, ForbiddenError
from infrastructure.db.persistence_gateway import (
    datasource_connection_repository,
    datasource_repository,
)
from schemas.connector_tools import ConnectorBinding
from service.ingest.connector_stores import read_stored_config
from service.orchestration.connector_tool_contract import (
    ALWAYS_AVAILABLE,
    SUPPORTED_CONNECTORS,
    to_tool_connector,
)
from service.personas.persona_access import get_persona_access_policy

OPERATIONS = ("list_resources", "read")


async def _can_assign(user_id: str) -> bool:
    if user_id == "dev-user":
        return True
    from integrations.authorization_client import get_authorization_client

    return await get_authorization_client().has_permission(user_id, "datasource:read")


class ConnectorToolService:
    """Use saved instance identifiers; never accept caller-supplied credentials.

    ``connections`` is the ``datasource_connections`` repository and
    ``read_config`` resolves ``(owner_user_id, config_id)`` to the decrypted
    configuration stored in user-service. Both are only consulted for a
    datasource an agent is actually bound to.
    """

    def __init__(
        self,
        repo: Any = None,
        connections: Any = None,
        read_config: Any = None,
        check_permission: Any = _can_assign,
        service: Any = None,
        access_policy: Any = None,
    ):
        if read_config is None and connections is not None and not hasattr(connections, "get"):
            # Invoked as ConnectorToolService(service, access_policy)
            self._underlying_service = repo
            self._access_policy = connections
            self.repo = getattr(repo, "repo", None)
            self.connections = getattr(repo, "connections", None)
            self.read_config = getattr(repo, "read_config", None)
            self.check_permission = getattr(repo, "check_permission", _can_assign)
        else:
            self._underlying_service = service
            self._access_policy = access_policy
            self.repo = repo
            self.connections = connections
            self.read_config = read_config
            self.check_permission = check_permission

    async def _is_available(self, row: dict[str, Any]) -> bool:
        connection = await self.connections.get(str(row["uuid"]))
        if not connection:
            return False
        connector_name = connection["connector_name"]
        if connector_name not in SUPPORTED_CONNECTORS:
            return False
        if connector_name in ALWAYS_AVAILABLE:
            return True
        # Whether the live adapter can read these depends on how they are
        # configured (TLS mode, credential kind, number of roots).
        try:
            config = await self.read_config(connection["owner_user_id"], connection["config_id"])
        except Exception:
            return False
        return isinstance(config, dict) and to_tool_connector(connector_name, config) is not None

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
            raise PermissionError(t("connectors.assignment_denied", default="Connector assignment is not permitted."))
        parsed = TypeAdapter(list[ConnectorBinding]).validate_python(bindings)
        if len(parsed) > 32 or len({b.datasource_id for b in parsed}) != len(parsed):
            raise ValueError(t("connectors.invalid_bindings", default="Select at most 32 distinct connectors."))
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
        self,
        persona_or_id: Any,
        datasource_id: str,
        operation: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if user_id is not None or not isinstance(persona_or_id, dict):
            return await self.resolve_for_user(persona_or_id, datasource_id, operation, user_id or "")
        persona = persona_or_id
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
        connection = await self.connections.get(datasource_id)
        if not row or not connection or connection["connector_name"] not in SUPPORTED_CONNECTORS:
            raise ValueError(
                t(
                    "connectors.unavailable",
                    default="Selected connector is not available for live tools.",
                )
            )
        try:
            config = await self.read_config(connection["owner_user_id"], connection["config_id"])
        except Exception:
            raise ValueError(
                t(
                    "connectors.source_unavailable",
                    default="The saved connector could not be resolved.",
                )
            ) from None
        if not isinstance(config, dict):
            raise ValueError(
                t(
                    "connectors.credentials_unavailable",
                    default="Saved connector credentials are unavailable for live tools.",
                )
            )
        tool_connector = to_tool_connector(connection["connector_name"], config)
        if tool_connector is None:
            raise ValueError(
                t(
                    "connectors.unavailable",
                    default="Selected connector is not available for live tools.",
                )
            )
        catalog = ConfiguredCatalog.model_validate(connection.get("catalog") or {})
        return {
            "id": datasource_id,
            "name": row["name"],
            "connector_type": tool_connector.connector_type,
            "config": tool_connector.config,
            "streams": catalog.names(),
        }

    async def resolve_for_user(
        self, persona_id: int, datasource_id: str, operation: str, user_id: str
    ) -> dict[str, Any]:
        from infrastructure.db.persistence_gateway import persona_repository
        from service.auth.auth_service import AuthenticatedUser

        persona = await persona_repository().get(persona_id)
        if not persona:
            raise ForbiddenError(message_key="connectors.access_denied")
        user = AuthenticatedUser(user_id=user_id, email="")
        access = getattr(self, "_access_policy", None) or get_persona_access_policy()
        restricted, accessible = await access.load_visibility(user)
        can_manage = await access.can_manage_all(user)
        if not access.can_access(persona, user, restricted, accessible, can_manage):
            raise ForbiddenError(message_key="connectors.access_denied")
        try:
            target = getattr(self, "_underlying_service", None) or self
            return await target.resolve(persona, datasource_id, operation)
        except PermissionError as exc:
            raise ForbiddenError(message_key="connectors.access_denied") from exc
        except ValueError as exc:
            raise BadRequestError(message_key="common.bad_request") from exc


def get_connector_tool_service() -> ConnectorToolService:
    return ConnectorToolService(
        datasource_repository(),
        datasource_connection_repository(),
        read_stored_config,
    )
