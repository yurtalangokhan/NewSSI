"""Outlook and SharePoint sources against a fake Microsoft Graph (httpx MockTransport)."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import httpx

from connector import ConfiguredCatalog, Record, State, SyncMode, SyncState
from connector.sources.outlook import OutlookSource
from connector.sources.sharepoint import SharePointSource

GRAPH = "https://graph.microsoft.com/v1.0"
AUTH = {
    "tenant_id": "tid",
    "client_id": "cid",
    "client_secret": "sec",
    "page_size": 1,
}


def _client(handler) -> httpx.AsyncClient:  # noqa: ANN001
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=GRAPH)


class _Graph:
    """Minimal Graph fake: token endpoint + routes, with @odata.nextLink paging."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token_calls = 0
        self.routes: dict[str, Any] = {}

    def page(
        self, items: list[dict[str, Any]], request: httpx.Request, *, delta: str | None = None
    ):  # noqa: ANN202
        skip = int(request.url.params.get("$skip", 0))
        top = int(request.url.params.get("$top", 1)) or 1
        chunk = items[skip : skip + top]
        body: dict[str, Any] = {"value": chunk}
        if skip + top < len(items):
            body["@odata.nextLink"] = str(request.url.copy_set_param("$skip", skip + top))
        elif delta:
            body["@odata.deltaLink"] = delta
        return httpx.Response(200, json=body)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "login.microsoftonline.com":
            self.token_calls += 1
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["client_credentials"]
            assert form["scope"] == ["https://graph.microsoft.com/.default"]
            return httpx.Response(200, json={"access_token": "T", "expires_in": 3600})
        assert request.headers.get("Authorization") == "Bearer T", (
            "every Graph call must carry the token"
        )
        route = self.routes.get(request.url.path)
        if route is None:
            return httpx.Response(404, json={"error": {"message": f"no route {request.url.path}"}})
        return route(request)


# ---------------------------------------------------------------------------
# Outlook
# ---------------------------------------------------------------------------

MESSAGES = [
    {
        "id": "m1",
        "subject": "Hello",
        "body": {"content": "plain text body"},
        "from": {"emailAddress": {"address": "a@x.com"}},
        "toRecipients": [{"emailAddress": {"address": "b@x.com"}}],
        "hasAttachments": True,
        "lastModifiedDateTime": "2026-01-01T10:00:00Z",
        "parentFolderId": "inbox",
    },
    {
        "id": "m2",
        "subject": "Later",
        "bodyPreview": "preview only",
        "hasAttachments": False,
        "lastModifiedDateTime": "2026-01-05T10:00:00Z",
    },
]


def _outlook_graph() -> _Graph:
    g = _Graph()

    def messages(request: httpx.Request) -> httpx.Response:
        flt = request.url.params.get("$filter")
        items = MESSAGES
        if flt:
            since = flt.split("gt ", 1)[1]
            items = [m for m in MESSAGES if m["lastModifiedDateTime"] > since]
        assert request.headers.get("Prefer") == 'outlook.body-content-type="text"'
        return g.page(items, request)

    g.routes["/v1.0/users/sales@acme.com/messages"] = messages
    g.routes["/v1.0/users/sales@acme.com/messages/m1/attachments"] = lambda r: httpx.Response(
        200,
        json={
            "value": [
                {"id": "a1", "name": "brief.pdf", "contentType": "application/pdf", "size": 10}
            ]
        },
    )
    g.routes["/v1.0/users/sales@acme.com/events"] = lambda r: g.page(
        [
            {
                "id": "e1",
                "subject": "Standup",
                "start": {"dateTime": "2026-01-02T09:00:00"},
                "end": {"dateTime": "2026-01-02T09:15:00"},
                "organizer": {"emailAddress": {"address": "a@x.com"}},
                "attendees": [{"emailAddress": {"address": "b@x.com"}}],
                "lastModifiedDateTime": "2026-01-01T08:00:00Z",
            }
        ],
        r,
    )
    g.routes["/v1.0/organization"] = lambda r: httpx.Response(200, json={"value": []})
    return g


