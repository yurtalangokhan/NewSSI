from __future__ import annotations

from dataclasses import asdict
from typing import Any

from error_contract import (
    BadRequestError,
    NotFoundError,
)

from core.exceptions import UnknownComponentError, UnknownOptionsSourceError
from service.auth.auth_service import AuthenticatedUser
from service.flows.resolvers import ResolverContext
from service.flows.service import FlowService


class FlowComponentsApplicationService:
    """Framework-free use cases for this JSON surface."""

    def __init__(self, service: FlowService | None = None):
        self.domain_service = service if service is not None else FlowService()

    async def list_components(self) -> dict[str, list[dict[str, Any]]]:
        """List every registered component template, grouped by category."""
        grouped = self.domain_service.list_components()
        return {
            category: [template.model_dump(mode="json") for template in templates]
            for category, templates in grouped.items()
        }

    async def resolve_component_options(
        self, source: str, user: AuthenticatedUser, dep: list[str] | None = None
    ) -> dict[str, Any]:
        """Resolve a dynamic options_source for the calling user.

        ``dep`` carries the sibling values a source declares in
        ``InputField.depends_on``, one ``name:value`` pair per entry — the chosen
        provider narrows ``llm.models``, for instance. They ride in the query
        string so the response stays cacheable by URL. A malformed entry is
        ignored rather than rejected: a dropdown must not 400 because the canvas
        sent something odd.
        """
        if dep is None:
            dep = []
        depends: dict[str, str] = {}
        for entry in dep:
            name, separator, value = entry.partition(":")
            if separator and name.strip():
                depends[name.strip()] = value.strip()
        try:
            result = await self.domain_service.resolve_options(
                source, ResolverContext(user_id=user.user_id, access_token=user.access_token, depends=depends)
            )
        except UnknownOptionsSourceError as exc:
            raise BadRequestError(
                message_key="flow.unknown_options_source", message_params={"source": exc.source}
            ) from exc
        return {
            "source": result.source,
            "available": result.available,
            "items": [asdict(item) for item in result.items],
        }

    async def get_component(self, component_type: str) -> dict[str, Any]:
        """Get a single component template by type."""
        try:
            template = self.domain_service.get_component(component_type)
        except UnknownComponentError as exc:
            raise NotFoundError(
                message_key="flow.unknown_component", message_params={"component_type": exc.component_type}
            ) from exc
        return template.model_dump(mode="json")
