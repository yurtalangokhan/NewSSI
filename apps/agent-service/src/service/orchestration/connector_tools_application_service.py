"""ConnectorTools application use cases."""

import asyncio

from error_contract import DependencyTimeoutError

from schemas.connector_tools import ConnectorResolveRequest
from service.orchestration.connector_tool_service import ConnectorToolService


class ConnectorToolsApplicationService:
    """Framework-free application use cases for this JSON surface."""

    def __init__(self, connector_service: ConnectorToolService, timeout_seconds: float):
        self.connector_service = connector_service
        self.timeout_seconds = timeout_seconds

    async def connector_options(self) -> list[dict]:
        return await self.connector_service.list_options()

    async def resolve_connector(self, body: ConnectorResolveRequest, user_id: str) -> dict:
        svc = self.connector_service
        resolve_fn = getattr(svc, "resolve_for_user", None) or getattr(svc, "resolve", None)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await resolve_fn(body.persona_id, str(body.datasource_id), body.operation, user_id)
        except TimeoutError:
            raise DependencyTimeoutError(
                message_key="connectors.timeout", headers={"Cache-Control": "no-store"}
            ) from None
