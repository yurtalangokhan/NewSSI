"""Shared authentication pieces and the Microsoft Graph delta reader."""

from __future__ import annotations

import base64
from typing import Any

import httpx
import pytest

from connector import SourceError
from connector.common.microsoft_graph import (
    GraphConfigBase,
    GraphSource,
    drive_item_record,
    identity_name,
    keep_drive_item,
)
from connector.common.oauth2 import OAuth2BearerMixin, OAuth2Token
from connector.common.rest_source import RestSource, basic_auth_header
from connector.models import Catalog, ConnectorDefinition, ConnectorKind

# ---- OAuth2Token ------------------------------------------------------------------------


def _client(handler) -> httpx.AsyncClient:  # noqa: ANN001
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test")


async def test_token_is_fetched_once_and_cached() -> None:
    calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"access_token": "T1", "expires_in": 3600})

    token = OAuth2Token("https://login.test/token", {"grant_type": "x", "scope": None})
    async with _client(handler) as client:
        assert await token.get(client) == "T1"
        assert await token.get(client) == "T1"
        assert calls == [{"grant_type": "x"}]  # one request; None values are not sent

        token.invalidate()
        await token.get(client)
        assert len(calls) == 2


async def test_form_may_be_built_per_request() -> None:
    seen: list[str] = []
    counter = iter(range(1, 10))

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(httpx.QueryParams(request.content.decode())["assertion"])
        return httpx.Response(200, json={"access_token": "T", "expires_in": 3600})

    token = OAuth2Token("https://login.test/token", lambda: {"assertion": f"jwt-{next(counter)}"})
    async with _client(handler) as client:
        await token.get(client)
        token.invalidate()
        await token.get(client)
    assert seen == ["jwt-1", "jwt-2"]  # a fresh assertion for every token request


async def test_transient_failures_are_retried_and_rejections_are_not() -> None:
    statuses = iter([503, 200])
    attempts: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        attempts.append(status)
        return httpx.Response(status, json={"access_token": "T"} if status == 200 else {})

    token = OAuth2Token("https://login.test/token", {})
    token.retry_delay = 0
    async with _client(flaky) as client:
        assert await token.get(client) == "T"
    assert attempts == [503, 200]

    rejected: list[int] = []

    def denied(request: httpx.Request) -> httpx.Response:
        rejected.append(1)
        return httpx.Response(401, text="invalid_client")

    token = OAuth2Token("https://login.test/token", {})
    async with _client(denied) as client:
        with pytest.raises(SourceError, match="token request failed: 401 invalid_client"):
            await token.get(client)
    assert rejected == [1]  # bad credentials are not asked about again


async def test_a_response_without_a_token_is_an_error() -> None:
    token = OAuth2Token("https://login.test/token", {})
    async with _client(lambda r: httpx.Response(200, json={"error": "nope"})) as client:
        with pytest.raises(SourceError, match="no 'access_token'"):
            await token.get(client)


async def test_a_token_answer_that_is_not_json_is_a_source_error() -> None:
    # A proxy's login page, a captive portal: 200 and HTML.
    token = OAuth2Token("https://login.test/token", {"client_secret": "S3CRET"})
    async with _client(lambda r: httpx.Response(200, text="<html>Sign in</html>")) as client:
        with pytest.raises(SourceError, match="token request failed: .*not JSON") as failed:
            await token.get(client)
    assert "Sign in" not in str(failed.value) and "S3CRET" not in str(failed.value)


# ---- bearer mixin ---------------------------------------------------------------------------


class _Config(GraphConfigBase):
    access_token: str | None = None


class _Api(OAuth2BearerMixin, RestSource[_Config]):
    definition = ConnectorDefinition(name="api", display_name="Api", kind=ConnectorKind.SOURCE)
    Config = _Config

    def base_url(self) -> str:
        return "https://api.test"

    def static_token(self) -> str | None:
        return self.config.access_token

    def oauth2_token(self) -> OAuth2Token:
        return OAuth2Token("https://login.test/token", {"grant_type": "client_credentials"})

    async def discover(self) -> Catalog:
        return Catalog()

    def read(self, catalog: Any, state: Any = None) -> Any:
        raise NotImplementedError


async def test_mixin_prefers_a_configured_token_over_fetching_one() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers.get("Authorization")))
        if request.url.host == "login.test":
            return httpx.Response(200, json={"access_token": "FETCHED"})
        return httpx.Response(200, json={})

    base = {"tenant_id": "t", "client_id": "c", "client_secret": "s"}
    fixed = _Api(_Api.validate_config({**base, "access_token": "FIXED"}), client=_client(handler))
    await fixed.get_json("/x")
    assert seen == [("api.test", "Bearer FIXED")]

    seen.clear()
    fetched = _Api(_Api.validate_config(base), client=_client(handler))
    await fetched.get_json("/x")
    await fetched.get_json("/y")
    assert [host for host, _ in seen] == ["login.test", "api.test", "api.test"]
    assert seen[-1][1] == "Bearer FETCHED"


def test_basic_auth_header() -> None:
    header = basic_auth_header("user@example.com", "p:w")
    assert header == {
        "Authorization": "Basic " + base64.b64encode(b"user@example.com:p:w").decode()
    }


# ---- Graph delta queries ------------------------------------------------------------------------


class _Graph(GraphSource[GraphConfigBase]):
    definition = ConnectorDefinition(name="graph", display_name="G", kind=ConnectorKind.SOURCE)
    Config = GraphConfigBase

    async def discover(self) -> Catalog:
        return Catalog()

    def read(self, catalog: Any, state: Any = None) -> Any:
        raise NotImplementedError


