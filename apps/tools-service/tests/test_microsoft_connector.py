import json
from functools import partial

import httpx
import pytest

from src.connectors.microsoft import MicrosoftConnectorError, read_microsoft_connector


def config(**changes):
    return {
        "credentials": {
            "auth_type": "Client",
            "tenant_id": "tenant",
            "client_id": "id",
            "client_secret": "secret",
            "refresh_token": "refresh",
        },
        "site_url": "https://tenant.sharepoint.com/sites/Finance",
        "search_scope": "ACCESSIBLE_DRIVES",
        "folder_path": "Reports",
        "streams": [{"name": "reports", "globs": ["**/*.csv"]}],
        **changes,
    }


async def run(cfg, query="", handler=None):
    calls = []

    def dispatch(request):
        calls.append(request)
        if handler:
            result = handler(request)
            if result is not None:
                return result
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "token"})
        if "/sites/tenant" in str(request.url):
            return httpx.Response(200, json={"id": "site"})
        if request.url.path.endswith("/drives"):
            return httpx.Response(200, json={"value": [{"id": "drive1"}, {"id": "drive2"}]})
        return httpx.Response(200, json={"value": []})

    rows = await read_microsoft_connector(
        "source-microsoft-sharepoint",
        cfg,
        "reports",
        query=query,
        limit=10,
        client_factory=partial(httpx.AsyncClient, transport=httpx.MockTransport(dispatch)),
    )
    return rows, calls


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["SHARED_ITEMS", "ALL"])
async def test_unsupported_scope_denied_before_network(scope):
    def no_network(request):
        pytest.fail("unsupported scope reached network")

    with pytest.raises(MicrosoftConnectorError):
        await run(config(search_scope=scope), handler=no_network)


@pytest.mark.asyncio
async def test_selected_drive_and_stream_path_used_with_native_client_credentials():
    def response(request):
        if request.url.path.endswith(":/content"):
            assert "/drives/drive2/" in request.url.path
            return httpx.Response(200, content=b"hello")

    cfg = config()
    cfg["credentials"].pop("refresh_token")
    rows, calls = await run(cfg, json.dumps({"drive_id": "drive2", "path": "year/a.csv"}), response)
    assert rows[0]["content"] == "hello"
    assert rows[0]["path"] == "year/a.csv"
    assert b"grant_type=client_credentials" in calls[0].content


@pytest.mark.asyncio
async def test_glob_does_not_cross_directory_boundaries():
    with pytest.raises(MicrosoftConnectorError):
        await run(
            config(streams=[{"name": "reports", "globs": ["public/*.csv"]}]),
            json.dumps({"drive_id": "drive1", "path": "public/private/a.csv"}),
        )


@pytest.mark.asyncio
async def test_unassigned_drive_denied():
    with pytest.raises(MicrosoftConnectorError):
        await run(config(), json.dumps({"drive_id": "other", "path": "a.csv"}))


@pytest.mark.asyncio
async def test_redirect_origin_validated_before_following():
    def response(request):
        assert request.url.host != "evil.test"
        if request.url.path.endswith(":/content"):
            return httpx.Response(302, headers={"Location": "https://evil.test/file"})

    with pytest.raises(MicrosoftConnectorError):
        await run(config(), json.dumps({"drive_id": "drive1", "path": "a.csv"}), response)


@pytest.mark.asyncio
async def test_download_is_capped_when_range_ignored():
    class Bytes(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * 65537
            pytest.fail("download continued after cap")

    def response(request):
        if request.url.path.endswith(":/content"):
            return httpx.Response(200, stream=Bytes())

    rows, _ = await run(config(), json.dumps({"drive_id": "drive1", "path": "a.csv"}), response)
    assert len(rows[0]["content"]) == 65536
    assert rows[0]["content_truncated"]


@pytest.mark.asyncio
async def test_listing_traverses_folders_and_pages_and_returns_selectors():
    def response(request):
        path = request.url.path
        if "/drives/drive1/" not in path:
            return None
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json={"value": [{"name": "b.csv", "file": {}, "size": 2}]})
        if "year" in path:
            return httpx.Response(200, json={"value": [{"name": "a.csv", "file": {}}]})
        if path.endswith("children"):
            return httpx.Response(
                200,
                json={
                    "value": [{"name": "year", "folder": {}}],
                    "@odata.nextLink": str(request.url.copy_set_param("page", "2")),
                },
            )

    rows, _ = await run(config(), handler=response)
    assert {row["path"] for row in rows} == {"year/a.csv", "b.csv"}
    assert all(row["drive_id"] == "drive1" for row in rows)


@pytest.mark.asyncio
async def test_empty_site_url_resolves_tenant_root():
    def response(request):
        if request.url.path == "/v1.0/sites/root":
            return httpx.Response(200, json={"id": "root-site"})

    _, calls = await run(config(site_url=""), handler=response)
    assert any(request.url.path == "/v1.0/sites/root" for request in calls)


@pytest.mark.asyncio
async def test_outlook_native_refresh_token_and_fixed_endpoint():
    calls = []

    def dispatch(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "token"})
        assert request.url.path == "/v1.0/me/messages"
        return httpx.Response(200, json={"value": [{"subject": "hello"}]})

    rows = await read_microsoft_connector(
        "source-outlook",
        {"client_id": "id", "client_secret": "secret", "refresh_token": "refresh"},
        "messages",
        query="",
        limit=10,
        client_factory=partial(httpx.AsyncClient, transport=httpx.MockTransport(dispatch)),
    )
    assert rows == [{"subject": "hello"}]
    assert b"grant_type=refresh_token" in calls[0].content


@pytest.mark.asyncio
async def test_remote_errors_are_sanitized():
    def dispatch(request):
        raise RuntimeError("client-secret refresh-secret")

    with pytest.raises(MicrosoftConnectorError) as error:
        await run(config(), handler=dispatch)
    assert "secret" not in str(error.value)
