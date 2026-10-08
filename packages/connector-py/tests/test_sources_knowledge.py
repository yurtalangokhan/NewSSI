"""Knowledge-base sources replayed against fake APIs."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from connector import ConfigValidationError
from connector.sources.axero import AxeroSource
from connector.sources.bookstack import BookStackSource
from connector.sources.canvas import CanvasSource
from connector.sources.coda import CodaSource
from connector.sources.discourse import DiscourseSource
from connector.sources.document360 import Document360Source
from connector.sources.gitbook import GitBookSource
from connector.sources.google_sites import GoogleSitesSource
from connector.sources.guru import GuruSource
from connector.sources.loopio import LoopioSource
from connector.sources.lumapps import LumAppsSource
from connector.sources.mediawiki import MediaWikiSource
from connector.sources.notion import NotionSource
from connector.sources.outline import OutlineSource
from connector.sources.slab import SlabSource, quill_to_text
from connector.sources.wikipedia import WikipediaSource
from tests.fake_api import FakeApi, read_all


def _rich(text: str) -> list[dict[str, Any]]:
    return [{"plain_text": text}]


async def test_notion_pages_with_nested_blocks_and_incremental_filter() -> None:
    def search(request: httpx.Request) -> dict[str, Any]:
        body = json.loads(request.content)
        assert body["sort"] == {"direction": "ascending", "timestamp": "last_edited_time"}
        if body["filter"]["value"] == "database":
            return {"results": [{"id": "db1", "title": _rich("Roadmap")}], "has_more": False}
        return {
            "results": [
                {
                    "id": "p1",
                    "last_edited_time": "2026-01-01T00:00:00.000Z",
                    "properties": {"Name": {"type": "title", "title": _rich("Old")}},
                },
                {
                    "id": "p2",
                    "last_edited_time": "2026-01-05T00:00:00.000Z",
                    "properties": {"Name": {"type": "title", "title": _rich("Handbook")}},
                },
            ],
            "has_more": False,
        }

    api = FakeApi(
        {
            "POST /v1/search": search,
            "/v1/blocks/p2/children": {
                "results": [
                    {"id": "b1", "type": "heading_1", "heading_1": {"rich_text": _rich("Intro")}},
                    {
                        "id": "b2",
                        "type": "toggle",
                        "toggle": {"rich_text": _rich("More")},
                        "has_children": True,
                    },
                ],
                "has_more": False,
            },
            "/v1/blocks/b2/children": {
                "results": [
                    {"id": "b3", "type": "paragraph", "paragraph": {"rich_text": _rich("Deep")}}
                ],
                "has_more": False,
            },
        }
    )
    src = NotionSource(NotionSource.validate_config({"token": "secret"}), client=api.client())
    prior = {"pages": {"cursor": "2026-01-02T00:00:00Z"}}
    records, states = await read_all(src, incremental=True, state=prior)
    assert [p["id"] for p in records["pages"]] == ["p2"]
    assert records["pages"][0]["title_text"] == "Handbook"
    assert records["pages"][0]["content"] == "Intro\nMore\nDeep"
    assert records["databases"][0]["title_text"] == "Roadmap"
    assert states["pages"] == {"cursor": "2026-01-05T00:00:00+00:00"}
    first = api.requests[0]
    assert first.headers["Authorization"] == "Bearer secret"
    assert first.headers["Notion-Version"] == "2022-06-28"
    assert "/v1/blocks/p1/children" not in api.paths()  # filtered pages are not enriched


async def test_bookstack_detail_and_server_side_filter() -> None:
    api = FakeApi(
        {
            "/api/shelves": {"data": [], "total": 0},
            "/api/books": {
                "data": [{"id": 1, "name": "Ops", "updated_at": "2026-01-01T00:00:00Z"}],
                "total": 1,
            },
            "/api/chapters": {"data": [], "total": 0},
            "/api/pages": {
                "data": [{"id": 7, "name": "Runbook", "updated_at": "2026-01-03T10:00:00Z"}],
                "total": 1,
            },
            "/api/pages/7": {"id": 7, "html": "<p>Restart</p>", "markdown": "Restart"},
        }
    )
    cfg = {"base_url": "https://docs.acme.com", "token_id": "id", "token_secret": "sec"}
    src = BookStackSource(BookStackSource.validate_config(cfg), client=api.client())
    assert (await src.check()).ok
    prior = {"pages": {"cursor": "2026-01-02T08:30:00Z"}}
    records, states = await read_all(src, incremental=True, state=prior)
    assert records["pages"][0]["markdown"] == "Restart"
    call = api.calls("/api/pages")[0]
    assert call.url.params["filter[updated_at:gt]"] == "2026-01-02 08:30:00"
    assert call.url.params["count"] == "100" and call.headers["Authorization"] == "Token id:sec"
    assert states["pages"]["cursor"] == "2026-01-03T10:00:00+00:00"


async def test_canvas_link_header_paging_and_course_children() -> None:
    def courses(request: httpx.Request) -> httpx.Response:
        if "page" not in request.url.params:
            link = '<https://c.test/api/v1/courses?page=2&per_page=100>; rel="next"'
            return httpx.Response(200, json=[{"id": 1, "name": "Bio"}], headers={"Link": link})
        return httpx.Response(200, json=[{"id": 2, "name": "Chem"}])

    api = FakeApi(
        {
            "/api/v1/courses": courses,
            "/api/v1/courses/1/pages": [{"page_id": 10, "title": "Syllabus", "body": "<p>x</p>"}],
            "/api/v1/courses/2/pages": httpx.Response(403, json={}),
            "/api/v1/courses/1/assignments": [{"id": 5, "name": "Essay"}],
            "/api/v1/courses/2/assignments": [],
            "/api/v1/courses/1/discussion_topics": [],
            "/api/v1/courses/2/discussion_topics": [{"id": 9, "title": "Exam moved"}],
        }
    )
    cfg = {"base_url": "https://c.test", "access_token": "tok"}
    src = CanvasSource(CanvasSource.validate_config(cfg), client=api.client("https://c.test"))
    records, _ = await read_all(src)
    assert [c["id"] for c in records["courses"]] == [1, 2]
    assert records["pages"] == [
        {"page_id": 10, "title": "Syllabus", "body": "<p>x</p>", "course_id": 1}
    ]
    assert records["announcements"][0]["course_id"] == 2
    assert api.calls("/api/v1/courses/1/pages")[0].url.params["include[]"] == "body"
    assert (
        api.calls("/api/v1/courses/1/discussion_topics")[0].url.params["only_announcements"]
        == "true"
    )


async def test_coda_docs_pages_tables() -> None:
    api = FakeApi(
        {
            "/apis/v1/docs": lambda r: (
                {"items": [{"id": "d1", "updatedAt": "2026-01-01T00:00:00Z"}], "nextPageToken": "t"}
                if "pageToken" not in r.url.params
                else {"items": [{"id": "d2", "updatedAt": "2026-01-02T00:00:00Z"}]}
            ),
            "/apis/v1/docs/d1/pages": {"items": [{"id": "pg1", "name": "Home"}]},
            "/apis/v1/docs/d2/pages": {"items": []},
            "/apis/v1/docs/d1/tables": {"items": [{"id": "t1"}]},
            "/apis/v1/docs/d2/tables": {"items": []},
        }
    )
    src = CodaSource(
        CodaSource.validate_config({"api_token": "t"}), client=api.client("https://coda.io/apis/v1")
    )
    records, _ = await read_all(src)
    assert [d["id"] for d in records["docs"]] == ["d1", "d2"]
    assert records["pages"] == [{"id": "pg1", "name": "Home", "doc_id": "d1"}]
    assert records["tables"][0]["doc_id"] == "d1"


async def test_document360_articles_with_detail() -> None:
    api = FakeApi(
        {
            "/v2/ProjectVersions": {"data": [{"id": "v1", "version_code_name": "v1"}]},
            "/v2/ProjectVersions/v1/articles": {
                "data": [{"id": "a1", "title": "Setup", "modified_at": "2026-01-01T00:00:00Z"}]
            },
            "/v2/Articles/a1/en": {"data": {"id": "a1", "html_content": "<h1>Setup</h1><p>Go</p>"}},
        }
    )
    src = Document360Source(
        Document360Source.validate_config({"api_token": "k"}), client=api.client()
    )
    records, _ = await read_all(src)
    assert records["articles"][0]["content_text"] == "Setup\nGo"
    assert records["articles"][0]["project_version_id"] == "v1"
    assert api.requests[0].headers["api_token"] == "k"


async def test_discourse_topics_and_backward_post_paging() -> None:
    def latest(request: httpx.Request) -> dict[str, Any]:
        page = int(request.url.params["page"])
        more = "/latest?page=1" if page == 0 else None
        return {
            "topic_list": {
                "topics": [{"id": page + 1, "bumped_at": "2026-01-01T00:00:00Z"}],
                "more_topics_url": more,
            }
        }

    def posts(request: httpx.Request) -> dict[str, Any]:
        before = request.url.params.get("before")
        if before is None:
            return {"latest_posts": [{"id": 9, "cooked": "<p>new</p>"}, {"id": 8, "raw": "older"}]}
        return {"latest_posts": [{"id": 7, "raw": "oldest"}] if before == "8" else []}

    api = FakeApi(
        {
            "/categories.json": {"category_list": {"categories": [{"id": 1, "name": "General"}]}},
            "/latest.json": latest,
            "/posts.json": posts,
        }
    )
    cfg = {"base_url": "https://forum.test", "api_key": "k", "api_username": "bot"}
    src = DiscourseSource(
        DiscourseSource.validate_config(cfg), client=api.client("https://forum.test")
    )
    records, _ = await read_all(src)
    assert [t["id"] for t in records["topics"]] == [1, 2]
    assert [(p["id"], p["text"]) for p in records["posts"]] == [
        (9, "new"),
        (8, "older"),
        (7, "oldest"),
    ]
    assert (
        api.requests[0].headers["Api-Key"] == "k"
        and api.requests[0].headers["Api-Username"] == "bot"
    )
    assert api.calls("/latest.json")[0].url.params["ascending"] == "false"  # newest first

    # Incremental: the first page is older than the cursor, so the second is never asked for.
    api.requests.clear()
    inc, _ = await read_all(
        src, only=["topics"], incremental=True, state={"topics": {"cursor": "2026-01-02T00:00:00Z"}}
    )
    assert inc == {} and len(api.calls("/latest.json")) == 1


async def test_discourse_without_api_key_is_anonymous() -> None:
    api = FakeApi(
        {"/categories.json": {"category_list": {"categories": [{"id": 1, "name": "General"}]}}}
    )
    src = DiscourseSource(
        DiscourseSource.validate_config({"base_url": "https://forum.test"}),
        client=api.client("https://forum.test"),
    )
    assert (await src.check()).ok
    records, _ = await read_all(src, only=["categories"])
    assert [c["name"] for c in records["categories"]] == ["General"]
    assert all("Api-Key" not in r.headers and "Api-Username" not in r.headers for r in api.requests)


async def test_gitbook_flattens_page_tree_and_fetches_markdown() -> None:
    api = FakeApi(
        {
            "/v1/orgs/org1/spaces": {"items": [{"id": "s1", "title": "Docs"}]},
            "/v1/spaces/s1/content": {
                "pages": [
                    {
                        "id": "p1",
                        "title": "Guide",
                        "type": "document",
                        "pages": [{"id": "p2", "title": "Install", "type": "document"}],
                    },
                    {"id": "g1", "title": "Group", "type": "group", "pages": []},
                ]
            },
            "/v1/spaces/s1/content/page/p1": {"markdown": "# Guide"},
            "/v1/spaces/s1/content/page/p2": {"markdown": "# Install"},
        }
    )
    cfg = {"api_token": "t", "organization_id": "org1"}
    src = GitBookSource(GitBookSource.validate_config(cfg), client=api.client())
    records, _ = await read_all(src)
    assert [(p["id"], p["markdown"]) for p in records["pages"]] == [
        ("p1", "# Guide"),
        ("p2", "# Install"),
    ]
    assert records["pages"][1]["breadcrumb"] == ["Guide", "Install"]
    assert api.calls("/v1/spaces/s1/content/page/p1")[0].url.params["format"] == "markdown"


async def test_slab_posts_quill_text_and_incremental() -> None:
    delta = json.dumps(
        {"ops": [{"insert": "Hello "}, {"insert": {"image": "x"}}, {"insert": "world\n"}]}
    )

    def graphql(request: httpx.Request) -> dict[str, Any]:
        query = json.loads(request.content)["query"]
        if "topics {" in query and "posts" not in query:
            return {"data": {"organization": {"topics": [{"id": "t1", "name": "Eng"}]}}}
        return {
            "data": {
                "organization": {
                    "posts": [
                        {
                            "id": "1",
                            "title": "Old",
                            "updatedAt": "2026-01-01T00:00:00Z",
                            "content": delta,
                        },
                        {
                            "id": "2",
                            "title": "New",
                            "updatedAt": "2026-01-09T00:00:00Z",
                            "content": delta,
                        },
                    ]
                }
            }
        }

    api = FakeApi({"POST /v1/graphql": graphql})
    cfg = {"api_token": "tok", "team_url": "https://acme.slab.com"}
    src = SlabSource(SlabSource.validate_config(cfg), client=api.client())
    prior = {"posts": {"cursor": "2026-01-05T00:00:00Z"}}
    records, states = await read_all(src, incremental=True, state=prior)
    assert [(p["id"], p["content_text"]) for p in records["posts"]] == [("2", "Hello world")]
    assert records["posts"][0]["url"] == "https://acme.slab.com/posts/2"
    assert records["topics"] == [{"id": "t1", "name": "Eng"}]
    assert states["posts"]["cursor"] == "2026-01-09T00:00:00+00:00"
    assert api.requests[0].headers["Authorization"] == "tok"
    assert quill_to_text("not json") == "not json" and quill_to_text(None) == ""


async def test_lumapps_and_outline_post_body_pagination() -> None:
    def lumapps(request: httpx.Request) -> dict[str, Any]:
        body = json.loads(request.content)
        assert body["lang"] == "en" and body["maxResults"] == 100 and "instanceId" not in body
        if "cursor" not in body:
            return {
                "items": [{"id": "c1", "updatedAt": "2026-01-01T00:00:00Z"}],
                "more": True,
                "cursor": "k",
            }
        return {"items": [{"id": "c2", "updatedAt": "2026-01-02T00:00:00Z"}], "more": False}

    api = FakeApi({"POST /_ah/api/lumapps/v1/content/list": lumapps})
    src = LumAppsSource(LumAppsSource.validate_config({"access_token": "t"}), client=api.client())
    records, _ = await read_all(src)
    assert [c["id"] for c in records["contents"]] == ["c1", "c2"]

    def documents(request: httpx.Request) -> dict[str, Any]:
        body = json.loads(request.content)
        assert body["sort"] == "updatedAt" and body["limit"] == 100 and body["offset"] == 0
        return {"data": [{"id": "d1", "text": "# Hi", "updatedAt": "2026-01-01T00:00:00Z"}]}

    api = FakeApi(
        {
            "POST /api/collections.list": {"data": [{"id": "col"}]},
            "POST /api/documents.list": documents,
        }
    )
    src = OutlineSource(OutlineSource.validate_config({"api_token": "ol"}), client=api.client())
    records, _ = await read_all(src)
    assert records["documents"][0]["text"] == "# Hi" and records["collections"] == [{"id": "col"}]


async def test_axero_entity_types_and_space_filter() -> None:
    api = FakeApi(
        {
            "/api/spaces": {"ResponseData": [{"SpaceID": 5}]},
            "/api/content/list": lambda r: {
                "ResponseData": (
                    [
                        {
                            "ContentID": int(r.url.params["EntityType"]),
                            "ContentBody": "<b>Hi</b>",
                            "DateUpdated": "2026-01-01T00:00:00Z",
                        }
                    ]
                    if r.url.params["StartPage"] == "1"
                    else []
                )
            },
        }
    )
    cfg = {"base_url": "https://ax.test", "api_key": "k", "space_ids": [5, 6]}
    src = AxeroSource(AxeroSource.validate_config(cfg), client=api.client())
    records, _ = await read_all(src)
    assert {s: r[0]["ContentID"] for s, r in records.items() if s != "spaces"} == {
        "articles": 3,
        "blogs": 4,
        "wikis": 9,
    }
    assert records["wikis"][0]["content_text"] == "Hi"
    call = api.calls("/api/content/list")[0]
    assert call.url.params["SpaceID"] == "5,6" and call.headers["Rest-Api-Key"] == "k"


def _wiki_page(pageid: int, title: str, stamp: str) -> dict[str, Any]:
    return {
        "pageid": pageid,
        "ns": 0,
        "title": title,
        "fullurl": f"https://w.test/wiki/{title}",
        "revisions": [
            {
                "revid": pageid * 10,
                "timestamp": stamp,
                "slots": {"main": {"content": f"text of {title}"}},
            }
        ],
    }


async def test_mediawiki_continue_paging_and_categories() -> None:
    def handler(request: httpx.Request) -> dict[str, Any]:
        p = request.url.params
        assert p["formatversion"] == "2" and p["rvslots"] == "main"
        if p.get("generator") == "categorymembers":
            assert p["gcmtitle"] == "Category:Ops"
            return {
                "query": {
                    "pages": [
                        _wiki_page(1, "A", "2026-01-01T00:00:00Z"),
                        {"title": "Gone", "missing": True},
                    ]
                }
            }
        if "gapcontinue" not in p:
            return {
                "continue": {"gapcontinue": "B", "continue": "gapcontinue||"},
                "query": {"pages": [_wiki_page(1, "A", "2026-01-01T00:00:00Z")]},
            }
        return {"query": {"pages": [_wiki_page(2, "B", "2026-01-04T00:00:00Z")]}}

    api = FakeApi({"/w/api.php": handler})
    src = MediaWikiSource(
        MediaWikiSource.validate_config({"api_url": "https://w.test/w/api.php"}),
        client=api.client("https://w.test/w"),
    )
    records, states = await read_all(
        src, incremental=True, state={"pages": {"cursor": "2026-01-02T00:00:00Z"}}
    )
    assert [(p["pageid"], p["content"]) for p in records["pages"]] == [(2, "text of B")]
    assert states["pages"]["cursor"] == "2026-01-04T00:00:00+00:00"

    by_category = MediaWikiSource(
        MediaWikiSource.validate_config(
            {"api_url": "https://w.test/w/api.php", "categories": ["Ops"]}
        ),
        client=api.client("https://w.test/w"),
    )
    records, _ = await read_all(by_category)
    assert [p["title"] for p in records["pages"]] == ["A"]  # the missing page is dropped


async def test_wikipedia_uses_language_host_and_requires_scope() -> None:
    api = FakeApi(
        {
            "/w/api.php": lambda r: {
                "query": {
                    "pages": [
                        _wiki_page(3, r.url.params["titles"].split("|")[0], "2026-01-01T00:00:00Z")
                    ]
                }
            }
        }
    )
    src = WikipediaSource(
        WikipediaSource.validate_config({"language": "tr", "titles": ["Ankara", "İzmir"]}),
        client=api.client(),
    )
    records, _ = await read_all(src)
    assert records["pages"][0]["title"] == "Ankara"
    assert api.requests[0].url.host == "tr.wikipedia.org"
    assert api.requests[0].url.params["titles"] == "Ankara|İzmir"
    assert "wikipedia source" in api.requests[0].headers["User-Agent"]
    with pytest.raises(ConfigValidationError):
        WikipediaSource.validate_config({"language": "en"})


async def test_loopio_oauth_client_credentials_and_stack_filter() -> None:
    def token(request: httpx.Request) -> dict[str, Any]:
        form = dict(p.split("=") for p in request.content.decode().split("&"))
        assert form["grant_type"] == "client_credentials" and form["scope"] == "library%3Aread"
        return {"access_token": "T", "expires_in": 3600}

    def entries(request: httpx.Request) -> dict[str, Any]:
        assert request.headers["Authorization"] == "Bearer T"
        return {
            "totalPages": 1,
            "items": [
                {
                    "id": 1,
                    "lastUpdatedDate": "2026-01-01T00:00:00Z",
                    "location": {"stack": {"name": "Security"}},
                    "questions": [{"text": "<p>SOC2?</p>"}],
                    "answer": {"text": "<b>Yes</b>"},
                },
                {
                    "id": 2,
                    "lastUpdatedDate": "2026-01-01T00:00:00Z",
                    "location": {"stack": {"name": "Legal"}},
                },
            ],
        }

    api = FakeApi({"POST /oauth2/access_token": token, "/data/v2/libraryEntries": entries})
    cfg = {"client_id": "c", "client_secret": "s", "stack_name": "Security"}
    src = LoopioSource(LoopioSource.validate_config(cfg), client=api.client())
    records, _ = await read_all(src)
    assert [
        (e["id"], e["questions_text"], e["answer_text"]) for e in records["library_entries"]
    ] == [(1, ["SOC2?"], "Yes")]
    assert len(api.calls("/oauth2/access_token")) == 1


async def test_google_sites_crawls_within_site_only() -> None:
    root = "https://sites.google.com/acme.com/handbook"
    pages_html = {
        "/acme.com/handbook": (
            '<title>Home</title><a href="/acme.com/handbook/leave">L</a>'
            '<a href="https://evil.test/x">X</a>'
        ),
        "/acme.com/handbook/leave": (
            '<title>Leave</title><p>30 days</p><a href="/acme.com/handbook">back</a>'
        ),
    }
    api = FakeApi(
        {
            k: httpx.Response(200, text=v, headers={"content-type": "text/html"})
            for k, v in pages_html.items()
        }
    )
    src = GoogleSitesSource(
        GoogleSitesSource.validate_config({"site_urls": [root]}),
        client=api.client("https://sites.google.com"),
    )
    assert (await src.check()).ok
    records, _ = await read_all(src)
    assert [(p["title"], p["url"]) for p in records["pages"]] == [
        ("Home", root),
        ("Leave", f"{root}/leave"),
    ]
    assert "30 days" in records["pages"][1]["content"]
    assert not any(r.url.host == "evil.test" for r in api.requests)


async def test_guru_cards_basic_auth_and_html_text() -> None:
    api = FakeApi(
        {
            "/api/v1/collections": [{"id": "col1", "name": "Support"}],
            "/api/v1/search/query": [
                {
                    "id": "c1",
                    "preferredPhrase": "Refunds",
                    "content": "<p>30 days</p>",
                    "lastModified": "2026-01-01T00:00:00Z",
                }
            ],
        }
    )
    cfg = {"username": "me@acme.com", "api_token": "tok", "query": "verified"}
    src = GuruSource(
        GuruSource.validate_config(cfg), client=api.client("https://api.getguru.com/api/v1")
    )
    records, _ = await read_all(src)
    assert (records["cards"][0]["title"], records["cards"][0]["content_text"]) == (
        "Refunds",
        "30 days",
    )
    call = api.calls("/api/v1/search/query")[0]
    assert call.url.params["q"] == "verified" and call.headers["Authorization"].startswith("Basic ")