async def test_outlook_messages_events_paging_and_attachments() -> None:
    g = _outlook_graph()
    cfg = OutlookSource.validate_config({**AUTH, "user_principal_names": ["sales@acme.com"]})
    src = OutlookSource(cfg, client=_client(g))
    assert (await src.check()).ok
    catalog = await src.discover()
    assert catalog.names() == ["messages", "events"]
    items = [i async for i in src.read(ConfiguredCatalog.from_catalog(catalog))]
    records = [i for i in items if isinstance(i, Record)]
    assert [(r.stream, r.data["id"]) for r in records] == [
        ("messages", "m1"),
        ("messages", "m2"),
        ("events", "e1"),
    ]
    m1 = records[0].data
    assert m1["body"] == "plain text body" and m1["from"] == "a@x.com" and m1["to"] == ["b@x.com"]
    assert m1["attachments"] == [
        {"id": "a1", "name": "brief.pdf", "content_type": "application/pdf", "size": 10}
    ]
    assert records[1].data["body"] == "preview only" and records[1].data["attachments"] == []
    assert records[2].data["start"] == "2026-01-02T09:00:00" and records[2].data["attendees"] == [
        "b@x.com"
    ]
    assert g.token_calls == 1  # token cached across every call


async def test_outlook_incremental_filter_and_state() -> None:
    g = _outlook_graph()
    cfg = OutlookSource.validate_config({**AUTH, "user_principal_names": ["sales@acme.com"]})
    src = OutlookSource(cfg, client=_client(g))
    catalog = await src.discover()
    configured = ConfiguredCatalog.from_catalog(
        catalog, sync_mode=SyncMode.INCREMENTAL, only=["messages"]
    )
    prior = SyncState(streams={"messages": {"cursor": "2026-01-02T00:00:00Z"}})
    items = [i async for i in src.read(configured, prior)]
    assert [i.data["id"] for i in items if isinstance(i, Record)] == ["m2"]
    assert items[-1] == State(stream="messages", data={"cursor": "2026-01-05T10:00:00+00:00"})
    call = next(r for r in g.requests if r.url.path.endswith("/messages"))
    assert call.url.params["$filter"] == "lastModifiedDateTime gt 2026-01-02T00:00:00Z"
    assert call.url.params["$orderby"] == "lastModifiedDateTime asc"


# ---------------------------------------------------------------------------
# SharePoint
# ---------------------------------------------------------------------------

SITE = "acme.sharepoint.com:/sites/hr"


def _sharepoint_graph() -> _Graph:
    g = _Graph()
    base = f"/v1.0/sites/{SITE}"
    g.routes[f"{base}/pages/microsoft.graph.sitePage"] = lambda r: g.page(
        [
            {
                "id": "p1",
                "title": "Policies",
                "name": "policies.aspx",
                "webUrl": "https://acme.sharepoint.com/sites/hr/SitePages/policies.aspx",
                "lastModifiedDateTime": "2026-01-01T00:00:00Z",
                "canvasLayout": {
                    "horizontalSections": [
                        {"columns": [{"webparts": [{"innerHtml": "<h2>Leave</h2><p>30 days</p>"}]}]}
                    ],
                    "verticalSection": {"webparts": [{"innerHtml": "<p>Contact HR</p>"}]},
                },
            }
        ],
        r,
    )
    g.routes[f"{base}/drives"] = lambda r: g.page(
        [{"id": "d1", "name": "Documents"}, {"id": "d2", "name": "Other"}], r
    )
    drive_items = [
        {"id": "root", "name": "root", "root": {}, "folder": {}},
        {
            "id": "f1",
            "name": "Policies",
            "folder": {},
            "lastModifiedDateTime": "2026-01-01T00:00:00Z",
        },
        {
            "id": "i1",
            "name": "handbook.pdf",
            "file": {"mimeType": "application/pdf"},
            "size": 123,
            "webUrl": "https://acme.sharepoint.com/x/handbook.pdf",
            "@microsoft.graph.downloadUrl": "https://dl/handbook.pdf",
            "parentReference": {"path": "/drives/d1/root:/Policies"},
            "lastModifiedBy": {"user": {"displayName": "Ann"}},
            "lastModifiedDateTime": "2026-01-02T00:00:00Z",
        },
        {
            "id": "i2",
            "name": "notes.txt",
            "file": {"mimeType": "text/plain"},
            "lastModifiedDateTime": "2026-01-03T00:00:00Z",
        },
    ]
    g.routes["/v1.0/drives/d1/root/delta"] = lambda r: g.page(
        drive_items, r, delta=f"{GRAPH}/drives/d1/root/delta?token=D1"
    )
    g.routes["/v1.0/drives/d1/root/delta"] = g.routes["/v1.0/drives/d1/root/delta"]
    g.routes[f"{base}/lists/Tasks/items"] = lambda r: g.page(
        [
            {
                "id": "1",
                "webUrl": "https://acme.sharepoint.com/sites/hr/Lists/Tasks/1",
                "lastModifiedDateTime": "2026-01-04T00:00:00Z",
                "fields": {"@odata.etag": "x", "Title": "Renew contracts", "Status": "Open"},
            }
        ],
        r,
    )
    g.routes["/v1.0/organization"] = lambda r: httpx.Response(200, json={"value": []})
    return g


