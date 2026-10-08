"""GraphQL plumbing for sources whose API is a single ``/graphql`` endpoint
(Linear, Slab, Fireflies).

Provides query execution with GraphQL-level error handling and a generator for
Relay-style connections (``nodes`` + ``pageInfo { hasNextPage endCursor }``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel

from ..errors import SourceError
from ..models import CheckResult, SyncMode
from .declarative import dig
from .rest_source import RestSource

ConfigT = TypeVar("ConfigT", bound=BaseModel)


class GraphQLError(SourceError):
    """The server answered 200 with an ``errors`` array."""


class GraphQLSource(RestSource[ConfigT]):
    graphql_path: ClassVar[str] = "/graphql"
    check_query: ClassVar[str] = "{ __typename }"

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    async def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = await self.post_json(
            self.graphql_path, {"query": query, "variables": variables or {}}
        )
        errors = (payload or {}).get("errors")
        if errors:
            message = "; ".join(str(e.get("message", e)) for e in errors)
            raise GraphQLError(message)
        return (payload or {}).get("data") or {}

    async def connection(
        self,
        query: str,
        path: str,
        variables: dict[str, Any] | None = None,
        *,
        cursor_variable: str = "after",
        max_pages: int = 100_000,
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate a Relay connection found at ``path`` (dot path inside ``data``)."""
        variables = dict(variables or {})
        for _ in range(max_pages):
            data = await self.execute(query, variables)
            conn = dig(data, path) or {}
            for node in conn.get("nodes") or [e.get("node") for e in conn.get("edges") or []]:
                if isinstance(node, dict):
                    yield node
            info = conn.get("pageInfo") or {}
            if not info.get("hasNextPage") or not info.get("endCursor"):
                return
            variables[cursor_variable] = info["endCursor"]

    async def check(self) -> CheckResult:
        try:
            await self.execute(self.check_query)
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)
