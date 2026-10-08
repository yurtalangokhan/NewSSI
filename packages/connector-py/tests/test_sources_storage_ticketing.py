"""Storage and ticketing sources replayed against fake APIs."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from connector import ConfigValidationError
from connector.common.s3_connection import (
    CloudflareR2Connection,
    GcsHmacConnection,
    OracleObjectStorageConnection,
)
from connector.sources.airtable import AirtableSource
from connector.sources.asana import AsanaSource
from connector.sources.box import BoxSource
from connector.sources.clickup import ClickUpSource
from connector.sources.cloudflare_r2 import CloudflareR2Source
from connector.sources.dropbox import DropboxSource
from connector.sources.egnyte import EgnyteSource
from connector.sources.freshdesk import FreshdeskSource
from connector.sources.google_drive import GoogleDriveSource
from connector.sources.google_storage import GoogleStorageSource
from connector.sources.linear import LinearSource
from connector.sources.oracle_storage import OracleStorageSource
from connector.sources.productboard import ProductboardSource
from connector.sources.s3 import S3Source
from connector.sources.testrail import TestRailSource
from connector.sources.zendesk import ZendeskSource
from tests.fake_api import FakeApi, read_all
from tests.test_s3_minio import FakeS3

# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------


def test_s3_compatible_connection_settings() -> None:
    gcs = GcsHmacConnection(hmac_access_id="a", hmac_secret="s").client_kwargs()
    assert gcs["endpoint_url"] == "https://storage.googleapis.com" and gcs["path_style"] is True
    oci = OracleObjectStorageConnection(
        namespace="ns", region="eu-frankfurt-1", access_key="a", secret_key="s"
    )
    assert oci.endpoint_url() == "https://ns.compat.objectstorage.eu-frankfurt-1.oraclecloud.com"
    r2 = CloudflareR2Connection(account_id="acc", access_key_id="a", secret_access_key="s")
    assert r2.endpoint_url() == "https://acc.r2.cloudflarestorage.com"
    assert r2.client_kwargs()["region_name"] == "auto"
    eu = CloudflareR2Connection(
        account_id="acc", access_key_id="a", secret_access_key="s", jurisdiction="eu"
    )
    assert eu.endpoint_url() == "https://acc.eu.r2.cloudflarestorage.com"


@pytest.mark.parametrize(
    ("cls", "config"),
    [
        (GoogleStorageSource, {"hmac_access_id": "a", "hmac_secret": "s", "bucket": "b"}),
        (
            OracleStorageSource,
            {"namespace": "n", "region": "r", "access_key": "a", "secret_key": "s", "bucket": "b"},
        ),
        (
            CloudflareR2Source,
            {"account_id": "x", "access_key_id": "a", "secret_access_key": "s", "bucket": "b"},
        ),
    ],
)
async def test_s3_compatible_sources_reuse_the_s3_reader(cls: type, config: dict) -> None:
    client = FakeS3({"notes.md": b"# Hi", "rows.jsonl": b'{"id": 1}\n'})
    src = cls(cls.validate_config(config), client=client)
    assert isinstance(src, S3Source) and (await src.check()).ok
    records, _ = await read_all(src)
    assert [r.get("content") or r.get("id") for r in records["files"]] == ["# Hi", 1]
    assert "aws_access_key_id" not in cls.spec().connection_specification["properties"]


async def test_google_drive_query_export_and_incremental() -> None:
    doc = "application/vnd.google-apps.document"
    api = FakeApi(
        {
            "/drive/v3/files": {
                "files": [
                    {
                        "id": "f1",
                        "name": "Plan",
                        "mimeType": doc,
                        "modifiedTime": "2026-01-03T00:00:00Z",
                    },
                    {
                        "id": "f2",
                        "name": "a.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2026-01-04T00:00:00Z",
                    },
                ]
            },
            "/drive/v3/files/f1/export": httpx.Response(200, text="Plan body"),
        }
    )
    cfg = {"access_token": "T", "folder_ids": ["F"]}
    src = GoogleDriveSource(
        GoogleDriveSource.validate_config(cfg), client=api.client("https://www.googleapis.com")
    )
    records, states = await read_all(
        src, incremental=True, state={"files": {"cursor": "2026-01-02T00:00:00Z"}}
    )
    assert records["files"][0]["content"] == "Plan body" and "content" not in records["files"][1]
    q = api.calls("/drive/v3/files")[0].url.params["q"]
    assert "'F' in parents" in q and "trashed = false" in q
    assert q.endswith("modifiedTime > '2026-01-02T00:00:00Z'")
    assert api.requests[0].headers["Authorization"] == "Bearer T"
    assert states["files"]["cursor"] == "2026-01-04T00:00:00+00:00"
    with pytest.raises(ConfigValidationError):
        GoogleDriveSource.validate_config({})


async def test_google_drive_keeps_unreadable_files_but_not_a_broken_export() -> None:
    # 403/404 on the body is the file's own state (no permission, gone): the metadata is
    # indexed without content. Any other failure would advance the cursor past a file whose
    # body is merely unavailable right now, and it would never be read: the run fails instead.
    doc = "application/vnd.google-apps.document"
    listing = {
        "files": [
            {"id": "f1", "mimeType": doc, "modifiedTime": "2026-01-03T00:00:00Z"},
            {"id": "f2", "mimeType": doc, "modifiedTime": "2026-01-04T00:00:00Z"},
        ]
    }
    api = FakeApi(
        {
            "/drive/v3/files": listing,
            "/drive/v3/files/f1/export": httpx.Response(403, json={"error": "forbidden"}),
            "/drive/v3/files/f2/export": httpx.Response(200, text="ok"),
        }
    )
    cfg = {"access_token": "T", "folder_ids": ["F"]}
    src = GoogleDriveSource(
        GoogleDriveSource.validate_config(cfg), client=api.client("https://www.googleapis.com")
    )
    records, _ = await read_all(src)
    assert [(f["id"], f.get("content"), f.get("content_error")) for f in records["files"]] == [
        ("f1", None, "403"),
        ("f2", "ok", None),
    ]

    broken = FakeApi(
        {"/drive/v3/files": listing, "/drive/v3/files/f1/export": httpx.Response(500, text="x")}
    )
    src = GoogleDriveSource(
        GoogleDriveSource.validate_config(cfg), client=broken.client("https://www.googleapis.com")
    )
    src.retry_delay = 0
    with pytest.raises(httpx.HTTPStatusError):
        await read_all(src)


async def test_dropbox_refresh_token_and_list_folder_continue() -> None:
    def token(request: httpx.Request) -> dict[str, Any]:
        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["refresh_token"] and form["refresh_token"] == ["R"]
        assert request.headers["Authorization"].startswith("Basic ")
        return {"access_token": "T", "expires_in": 14400}

    api = FakeApi(
        {
            "POST /oauth2/token": token,
            "POST /2/files/list_folder": {
                "entries": [
                    {".tag": "folder", "path_display": "/docs"},
                    {
                        ".tag": "file",
                        "id": "id:1",
                        "path_display": "/docs/a.txt",
                        "server_modified": "2026-01-01T00:00:00Z",
                    },
                ],
                "cursor": "C1",
                "has_more": True,
            },
            "POST /2/files/list_folder/continue": lambda r: (
                {
                    "entries": [
                        {
                            ".tag": "file",
                            "id": "id:2",
                            "path_display": "/b.txt",
                            "server_modified": "2026-01-02T00:00:00Z",
                        }
                    ],
                    "has_more": False,
                }
                if json.loads(r.content) == {"cursor": "C1"}
                else httpx.Response(400)
            ),
        }
    )
    cfg = {"refresh_token": "R", "app_key": "k", "app_secret": "s", "path": "/"}
    src = DropboxSource(
        DropboxSource.validate_config(cfg), client=api.client("https://api.dropboxapi.com")
    )
    records, _ = await read_all(src)
    assert [f["path"] for f in records["files"]] == ["/docs/a.txt", "/b.txt"]
    assert json.loads(api.calls("/2/files/list_folder")[0].content)["path"] == ""
    with pytest.raises(ConfigValidationError):
        DropboxSource.validate_config({"refresh_token": "R"})


async def test_box_ccg_auth_and_folder_walk() -> None:
    def token(request: httpx.Request) -> dict[str, Any]:
        form = parse_qs(request.content.decode())
        assert form["box_subject_type"] == ["enterprise"] and form["box_subject_id"] == ["E1"]
        return {"access_token": "T", "expires_in": 3600}

    def folder(files: list[dict[str, Any]]):  # noqa: ANN202
        return {"entries": files, "total_count": len(files)}

    api = FakeApi(
        {
            "POST /oauth2/token": token,
            "/2.0/folders/0/items": folder(
                [
                    {
                        "type": "folder",
                        "id": "10",
                        "name": "HR",
                        "modified_at": "2025-12-01T00:00:00Z",
                    },
                    {
                        "type": "file",
                        "id": "1",
                        "name": "root.txt",
                        "modified_at": "2026-01-01T00:00:00Z",
                        "path_collection": {"entries": [{"name": "All Files"}]},
                    },
                    {"type": "web_link", "id": "w"},
                ]
            ),
            "/2.0/folders/10/items": folder(
                [
                    {
                        "type": "file",
                        "id": "2",
                        "name": "policy.pdf",
                        "modified_at": "2026-01-02T00:00:00Z",
                        "path_collection": {"entries": [{"name": "All Files"}, {"name": "HR"}]},
                    }
                ]
            ),
        }
    )
    cfg = {"client_id": "c", "client_secret": "s", "enterprise_id": "E1"}
    src = BoxSource(BoxSource.validate_config(cfg), client=api.client("https://api.box.com"))
    records, _ = await read_all(src)
    assert [f["path"] for f in records["files"]] == [
        "All Files/root.txt",
        "All Files/HR/policy.pdf",
    ]
    assert api.calls("/2.0/folders/10/items")[0].headers["Authorization"] == "Bearer T"

    # Incremental: a folder's own modified_at says nothing about what is inside (Box only
    # touches the direct parent), so folders older than the cursor are still walked.
    prior = {"files": {"cursor": "2026-01-01T12:00:00Z"}}
    records, states = await read_all(src, incremental=True, state=prior)
    assert [f["path"] for f in records["files"]] == ["All Files/HR/policy.pdf"]
    assert states["files"] == {"cursor": "2026-01-02T00:00:00+00:00"}


async def test_egnyte_splits_listing_and_walks_subfolders() -> None:
    # Egnyte stamps files in RFC 1123 ("Thu, 01 Jan 2026 00:00:00 GMT") and folders in epoch
    # milliseconds; a folder listing is paged by ``count``/``offset`` over its files.
    def shared(request: httpx.Request) -> dict[str, Any]:
        offset = int(request.url.params.get("offset", 0))
        files = [
            {
                "name": "a.txt",
                "path": "/Shared/a.txt",
                "entry_id": "e1",
                "last_modified": "Thu, 01 Jan 2026 00:00:00 GMT",
            },
            {
                "name": "b.txt",
                "path": "/Shared/b.txt",
                "entry_id": "e3",
                "last_modified": "Sat, 03 Jan 2026 00:00:00 GMT",
            },
            {
                "name": "c.txt",
                "path": "/Shared/c.txt",
                "entry_id": "e4",
                "last_modified": "Fri, 02 Jan 2026 12:00:00 GMT",
            },
        ]
        page = files[offset : offset + 2]
        return {
            "folders": [{"name": "Legal", "path": "/Shared/Legal", "lastModified": 1700000000000}],
            "files": page,
            "count": len(page),
            "offset": offset,
            "total_count": len(files),
        }

    api = FakeApi(
        {
            "/pubapi/v1/fs/Shared": shared,
            "/pubapi/v1/fs/Shared/Legal": {
                "files": [
                    {
                        "name": "nda.docx",
                        "path": "/Shared/Legal/nda.docx",
                        "entry_id": "e2",
                        "last_modified": "Fri, 02 Jan 2026 00:00:00 GMT",
                    }
                ],
                "count": 1,
                "offset": 0,
                "total_count": 1,
            },
        }
    )
    cfg = {"domain": "acme", "access_token": "t"}
    src = EgnyteSource(
        EgnyteSource.validate_config(cfg), client=api.client("https://acme.egnyte.com")
    )
    records, _ = await read_all(src)
    assert [f["path"] for f in records["files"]] == [
        "/Shared/a.txt",
        "/Shared/b.txt",
        "/Shared/c.txt",
        "/Shared/Legal/nda.docx",
    ]
    assert records["files"][0]["last_modified"] == "2026-01-01T00:00:00+00:00"
    assert api.requests[0].url.params["list_content"] == "true"
    assert [r.url.params.get("offset") for r in api.calls("/pubapi/v1/fs/Shared")] == ["0", "2"]

    # Incremental: the cursor is the ISO form, and the RFC 1123 stamps compare as times
    # (not as text starting with the weekday).
    prior = {"files": {"cursor": "2026-01-02T06:00:00Z"}}
    records, states = await read_all(src, incremental=True, state=prior)
    assert [f["path"] for f in records["files"]] == ["/Shared/b.txt", "/Shared/c.txt"]
    assert states["files"] == {"cursor": "2026-01-03T00:00:00+00:00"}


# ---------------------------------------------------------------------------
# ticketing
# ---------------------------------------------------------------------------


async def test_zendesk_incremental_export_and_comments() -> None:
    def tickets(request: httpx.Request) -> dict[str, Any]:
        if "cursor" in request.url.params:
            assert "start_time" not in request.url.params
            return {
                "tickets": [{"id": 2, "updated_at": "2026-01-05T00:00:00Z"}],
                "end_of_stream": True,
                "after_cursor": "c3",
            }
        return {
            "tickets": [{"id": 1, "updated_at": "2026-01-04T00:00:00Z"}],
            "end_of_stream": False,
            "after_cursor": "c2",
        }

    api = FakeApi(
        {
            "/api/v2/incremental/tickets/cursor.json": tickets,
            "/api/v2/tickets/1/comments.json": {
                "comments": [{"id": 11, "body": "hi", "created_at": "2026-01-04T00:00:00Z"}],
                "next_page": None,
            },
            "/api/v2/tickets/2/comments.json": {"comments": []},
            "/api/v2/help_center/articles.json": {
                "articles": [
                    {"id": 9, "body": "<p>How to</p>", "updated_at": "2026-01-01T00:00:00Z"}
                ],
                "next_page": None,
            },
        }
    )
    cfg = {"subdomain": "acme", "email": "a@acme.com", "api_token": "tok"}
    src = ZendeskSource(
        ZendeskSource.validate_config(cfg), client=api.client("https://acme.zendesk.com")
    )
    records, states = await read_all(
        src, incremental=True, state={"tickets": {"cursor": "2026-01-03T00:00:00Z"}}
    )
    assert [t["id"] for t in records["tickets"]] == [1, 2]
    assert records["ticket_comments"] == [
        {"id": 11, "body": "hi", "created_at": "2026-01-04T00:00:00Z", "ticket_id": 1}
    ]
    assert records["articles"][0]["body_text"] == "How to"
    first = api.calls("/api/v2/incremental/tickets/cursor.json")[0]
    assert first.url.params["start_time"] == "1767398400"
    assert states["tickets"]["cursor"] == "2026-01-05T00:00:00+00:00"

    # The comments stream exports the tickets changed since its own cursor (a comment
    # moves its ticket's updated_at), not every ticket since start_date.
    api.requests.clear()
    records, states = await read_all(
        src,
        only=["ticket_comments"],
        incremental=True,
        state={"ticket_comments": {"cursor": "2026-01-03T12:00:00Z"}},
    )
    exports = api.calls("/api/v2/incremental/tickets/cursor.json")
    assert exports[0].url.params["start_time"] == "1767441600"
    assert [c["id"] for c in records["ticket_comments"]] == [11]
    assert states["ticket_comments"] == {"cursor": "2026-01-04T00:00:00+00:00"}


async def test_zendesk_without_credentials_reads_the_help_center_anonymously() -> None:
    api = FakeApi(
        {
            "/api/v2/help_center/articles.json": {
                "articles": [
                    {"id": 9, "body": "<p>How to</p>", "updated_at": "2026-01-01T00:00:00Z"}
                ],
                "next_page": None,
            }
        }
    )
    src = ZendeskSource(
        ZendeskSource.validate_config({"subdomain": "acme"}),
        client=api.client("https://acme.zendesk.com"),
    )
    records, _ = await read_all(src, only=["articles"])
    assert records["articles"][0]["body_text"] == "How to"
    assert all("authorization" not in r.headers for r in api.requests)  # no junk Basic header


async def test_airtable_discovers_tables_and_flattens_fields() -> None:
    api = FakeApi(
        {
            "/v0/meta/bases/appX/tables": {"tables": [{"id": "tbl1", "name": "Bug Reports"}]},
            "/v0/appX/tbl1": lambda r: (
                {
                    "records": [
                        {
                            "id": "rec1",
                            "createdTime": "2026-01-01T00:00:00Z",
                            "fields": {"Title": "Crash", "Modified": "2026-01-05T00:00:00Z"},
                        }
                    ],
                    "offset": "o2",
                }
                if "offset" not in r.url.params
                else {
                    "records": [
                        {
                            "id": "rec2",
                            "fields": {"Title": "Slow", "Modified": "2026-01-06T00:00:00Z"},
                        }
                    ]
                }
            ),
        }
    )
    cfg = {"api_token": "pat", "base_id": "appX", "last_modified_field": "Modified"}
    src = AirtableSource(
        AirtableSource.validate_config(cfg), client=api.client("https://api.airtable.com")
    )
    records, states = await read_all(
        src, incremental=True, state={"bug_reports": {"cursor": "2026-01-02T00:00:00Z"}}
    )
    assert [(r["id"], r["Title"]) for r in records["bug_reports"]] == [
        ("rec1", "Crash"),
        ("rec2", "Slow"),
    ]
    formula = api.calls("/v0/appX/tbl1")[0].url.params["filterByFormula"]
    assert formula == "IS_AFTER({Modified}, '2026-01-02T00:00:00+00:00')"
    assert states["bug_reports"]["cursor"] == "2026-01-06T00:00:00+00:00"


async def test_linear_relay_paging_filter_and_flattening() -> None:
    def graphql(request: httpx.Request) -> dict[str, Any]:
        body = json.loads(request.content)
        if "issues(" not in body["query"]:
            return {
                "data": {
                    "teams": {"nodes": [{"id": "t"}], "pageInfo": {"hasNextPage": False}},
                    "projects": {"nodes": [], "pageInfo": {}},
                }
            }
        assert body["variables"]["filter"] == {
            "updatedAt": {"gt": "2026-01-01T00:00:00+00:00"},
            "team": {"key": {"in": ["ENG"]}},
        }
        first = "after" not in body["variables"]
        node = {
            "id": "i1" if first else "i2",
            "updatedAt": "2026-01-02T00:00:00Z" if first else "2026-01-03T00:00:00Z",
            "labels": {"nodes": [{"name": "bug"}]},
            "comments": {"nodes": []},
        }
        return {
            "data": {
                "issues": {"nodes": [node], "pageInfo": {"hasNextPage": first, "endCursor": "c1"}}
            }
        }

    api = FakeApi({"POST /graphql": graphql})
    cfg = {"api_key": "lin_api", "team_keys": ["ENG"]}
    src = LinearSource(
        LinearSource.validate_config(cfg), client=api.client("https://api.linear.app")
    )
    records, states = await read_all(
        src, only=["issues"], incremental=True, state={"issues": {"cursor": "2026-01-01T00:00:00Z"}}
    )
    assert [i["id"] for i in records["issues"]] == ["i1", "i2"]
    assert records["issues"][0]["labels"] == [{"name": "bug"}]
    assert states["issues"]["cursor"] == "2026-01-03T00:00:00+00:00"
    assert api.requests[0].headers["Authorization"] == "lin_api"


async def test_freshdesk_tickets_and_three_level_solutions() -> None:
    api = FakeApi(
        {
            "/api/v2/tickets": [{"id": 1, "updated_at": "2026-01-02T00:00:00Z"}],
            "/api/v2/contacts": [],
            "/api/v2/companies": [],
            "/api/v2/solutions/categories": [{"id": 100}],
            "/api/v2/solutions/categories/100/folders": [{"id": 200}],
            "/api/v2/solutions/folders/200/articles": [
                {"id": 300, "description": "<p>Reset</p>", "updated_at": "2026-01-01T00:00:00Z"}
            ],
        }
    )
    cfg = {"domain": "acme", "api_key": "key"}
    src = FreshdeskSource(
        FreshdeskSource.validate_config(cfg), client=api.client("https://acme.freshdesk.com")
    )
    records, _ = await read_all(
        src, incremental=True, state={"tickets": {"cursor": "2026-01-01T12:00:00Z"}}
    )
    article = records["solution_articles"][0]
    assert (article["id"], article["folder_id"], article["description_text"]) == (300, 200, "Reset")
    call = api.calls("/api/v2/tickets")[0]
    assert (
        call.url.params["updated_since"] == "2026-01-01T12:00:00Z"
        and call.url.params["per_page"] == "100"
    )


async def test_freshdesk_tickets_re_anchor_updated_since_at_the_page_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Freshdesk serves at most 300 pages per query (30 000 tickets); a bigger backlog has to be
    # read as a chain of queries, each starting at the last ``updated_at`` seen.
    from connector.sources import freshdesk as module

    monkeypatch.setattr(
        module, "_TICKET_PAGER", module._TicketPagination(page_size=2, max_page=2), raising=True
    )
    stamps = {i: f"2026-01-0{i}T00:00:00Z" for i in range(1, 6)}

    def tickets(request: httpx.Request) -> list[dict[str, Any]]:
        since, page = request.url.params["updated_since"], int(request.url.params["page"])
        assert page <= 2, "paged past the cap"
        ids = [i for i in stamps if stamps[i] >= since][(page - 1) * 2 : page * 2]
        return [{"id": i, "updated_at": stamps[i]} for i in ids]

    api = FakeApi({"/api/v2/tickets": tickets})
    cfg = {"domain": "acme", "api_key": "key", "include_solutions": False}
    src = FreshdeskSource(
        FreshdeskSource.validate_config(cfg), client=api.client("https://acme.freshdesk.com")
    )
    records, states = await read_all(
        src, only=["tickets"], incremental=True, state={"tickets": {"cursor": stamps[1]}}
    )
    # Ticket 4 sits on the boundary and is read twice: nothing sharing its stamp may be lost.
    assert [t["id"] for t in records["tickets"]] == [1, 2, 3, 4, 4, 5]
    assert [
        (c.url.params["updated_since"], c.url.params["page"]) for c in api.calls("/api/v2/tickets")
    ] == [(stamps[1], "1"), (stamps[1], "2"), (stamps[4], "1"), (stamps[4], "2")]
    assert states["tickets"]["cursor"] == "2026-01-05T00:00:00+00:00"


async def test_asana_tasks_keep_project_query_and_per_project_cursor() -> None:
    api = FakeApi(
        {
            "/api/1.0/projects": {
                "data": [{"gid": "P1", "name": "Launch"}, {"gid": "P2", "name": "Skip"}]
            },
            "/api/1.0/tasks": lambda r: {
                "data": [
                    {"gid": "T-" + r.url.params["project"], "modified_at": "2026-01-05T00:00:00Z"}
                ]
            },
        }
    )
    cfg = {"access_token": "pat", "project_gids": ["P1"]}
    src = AsanaSource(
        AsanaSource.validate_config(cfg), client=api.client("https://app.asana.com/api/1.0")
    )
    prior = {
        "tasks": {"cursor": "2026-01-01T00:00:00Z", "by_parent": {"P1": "2026-01-01T00:00:00Z"}}
    }
    records, states = await read_all(src, only=["tasks"], incremental=True, state=prior)
    assert records["tasks"] == [
        {"gid": "T-P1", "modified_at": "2026-01-05T00:00:00Z", "project_gid": "P1"}
    ]
    call = api.calls("/api/1.0/tasks")[0]
    assert (
        call.url.params["project"] == "P1"
        and call.url.params["modified_since"] == "2026-01-01T00:00:00Z"
    )
    assert "opt_fields" in call.url.params
    assert states["tasks"]["by_parent"] == {"P1": "2026-01-05T00:00:00+00:00"}


async def test_testrail_hand_built_urls_and_bare_list_payloads() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> Any:
        raw = request.url.raw_path.decode()
        seen.append(raw)
        if "get_projects" in raw:
            return {"offset": 0, "limit": 250, "size": 1, "projects": [{"id": 1, "name": "App"}]}
        if "get_suites/1" in raw:
            return [{"id": 7, "project_id": 1, "name": "Smoke"}]  # older servers: bare list
        assert "get_cases/1&suite_id=7" in raw and "updated_after=1767225600" in raw
        return {"cases": [{"id": 50, "title": "Login", "updated_on": 1767312000}]}

    api = FakeApi({"/index.php": handler})
    cfg = {"base_url": "https://tr.test", "username": "u", "api_key": "k"}
    src = TestRailSource(TestRailSource.validate_config(cfg), client=api.client("https://tr.test"))
    records, states = await read_all(src, incremental=True, state={"cases": {"cursor": 1767225600}})
    assert records["cases"][0]["title"] == "Login" and records["suites"][0]["name"] == "Smoke"
    assert seen[0].startswith("/index.php?/api/v2/get_projects&limit=250&offset=0")
    assert states["cases"] == {"cursor": 1767312000}


async def test_clickup_epoch_millis_cursor_and_last_page_flag() -> None:
    api = FakeApi(
        {
            "/api/v2/team/T/space": {"spaces": [{"id": "s"}]},
            "/api/v2/team/T/task": lambda r: {
                "tasks": [{"id": "t" + r.url.params["page"], "date_updated": "1767312000000"}],
                "last_page": r.url.params["page"] == "1",
            },
        }
    )
    cfg = {"api_token": "pk", "team_id": "T"}
    src = ClickUpSource(
        ClickUpSource.validate_config(cfg), client=api.client("https://api.clickup.com/api/v2")
    )
    records, states = await read_all(
        src, incremental=True, state={"tasks": {"cursor": "1767225600000"}}
    )
    assert [t["id"] for t in records["tasks"]] == ["t0", "t1"]
    assert api.calls("/api/v2/team/T/task")[0].url.params["date_updated_gt"] == "1767225600000"
    assert states["tasks"] == {"cursor": "1767312000000"}
    assert api.requests[0].headers["Authorization"] == "pk"


async def test_productboard_links_and_cursor_paging() -> None:
    api = FakeApi(
        {
            "/products": {"data": []},
            "/components": {"data": []},
            "/features": lambda r: (
                {
                    "data": [
                        {
                            "id": "f1",
                            "description": "<p>SSO</p>",
                            "updatedAt": "2026-01-01T00:00:00Z",
                        }
                    ],
                    "links": {"next": "https://api.productboard.com/features?pageOffset=1"},
                }
                if "pageOffset" not in r.url.params
                else {
                    "data": [{"id": "f2", "updatedAt": "2026-01-02T00:00:00Z"}],
                    "links": {"next": None},
                }
            ),
            "/notes": {
                "data": [
                    {"id": "n1", "content": "<b>Need SSO</b>", "updatedAt": "2026-01-03T00:00:00Z"}
                ]
            },
        }
    )
    src = ProductboardSource(
        ProductboardSource.validate_config({"api_token": "t"}),
        client=api.client("https://api.productboard.com"),
    )
    records, _ = await read_all(
        src, incremental=True, state={"notes": {"cursor": "2026-01-02T00:00:00Z"}}
    )
    assert [f["id"] for f in records["features"]] == ["f1", "f2"]
    assert records["features"][0]["description_text"] == "SSO"
    assert records["notes"][0]["content_text"] == "Need SSO"
    assert api.calls("/notes")[0].url.params["updatedFrom"] == "2026-01-02T00:00:00Z"
    assert api.requests[0].headers["X-Version"] == "1"