def _graph(pages: dict[str, dict[str, Any]], requested: list[str]) -> _Graph:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "T", "expires_in": 3600})
        query = request.url.query.decode()
        requested.append(request.url.path + (f"?{query}" if query else ""))
        return httpx.Response(200, json=pages[requested[-1]])

    config = _Graph.validate_config({"tenant_id": "t", "client_id": "c", "client_secret": "s"})
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://graph.microsoft.com/v1.0"
    )
    return _Graph(config, client=client)


PAGES = {
    "/v1.0/drives/d/root/delta": {
        "value": [{"id": "1"}, {"id": "2"}],
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/drives/d/root/delta?page=2",
    },
    "/v1.0/drives/d/root/delta?page=2": {
        "value": [{"id": "3"}],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/drives/d/root/delta?token=next",
    },
}


async def test_delta_query_streams_pages_and_exposes_the_link_at_the_end() -> None:
    requested: list[str] = []
    changes = _graph(PAGES, requested).delta("/drives/d/root/delta")

    seen: list[str] = []
    async for item in changes:
        seen.append(item["id"])
        if item["id"] == "1":
            # The second page has not been requested while the first is being consumed.
            assert requested == ["/v1.0/drives/d/root/delta"]
            assert changes.delta_link is None
    assert seen == ["1", "2", "3"]
    assert changes.delta_link == "https://graph.microsoft.com/v1.0/drives/d/root/delta?token=next"


async def test_an_abandoned_delta_query_has_no_link_to_save() -> None:
    requested: list[str] = []
    changes = _graph(PAGES, requested).delta("/drives/d/root/delta")
    async for _item in changes:
        break
    assert changes.delta_link is None and len(requested) == 1


def _expiring_graph(requested: list[str], *, gone: str) -> _Graph:
    """``PAGES``, except that the request ``gone`` is answered 410."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "T", "expires_in": 3600})
        query = request.url.query.decode()
        requested.append(request.url.path + (f"?{query}" if query else ""))
        if requested[-1] == gone:
            return httpx.Response(410, json={"error": {"code": "resyncRequired"}})
        return httpx.Response(200, json=PAGES[requested[-1]])

    config = _Graph.validate_config({"tenant_id": "t", "client_id": "c", "client_secret": "s"})
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://graph.microsoft.com/v1.0"
    )
    return _Graph(config, client=client)


async def test_a_delta_link_the_service_forgot_starts_the_query_over() -> None:
    requested: list[str] = []
    stale = "https://graph.microsoft.com/v1.0/drives/d/root/delta?token=old"
    graph = _expiring_graph(requested, gone="/v1.0/drives/d/root/delta?token=old")

    changes = graph.delta("/drives/d/root/delta", resume_from=stale)

    assert [item["id"] async for item in changes] == ["1", "2", "3"]
    assert requested[:2] == ["/v1.0/drives/d/root/delta?token=old", "/v1.0/drives/d/root/delta"]
    assert changes.delta_link == "https://graph.microsoft.com/v1.0/drives/d/root/delta?token=next"


async def test_a_410_anywhere_else_is_an_error() -> None:
    # Half way through a query there is nothing to start over from without repeating
    # what was already delivered; and a query without a stored link has no excuse.
    graph = _expiring_graph([], gone="/v1.0/drives/d/root/delta?page=2")
    with pytest.raises(httpx.HTTPStatusError, match="410"):
        [item async for item in graph.delta("/drives/d/root/delta")]

    graph = _expiring_graph([], gone="/v1.0/drives/d/root/delta")
    with pytest.raises(httpx.HTTPStatusError, match="410"):
        [item async for item in graph.delta("/drives/d/root/delta")]


# ---- drive items ------------------------------------------------------------------------------


def test_drive_item_filtering_and_mapping() -> None:
    root = {"id": "r", "name": "root", "root": {}, "folder": {}}
    folder = {"id": "f", "name": "Docs", "folder": {"childCount": 1}}
    pdf = {
        "id": "p",
        "name": "Report.PDF",
        "size": 10,
        "file": {"mimeType": "application/pdf"},
        "parentReference": {"driveId": "d1", "path": "/drive/root:/Docs"},
        "webUrl": "https://sp/Report.PDF",
        "createdBy": {"user": {"displayName": "Ada"}},
        "lastModifiedBy": {"user": {"email": "bob@example.com"}},
        "lastModifiedDateTime": "2026-01-02T03:04:05Z",
    }
    txt = {"id": "t", "name": "notes.txt", "file": {}}

    def keep(raw: dict[str, Any], folders: bool = False, ext: list[str] | None = None) -> bool:
        return keep_drive_item(raw, include_folders=folders, file_extensions=ext)

    assert not keep(root, folders=True)
    assert keep(folder, folders=True) and not keep(folder)
    assert keep(pdf, ext=[".pdf"]) and not keep(txt, ext=["pdf"]) and keep(txt)

    assert drive_item_record(pdf) == {
        "id": "p",
        "drive_id": "d1",
        "name": "Report.PDF",
        "path": "/drive/root:/Docs/Report.PDF",
        "is_folder": False,
        "size": 10,
        "mime_type": "application/pdf",
        "web_url": "https://sp/Report.PDF",
        "download_url": None,
        "deleted": False,
        "created_by": "Ada",
        "last_modified_by": "bob@example.com",
        "last_modified": "2026-01-02T03:04:05Z",
    }
    assert identity_name(None) is None and identity_name({"user": {}}) is None