async def test_sharepoint_pages_drive_delta_and_lists() -> None:
    g = _sharepoint_graph()
    cfg = SharePointSource.validate_config(
        {
            **AUTH,
            "site": SITE,
            "lists": ["Tasks"],
            "drives": ["Documents"],
            "file_extensions": ["pdf"],
        }
    )
    src = SharePointSource(cfg, client=_client(g))
    assert (await src.check()).ok
    catalog = await src.discover()
    configured = ConfiguredCatalog.from_catalog(catalog, sync_mode=SyncMode.INCREMENTAL)
    items = [i async for i in src.read(configured)]
    records = {(i.stream, i.data["id"]): i.data for i in items if isinstance(i, Record)}
    states = {s.stream: s.data for s in items if isinstance(s, State)}

    assert records[("pages", "p1")]["content"] == "Leave\n30 days\n\nContact HR"
    assert [k for k in records if k[0] == "drive_items"] == [
        ("drive_items", "i1")
    ]  # pdf only, no folders/root
    item = records[("drive_items", "i1")]
    assert item["path"] == "/drives/d1/root:/Policies/handbook.pdf"
    assert item["download_url"] == "https://dl/handbook.pdf" and item["last_modified_by"] == "Ann"
    assert records[("list_items", "1")]["fields"] == {"Title": "Renew contracts", "Status": "Open"}

    assert states["pages"] == {"cursor": "2026-01-01T00:00:00+00:00"}
    assert states["drive_items"] == {
        "delta_links": {"d1": f"{GRAPH}/drives/d1/root/delta?token=D1"}
    }
    assert states["list_items"] == {"cursor": "2026-01-04T00:00:00+00:00"}
    assert not any(r.url.path.startswith("/v1.0/drives/d2") for r in g.requests)  # filtered by name


async def test_sharepoint_second_run_uses_delta_link() -> None:
    g = _sharepoint_graph()
    g.routes["/v1.0/drives/d1/root/delta"] = lambda r: (
        g.page(
            [
                {
                    "id": "i9",
                    "name": "new.pdf",
                    "file": {},
                    "lastModifiedDateTime": "2026-02-01T00:00:00Z",
                }
            ],
            r,
            delta=f"{GRAPH}/drives/d1/root/delta?token=D2",
        )
        if r.url.params.get("token") == "D1"
        else httpx.Response(500, json={"error": {"message": "should have used delta link"}})
    )
    cfg = SharePointSource.validate_config({**AUTH, "site": SITE, "drives": ["Documents"]})
    src = SharePointSource(cfg, client=_client(g))
    catalog = await src.discover()
    configured = ConfiguredCatalog.from_catalog(
        catalog, sync_mode=SyncMode.INCREMENTAL, only=["drive_items"]
    )
    prior = SyncState(
        streams={"drive_items": {"delta_links": {"d1": f"{GRAPH}/drives/d1/root/delta?token=D1"}}}
    )
    items = [i async for i in src.read(configured, prior)]
    assert [i.data["id"] for i in items if isinstance(i, Record)] == ["i9"]
    assert items[-1].data["delta_links"]["d1"].endswith("token=D2")


def test_graph_secrets() -> None:
    assert OutlookSource.secret_fields() == {"client_secret"}
    assert SharePointSource.secret_fields() == {"client_secret"}
