"""Test helpers: a routable fake HTTP API and a read-everything convenience."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from connector import ConfiguredCatalog, Record, State, SyncMode, SyncState
from connector.base import BaseSource

Route = Any  # JSON payload, httpx.Response, or callable(request) -> either


class FakeApi:
    """Routes by ``"METHOD /path"`` or plain ``"/path"``; unknown paths answer 404.

    The host is ignored, so the same fake serves sources that call several
    hosts (token endpoint + API).
    """

    def __init__(self, routes: dict[str, Route]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        route = self.routes.get(f"{request.method} {path}", self.routes.get(path))
        if route is None:
            return httpx.Response(404, json={"error": f"no route for {request.method} {path}"})
        result = route(request) if callable(route) else route
        return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)

    def client(self, base_url: str = "https://api.test") -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self), base_url=base_url)

    def calls(self, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == path]

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


def pages(*payloads: Any, key: Callable[[httpx.Request], bool] | None = None) -> Callable:
    """Return successive payloads on successive calls (the last one repeats)."""
    state = {"i": 0}

    def route(request: httpx.Request) -> Any:
        payload = payloads[min(state["i"], len(payloads) - 1)]
        state["i"] += 1
        return payload

    return route


async def read_all(
    source: BaseSource,
    *,
    only: list[str] | None = None,
    incremental: bool = False,
    state: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    """Discover + read; returns ``(records by stream, final state by stream)``."""
    catalog = await source.discover()
    configured = ConfiguredCatalog.from_catalog(
        catalog,
        sync_mode=SyncMode.INCREMENTAL if incremental else SyncMode.FULL_REFRESH,
        only=only,
    )
    records: dict[str, list[dict[str, Any]]] = {}
    states: dict[str, dict[str, Any]] = {}
    async for item in source.read(configured, SyncState(streams=state or {})):
        if isinstance(item, Record):
            records.setdefault(item.stream, []).append(item.data)
        elif isinstance(item, State):
            states[item.stream] = item.data
    return records, states
