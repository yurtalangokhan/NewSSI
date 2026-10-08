"""Microsoft 365 source against a fake Graph API."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from connector.sources.microsoft365 import Microsoft365Source
from tests.fake_api import FakeApi, read_all

GRAPH = "https://graph.microsoft.com/v1.0"
AUTH = {"tenant_id": "tid", "client_id": "cid", "client_secret": "sec", "page_size": 2}

USERS = [
    {
        "id": "u1",
        "displayName": "Ann",
        "userPrincipalName": "ann@acme.com",
        "userType": "Member",
        "accountEnabled": True,
        "department": "Eng",
    },
    {
        "id": "u2",
        "displayName": "Guest",
        "userPrincipalName": "g#EXT#@acme.com",
        "userType": "Guest",
        "accountEnabled": True,
    },
    {
        "id": "u3",
        "displayName": "Gone",
        "userPrincipalName": "gone@acme.com",
        "userType": "Member",
        "accountEnabled": False,
    },
    {
        "id": "u4",
        "displayName": "Bob",
        "userPrincipalName": "bob@acme.com",
        "userType": "Member",
        "accountEnabled": True,
    },
]
DRIVE_ITEMS = [
    {"id": "root", "name": "root", "root": {}, "folder": {}},
    {"id": "f1", "name": "Docs", "folder": {}, "lastModifiedDateTime": "2026-01-01T00:00:00Z"},
    {
        "id": "i1",
        "name": "plan.docx",
        "size": 10,
        "file": {"mimeType": "application/vnd.openxmlformats"},
        "parentReference": {"driveId": "d1", "path": "/drive/root:/Docs"},
        "webUrl": "https://acme-my.sharepoint.com/plan.docx",
        "@microsoft.graph.downloadUrl": "https://dl/plan",
        "lastModifiedBy": {"user": {"displayName": "Ann"}},
        "lastModifiedDateTime": "2026-01-02T00:00:00Z",
    },
    {
        "id": "i2",
        "name": "photo.png",
        "size": 5,
        "file": {"mimeType": "image/png"},
        "lastModifiedDateTime": "2026-01-03T00:00:00Z",
    },
]


def _graph() -> FakeApi:
    def users(request: httpx.Request) -> dict[str, Any]:
        assert request.headers["Authorization"] == "Bearer T"
        if "$skiptoken" not in request.url.params:
            assert request.url.params["$select"].startswith("id,displayName")
            return {"value": USERS[:2], "@odata.nextLink": f"{GRAPH}/users?$skiptoken=s2"}
        return {"value": USERS[2:]}

    def delta(user: str, token: str, first: list, later: list) -> Any:
        def route(request: httpx.Request) -> dict[str, Any]:
            if request.url.params.get("token") == token:
                return {
                    "value": later,
                    "@odata.deltaLink": f"{GRAPH}/users/{user}/drive/root/delta?token={token}2",
                }
            return {
                "value": first,
                "@odata.deltaLink": f"{GRAPH}/users/{user}/drive/root/delta?token={token}",
            }

        return route

    def pages(request: httpx.Request) -> dict[str, Any]:
        assert (
            request.url.params["$top"] == "2" and "parentSection" in request.url.params["$expand"]
        )
        items = [
            {
                "id": "p1",
                "title": "Roadmap",
                "lastModifiedDateTime": "2026-01-05T00:00:00Z",
                "parentSection": {"displayName": "Plans"},
                "parentNotebook": {"displayName": "Team"},
                "links": {"oneNoteWebUrl": {"href": "https://onenote/p1"}},
            },
            {"id": "p2", "title": "Old", "lastModifiedDateTime": "2026-01-01T00:00:00Z"},
        ]
        flt = request.url.params.get("$filter")
        if flt:
            since = flt.split("gt ", 1)[1]
            items = [p for p in items if p["lastModifiedDateTime"] > since]
        return {"value": items}

    return FakeApi(
        {
            "POST /tid/oauth2/v2.0/token": {"access_token": "T", "expires_in": 3600},
            "/v1.0/users": users,
            "/v1.0/users/bob@acme.com": USERS[3],
            "/v1.0/users/nobody@acme.com": httpx.Response(
                404, json={"error": {"code": "Request_ResourceNotFound"}}
            ),
            "/v1.0/groups": {
                "value": [
                    {
                        "id": "g1",
                        "displayName": "Eng",
                        "groupTypes": ["Unified"],
                        "mail": "eng@acme.com",
                    }
                ]
            },
            "/v1.0/users/u1/drive/root/delta": delta(
                "u1",
                "D1",
                DRIVE_ITEMS,
                [
                    {
                        "id": "i3",
                        "name": "new.pdf",
                        "file": {"mimeType": "application/pdf"},
                        "lastModifiedDateTime": "2026-02-01T00:00:00Z",
                    }
                ],
            ),
            "/v1.0/users/u4/drive/root/delta": httpx.Response(
                404, json={"error": {"code": "ResourceNotFound"}}
            ),
            "/v1.0/users/u1/onenote/pages": pages,
            "/v1.0/users/u4/onenote/pages": httpx.Response(
                403, json={"error": {"code": "Forbidden"}}
            ),
            "/v1.0/users/u1/onenote/pages/p1/content": httpx.Response(
                200,
                text="<html><body><h1>Q1</h1><p>Ship <b>it</b></p></body></html>",
                headers={"content-type": "text/html"},
            ),
            "/v1.0/users/u1/onenote/pages/p2/content": httpx.Response(200, text="<p>old</p>"),
        }
    )


def _source(api: FakeApi, **cfg: Any) -> Microsoft365Source:
    config = Microsoft365Source.validate_config({**AUTH, **cfg})
    return Microsoft365Source(config, client=api.client(GRAPH))


async def test_users_groups_and_filtering() -> None:
    api = _graph()
    src = _source(api)
    assert (await src.discover()).names() == ["users", "groups", "onedrive_files", "onenote_pages"]
    records, states = await read_all(src, only=["users", "groups"])
    assert [u["id"] for u in records["users"]] == ["u1", "u4"]  # guest and disabled skipped
    assert records["users"][0] == {
        "id": "u1",
        "display_name": "Ann",
        "user_principal_name": "ann@acme.com",
        "mail": None,
        "job_title": None,
        "department": "Eng",
        "office_location": None,
        "account_enabled": True,
        "user_type": "Member",
        "created": None,
    }
    assert records["groups"] == [
        {
            "id": "g1",
            "display_name": "Eng",
            "description": None,
            "mail": "eng@acme.com",
            "mail_enabled": None,
            "security_enabled": None,
            "group_types": ["Unified"],
            "visibility": None,
            "created": None,
        }
    ]
    assert states == {} and len(api.calls("/v1.0/users")) == 2  # paged through nextLink

    whole_directory = _graph()
    everyone = _source(
        whole_directory, include_guests=True, include_disabled_users=True, max_users=3
    )
    records, _ = await read_all(everyone, only=["users"])
    assert [u["id"] for u in records["users"]] == ["u1", "u2", "u3"]
    assert "$filter" not in whole_directory.calls("/v1.0/users")[0].url.params


async def test_user_listing_stops_at_max_users_and_filters_disabled_server_side() -> None:
    # A tenant with tens of thousands of accounts was listed in full before ``max_users``
    # was applied; disabled accounts were fetched only to be dropped.
    api = _graph()
    records, _ = await read_all(_source(api, max_users=1), only=["users"])
    assert [u["id"] for u in records["users"]] == ["u1"]
    calls = api.calls("/v1.0/users")
    assert len(calls) == 1  # the second page was never asked for
    assert calls[0].url.params["$filter"] == "accountEnabled eq true"


async def test_onedrive_delta_per_user_and_missing_drive() -> None:
    api = _graph()
    src = _source(api, file_extensions=["docx", "pdf"])
    records, states = await read_all(src, only=["onedrive_files"], incremental=True)
    assert [f["id"] for f in records["onedrive_files"]] == ["i1"]  # root, folder and png filtered
    item = records["onedrive_files"][0]
    assert item["owner"] == "ann@acme.com" and item["path"] == "/drive/root:/Docs/plan.docx"
    assert item["drive_id"] == "d1" and item["download_url"] == "https://dl/plan"
    assert item["last_modified_by"] == "Ann" and item["deleted"] is False
    assert states["onedrive_files"] == {
        "delta_links": {"u1": f"{GRAPH}/users/u1/drive/root/delta?token=D1"}
    }
    assert len(api.calls("/v1.0/users/u4/drive/root/delta")) == 1  # 404: skipped, not fatal

    again, states = await read_all(src, only=["onedrive_files"], incremental=True, state=states)
    assert [f["id"] for f in again["onedrive_files"]] == ["i3"]
    assert states["onedrive_files"]["delta_links"]["u1"].endswith("token=D12")

    folders = _source(_graph(), include_folders=True)
    records, _ = await read_all(folders, only=["onedrive_files"])
    assert [f["name"] for f in records["onedrive_files"]] == ["Docs", "plan.docx", "photo.png"]
    assert records["onedrive_files"][0]["is_folder"] is True


async def test_onenote_pages_with_content_and_per_user_cursor() -> None:
    api = _graph()
    src = _source(api)
    records, states = await read_all(src, only=["onenote_pages"], incremental=True)
    pages = {p["id"]: p for p in records["onenote_pages"]}
    assert pages["p1"]["content"] == "Q1\nShip it"
    assert (pages["p1"]["notebook"], pages["p1"]["section"]) == ("Team", "Plans")
    assert pages["p1"]["web_url"] == "https://onenote/p1" and pages["p1"]["owner"] == "ann@acme.com"
    assert states["onenote_pages"] == {"by_user": {"u1": "2026-01-05T00:00:00+00:00"}}
    assert len(api.calls("/v1.0/users/u4/onenote/pages")) == 1  # 403: skipped

    again, states = await read_all(src, only=["onenote_pages"], incremental=True, state=states)
    assert again == {}
    call = api.calls("/v1.0/users/u1/onenote/pages")[-1]
    assert call.url.params["$filter"] == "lastModifiedDateTime gt 2026-01-05T00:00:00Z"
    assert states == {}  # nothing new: the cursor is not rewritten

    no_content = _source(_graph(), include_onenote_content=False)
    records, _ = await read_all(no_content, only=["onenote_pages"])
    assert all(p["content"] is None for p in records["onenote_pages"])


async def test_onenote_content_failures_other_than_403_404_fail_the_run() -> None:
    # The page is read with ``content: None`` and the cursor moves past it: swallowing
    # every failure would make a page whose body was merely unavailable permanently empty.
    api = _graph()
    api.routes["/v1.0/users/u1/onenote/pages/p1/content"] = httpx.Response(
        403, json={"error": {"code": "Forbidden"}}
    )
    records, _ = await read_all(_source(api), only=["onenote_pages"])
    pages = {p["id"]: p for p in records["onenote_pages"]}
    assert pages["p1"]["content"] is None and pages["p2"]["content"] == "old"

    api.routes["/v1.0/users/u1/onenote/pages/p1/content"] = httpx.Response(503, text="busy")
    src = _source(api)
    src.retry_delay = 0
    with pytest.raises(httpx.HTTPStatusError):
        await read_all(src, only=["onenote_pages"])


async def test_explicit_user_principal_names() -> None:
    api = _graph()
    src = _source(api, user_principal_names=["bob@acme.com", "nobody@acme.com"])
    records, _ = await read_all(src, only=["users", "onedrive_files"])
    assert [u["id"] for u in records["users"]] == ["u4"]  # unknown UPN skipped
    assert "onedrive_files" not in records  # Bob has no drive
    assert api.calls("/v1.0/users") == []  # directory was not listed
    assert Microsoft365Source.secret_fields() == {"client_secret"}
