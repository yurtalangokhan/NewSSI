"""Messaging, sales, code-repository and miscellaneous sources replayed against fakes."""

from __future__ import annotations

import base64
import json
import os
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from connector import ConfigValidationError
from connector.sources.bitbucket import BitbucketSource
from connector.sources.braintrust import BraintrustSource
from connector.sources.discord import DiscordSource
from connector.sources.file_upload import FileUploadSource
from connector.sources.fireflies import FirefliesSource
from connector.sources.github import GitHubSource
from connector.sources.gmail import GmailSource
from connector.sources.gong import GongSource
from connector.sources.highspot import HighspotSource
from connector.sources.hubspot import HubSpotSource
from connector.sources.imap import ImapSource
from connector.sources.microsoft_teams import MicrosoftTeamsSource
from connector.sources.salesforce import SalesforceSource
from connector.sources.slack import SlackSource
from connector.sources.xenforo import XenForoSource
from connector.sources.zulip import ZulipSource
from tests.fake_api import FakeApi, read_all

GRAPH = "https://graph.microsoft.com/v1.0"

# ---------------------------------------------------------------------------
# messaging
# ---------------------------------------------------------------------------


async def test_slack_channels_messages_and_not_in_channel_is_skipped() -> None:
    def history(request: httpx.Request) -> dict[str, Any]:
        channel = request.url.params["channel"]
        if channel == "C2":
            return {"ok": False, "error": "not_in_channel"}
        assert request.url.params["oldest"] == "1767225600.000100"
        return {"ok": True, "messages": [{"ts": "1767312000.000200", "text": "deploy done"}]}

    api = FakeApi(
        {
            "/api/conversations.list": {
                "ok": True,
                "channels": [{"id": "C1", "name": "ops"}, {"id": "C2", "name": "secret"}],
                "response_metadata": {"next_cursor": ""},
            },
            "/api/users.list": {"ok": True, "members": [{"id": "U1"}]},
            "/api/conversations.history": history,
        }
    )
    src = SlackSource(
        SlackSource.validate_config({"bot_token": "xoxb"}),
        client=api.client("https://slack.com/api"),
    )
    prior = {"messages": {"cursor": "1767225600.000100", "by_parent": {"C1": "1767225600.000100"}}}
    records, states = await read_all(src, incremental=True, state=prior)
    assert [m["text"] for m in records["messages"]] == ["deploy done"]
    assert records["messages"][0]["channel_id"] == "C1"
    assert records["messages"][0]["sent_at"].startswith("2026-01-02T00:00:00")
    assert states["messages"]["by_parent"] == {"C1": "1767312000.000200"}
    assert api.requests[0].headers["Authorization"] == "Bearer xoxb"


async def test_slack_auth_failure_is_reported_by_check() -> None:
    api = FakeApi({"/api/conversations.list": {"ok": False, "error": "invalid_auth"}})
    src = SlackSource(
        SlackSource.validate_config({"bot_token": "bad"}),
        client=api.client("https://slack.com/api"),
    )
    result = await src.check()
    assert not result.ok and "invalid_auth" in (result.message or "")


async def test_microsoft_teams_delta_links_per_channel() -> None:
    graph = "https://graph.microsoft.com/v1.0"

    def messages(request: httpx.Request) -> dict[str, Any]:
        assert request.headers["Authorization"] == "Bearer T"
        if request.url.params.get("$deltatoken") == "D1":
            return {
                "value": [{"id": "m2", "body": {"contentType": "text", "content": "new"}}],
                "@odata.deltaLink": f"{graph}/teams/t1/channels/c1/messages/delta?$deltatoken=D2",
            }
        return {
            "value": [
                {
                    "id": "m1",
                    "body": {"contentType": "html", "content": "<p>Hello <b>team</b></p>"},
                    "from": {"user": {"displayName": "Ann"}},
                    "createdDateTime": "2026-01-01T00:00:00Z",
                }
            ],
            "@odata.deltaLink": f"{graph}/teams/t1/channels/c1/messages/delta?$deltatoken=D1",
        }

    api = FakeApi(
        {
            "POST /tid/oauth2/v2.0/token": {"access_token": "T", "expires_in": 3600},
            "/v1.0/groups": {
                "value": [{"id": "t1", "displayName": "Eng"}, {"id": "t2", "displayName": "Other"}]
            },
            "/v1.0/teams/t1/channels": {"value": [{"id": "c1", "displayName": "General"}]},
            "/v1.0/teams/t1/channels/c1/messages/delta": messages,
        }
    )
    cfg = {"tenant_id": "tid", "client_id": "c", "client_secret": "s", "team_names": ["Eng"]}
    src = MicrosoftTeamsSource(MicrosoftTeamsSource.validate_config(cfg), client=api.client(graph))
    records, states = await read_all(src, incremental=True)
    msg = records["messages"][0]
    assert (msg["text"], msg["from"], msg["channel_name"], msg["team_name"]) == (
        "Hello team",
        "Ann",
        "General",
        "Eng",
    )
    assert [t["id"] for t in records["teams"]] == ["t1"]
    link = states["messages"]["delta_links"]["c1"]
    assert link.endswith("$deltatoken=D1")

    records, states = await read_all(
        src, only=["messages"], incremental=True, state={"messages": states["messages"]}
    )
    assert [m["id"] for m in records["messages"]] == ["m2"]
    assert states["messages"]["delta_links"]["c1"].endswith("$deltatoken=D2")


def _teams_api(delta: Any, replies: Any = None) -> FakeApi:
    routes: dict[str, Any] = {
        "POST /tid/oauth2/v2.0/token": {"access_token": "T", "expires_in": 3600},
        "/v1.0/groups": {"value": [{"id": "t1", "displayName": "Eng"}]},
        "/v1.0/teams/t1/channels": {
            "value": [{"id": "c1", "displayName": "General"}, {"id": "c2", "displayName": "Ops"}]
        },
        "/v1.0/teams/t1/channels/c1/messages/delta": delta,
        "/v1.0/teams/t1/channels/c2/messages/delta": {
            "value": [{"id": "n1", "body": {"content": "ops"}}],
            "@odata.deltaLink": f"{GRAPH}/teams/t1/channels/c2/messages/delta?$deltatoken=C2",
        },
    }
    for message_id, answer in (replies or {}).items():
        routes[f"/v1.0/teams/t1/channels/c1/messages/{message_id}/replies"] = answer
    return FakeApi(routes)


def _teams_source(api: FakeApi, **config: Any) -> MicrosoftTeamsSource:
    cfg = {"tenant_id": "tid", "client_id": "c", "client_secret": "s", **config}
    return MicrosoftTeamsSource(MicrosoftTeamsSource.validate_config(cfg), client=api.client(GRAPH))


async def test_microsoft_teams_a_failing_replies_request_fails_the_sync() -> None:
    three = {
        "value": [{"id": m, "body": {"content": m}} for m in ("m1", "m2", "m3")],
        "@odata.deltaLink": f"{GRAPH}/teams/t1/channels/c1/messages/delta?$deltatoken=C1",
    }
    api = _teams_api(
        three,
        replies={
            "m1": {"value": [{"id": "r1", "body": {"content": "re"}}]},
            "m2": httpx.Response(404, json={"error": {"code": "NotFound"}}),
            "m3": {"value": []},
        },
    )

    # The rest of the channel must not be dropped without a word, and without a delta
    # link, on every run: the failure is the sync's.
    with pytest.raises(httpx.HTTPStatusError, match="404"):
        await read_all(
            _teams_source(api, include_replies=True), only=["messages"], incremental=True
        )


async def test_microsoft_teams_skips_a_channel_it_may_not_read() -> None:
    api = _teams_api(httpx.Response(403, json={"error": {"code": "Forbidden"}}))

    records, states = await read_all(_teams_source(api), only=["messages"], incremental=True)

    assert [m["id"] for m in records["messages"]] == ["n1"]
    assert list(states["messages"]["delta_links"]) == ["c2"]


async def test_microsoft_teams_starts_over_when_its_delta_link_has_expired() -> None:
    def delta(request: httpx.Request) -> Any:
        if request.url.params.get("$deltatoken") == "OLD":
            return httpx.Response(410, json={"error": {"code": "SyncStateNotFound"}})
        return {
            "value": [{"id": "m1", "body": {"content": "again"}}],
            "@odata.deltaLink": f"{GRAPH}/teams/t1/channels/c1/messages/delta?$deltatoken=NEW",
        }

    api = _teams_api(delta)
    stored = {"c1": f"{GRAPH}/teams/t1/channels/c1/messages/delta?$deltatoken=OLD"}

    records, states = await read_all(
        _teams_source(api),
        only=["messages"],
        incremental=True,
        state={"messages": {"delta_links": stored}},
    )

    # A link the service no longer knows fails every run until someone resets the state.
    # A fresh delta lists the channel again and leaves a link that works.
    assert [m["id"] for m in records["messages"]] == ["m1", "n1"]
    assert states["messages"]["delta_links"]["c1"].endswith("$deltatoken=NEW")
    asked = [
        r.url.params.get("$deltatoken")
        for r in api.calls("/v1.0/teams/t1/channels/c1/messages/delta")
    ]
    assert asked == ["OLD", None]


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


async def test_gmail_list_detail_body_extraction_and_after_query() -> None:
    full = {
        "id": "m1",
        "threadId": "t1",
        "internalDate": "1767312000000",
        "snippet": "Hi",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "Subject", "value": "Invoice"},
                {"name": "From", "value": "a@x.com"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("Please pay")}},
                {"mimeType": "application/pdf", "filename": "inv.pdf", "body": {"size": 10}},
            ],
        },
    }
    api = FakeApi(
        {
            "/gmail/v1/users/me/messages": {"messages": [{"id": "m1", "threadId": "t1"}]},
            "/gmail/v1/users/me/messages/m1": full,
        }
    )
    cfg = {"access_token": "T", "query": "label:billing"}
    src = GmailSource(
        GmailSource.validate_config(cfg), client=api.client("https://gmail.googleapis.com")
    )
    records, states = await read_all(
        src, incremental=True, state={"messages": {"cursor": "2026-01-01T00:00:00Z"}}
    )
    msg = records["messages"][0]
    assert (msg["subject"], msg["from"], msg["body"]) == ("Invoice", "a@x.com", "Please pay")
    assert msg["attachments"] == [
        {"filename": "inv.pdf", "mime_type": "application/pdf", "size": 10}
    ]
    assert (
        api.calls("/gmail/v1/users/me/messages")[0].url.params["q"]
        == "label:billing after:1767225600"
    )
    assert api.calls("/gmail/v1/users/me/messages/m1")[0].url.params["format"] == "full"
    assert states["messages"]["cursor"] == "2026-01-02T00:00:00+00:00"


class _FakeImap:
    def __init__(self, mailbox: dict[int, bytes], validity: int = 7) -> None:
        self.mailbox, self.validity, self.searches = mailbox, validity, []
        self.logged_out = False

    def select(self, folder: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        return ("OK", [b"2"]) if folder == '"INBOX"' else ("NO", [b"nope"])

    def response(self, code: str) -> tuple[str, list[bytes]]:
        return code, [str(self.validity).encode()]

    def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
        if command == "SEARCH":
            self.searches.append(args[1:])
            start = int(str(args[1]).split()[1].split(":")[0])
            uids = [u for u in self.mailbox if u >= start] or [max(self.mailbox)]
            return "OK", [" ".join(map(str, uids)).encode()]
        wanted = [int(u) for u in str(args[0]).split(",")]
        data: list[Any] = []
        for u in wanted:
            data += [(f"1 (UID {u} RFC822 {{10}}".encode(), self.mailbox[u]), b")"]
        return "OK", data

    def logout(self) -> None:
        self.logged_out = True


def _mail(subject: str, body: str, html: bool = False) -> bytes:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, "a@x.com", "b@x.com"
    msg["Date"] = "Fri, 02 Jan 2026 10:00:00 +0000"
    msg["Message-ID"] = f"<{subject}@x>"
    msg.set_content(body, subtype="html" if html else "plain")
    msg.add_attachment(b"%PDF", maintype="application", subtype="pdf", filename="a.pdf")
    return msg.as_bytes()


def test_imap_default_client_verifies_the_server_certificate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # imaplib's own default context does not verify certificates: the password would go
    # to whoever answers on port 993. The client is built with a verifying context.
    import ssl

    from connector.sources import imap as module

    built: list[dict[str, Any]] = []

    class _Ssl:
        def __init__(self, host: str, port: int, **kwargs: Any) -> None:
            built.append({"host": host, "port": port, **kwargs})

        def login(self, user: str, password: str) -> None:
            pass

    monkeypatch.setattr(module.imaplib, "IMAP4_SSL", _Ssl)
    base = {"host": "mail.test", "username": "u", "password": "p"}
    module._default_client(ImapSource.validate_config(base))
    context = built[-1]["ssl_context"]
    assert context.verify_mode is ssl.CERT_REQUIRED and context.check_hostname is True

    module._default_client(ImapSource.validate_config({**base, "verify_ssl": False}))
    context = built[-1]["ssl_context"]
    assert context.verify_mode is ssl.CERT_NONE and context.check_hostname is False


async def test_imap_uid_incremental_and_uidvalidity_reset() -> None:
    fake = _FakeImap({1: _mail("one", "first"), 2: _mail("two", "<p>second</p>", html=True)})
    cfg = {"host": "mail.test", "username": "u", "password": "p"}
    src = ImapSource(ImapSource.validate_config(cfg), client_factory=lambda c: fake)
    assert (await src.check()).ok
    records, states = await read_all(src, incremental=True)
    assert [(m["uid"], m["subject"], m["body"].strip()) for m in records["messages"]] == [
        (1, "one", "first"),
        (2, "two", "second"),
    ]
    assert records["messages"][0]["attachments"] == [
        {"filename": "a.pdf", "content_type": "application/pdf"}
    ]
    assert records["messages"][0]["date"] == "2026-01-02T10:00:00+00:00"
    assert states["messages"] == {"folders": {"INBOX": {"uidvalidity": 7, "last_uid": 2}}}
    assert fake.logged_out

    again, _ = await read_all(src, incremental=True, state=states)
    assert again == {}  # "3:*" echoes the last UID; it must not be re-read
    fake.validity = 8  # server rebuilt the mailbox: start over
    reset, _ = await read_all(src, incremental=True, state=states)
    assert len(reset["messages"]) == 2


async def test_imap_undecodable_body_does_not_fail_the_run() -> None:
    # A charset Python does not know would raise on every run and the UID would never pass.
    odd = (
        b"Subject: odd\r\nFrom: a@x.com\r\nTo: b@x.com\r\nMessage-ID: <odd@x>\r\n"
        b'Content-Type: text/plain; charset="x-unknown"\r\n\r\nhello\r\n'
    )
    fake = _FakeImap({1: _mail("one", "first"), 2: odd, 3: _mail("three", "third")})
    cfg = {"host": "mail.test", "username": "u", "password": "p"}
    src = ImapSource(ImapSource.validate_config(cfg), client_factory=lambda c: fake)
    records, states = await read_all(src, incremental=True)
    by_uid = {m["uid"]: m for m in records["messages"]}
    assert [m["body"].strip() for m in records["messages"]] == ["first", "", "third"]
    assert by_uid[2]["subject"] == "odd" and "x-unknown" in by_uid[2]["parse_error"]
    assert by_uid[1]["parse_error"] is None
    assert states["messages"]["folders"]["INBOX"]["last_uid"] == 3


async def test_discord_forward_paging_by_max_snowflake() -> None:
    def messages(request: httpx.Request) -> list[dict[str, Any]]:
        after = int(request.url.params["after"])
        ids = [i for i in range(1, 151) if i > after][:100]
        return [
            {"id": str(i), "content": f"m{i}", "author": {"username": "bot"}} for i in reversed(ids)
        ]

    api = FakeApi(
        {
            "/api/v10/guilds/G/channels": [{"id": "c1", "type": 0}, {"id": "v1", "type": 2}],
            "/api/v10/channels/c1/messages": messages,
        }
    )
    cfg = {"bot_token": "tok", "guild_id": "G"}
    src = DiscordSource(
        DiscordSource.validate_config(cfg), client=api.client("https://discord.com/api/v10")
    )
    records, states = await read_all(src, incremental=True)
    assert (
        len(records["messages"]) == 150 and len(records["channels"]) == 1
    )  # voice channel dropped
    assert [c.url.params["after"] for c in api.calls("/api/v10/channels/c1/messages")] == [
        "0",
        "100",
    ]
    assert states["messages"] == {"cursor": "150", "by_parent": {"c1": "150"}}
    assert api.requests[0].headers["Authorization"] == "Bot tok"


async def test_xenforo_threads_and_posts() -> None:
    api = FakeApi(
        {
            "/api/nodes": {"nodes": [{"node_id": 1, "title": "General"}]},
            "/api/threads": {
                "threads": [{"thread_id": 5, "title": "Hi", "last_post_date": 1767312000}],
                "pagination": {"current_page": 1, "last_page": 1},
            },
            "/api/threads/5/posts": {
                "posts": [
                    {"post_id": 50, "message_parsed": "<p>Welcome</p>", "post_date": 1767312000}
                ],
                "pagination": {"last_page": 1},
            },
        }
    )
    cfg = {"base_url": "https://forum.test", "api_key": "k", "api_user_id": 1}
    src = XenForoSource(
        XenForoSource.validate_config(cfg), client=api.client("https://forum.test/api")
    )
    records, _ = await read_all(src)
    assert records["posts"][0]["text"] == "Welcome"
    assert records["threads"][0]["last_post_at"].startswith("2026-01-02")
    assert (
        api.requests[0].headers["XF-Api-Key"] == "k"
        and api.requests[0].headers["XF-Api-User"] == "1"
    )


async def test_zulip_anchor_paging_and_multi_stream_filter() -> None:
    def messages(request: httpx.Request) -> dict[str, Any]:
        anchor = request.url.params["anchor"]
        assert json.loads(request.url.params["narrow"]) == []
        if anchor == "10":
            assert request.url.params["include_anchor"] == "false"
            return {
                "messages": [
                    {
                        "id": 11,
                        "type": "stream",
                        "display_recipient": "dev",
                        "timestamp": 1767312000,
                    },
                    {
                        "id": 12,
                        "type": "stream",
                        "display_recipient": "random",
                        "timestamp": 1767312000,
                    },
                ],
                "found_newest": False,
            }
        return {
            "messages": [
                {"id": 13, "type": "stream", "display_recipient": "ops", "timestamp": 1767312000}
            ],
            "found_newest": True,
        }

    api = FakeApi(
        {
            "/api/v1/streams": {"streams": [{"stream_id": 1, "name": "dev"}]},
            "/api/v1/messages": messages,
        }
    )
    cfg = {
        "site_url": "https://z.test",
        "email": "bot@z.test",
        "api_key": "k",
        "stream_names": ["dev", "ops"],
    }
    src = ZulipSource(ZulipSource.validate_config(cfg), client=api.client("https://z.test/api/v1"))
    records, states = await read_all(src, incremental=True, state={"messages": {"cursor": 10}})
    assert [m["id"] for m in records["messages"]] == [11, 13]
    assert states["messages"] == {"cursor": 13}


# ---------------------------------------------------------------------------
# sales
# ---------------------------------------------------------------------------


async def test_salesforce_token_instance_url_describe_and_soql() -> None:
    def token(request: httpx.Request) -> dict[str, Any]:
        assert parse_qs(request.content.decode())["grant_type"] == ["client_credentials"]
        return {"access_token": "T", "instance_url": "https://acme.my.salesforce.com"}

    def query(request: httpx.Request) -> dict[str, Any]:
        assert request.url.host == "acme.my.salesforce.com"
        return {
            "records": [
                {
                    "attributes": {"type": "Account"},
                    "Id": "001",
                    "Name": "Acme",
                    "SystemModstamp": "2026-01-03T00:00:00.000+0000",
                }
            ],
            "done": False,
            "nextRecordsUrl": "/services/data/v60.0/query/01g-2000",
        }

    api = FakeApi(
        {
            "POST /services/oauth2/token": token,
            "/services/data/v60.0/sobjects/Account/describe": {
                "fields": [
                    {"name": "Id", "type": "id"},
                    {"name": "Name", "type": "string"},
                    {"name": "BillingAddress", "type": "address"},
                    {"name": "SystemModstamp", "type": "datetime"},
                ]
            },
            "/services/data/v60.0/query": query,
            "/services/data/v60.0/query/01g-2000": {
                "records": [
                    {"Id": "002", "Name": "Beta", "SystemModstamp": "2026-01-04T00:00:00.000+0000"}
                ],
                "done": True,
            },
        }
    )
    cfg = {
        "login_url": "https://acme.my.salesforce.com",
        "client_id": "c",
        "client_secret": "s",
        "objects": ["Account"],
    }
    src = SalesforceSource(
        SalesforceSource.validate_config(cfg), client=api.client("https://acme.my.salesforce.com")
    )
    records, states = await read_all(
        src, incremental=True, state={"account": {"cursor": "2026-01-02T00:00:00Z"}}
    )
    assert [(r["Id"], r["Name"]) for r in records["account"]] == [("001", "Acme"), ("002", "Beta")]
    assert "attributes" not in records["account"][0]
    soql = api.calls("/services/data/v60.0/query")[0].url.params["q"]
    assert soql == (
        "SELECT Id, Name, SystemModstamp FROM Account "
        "WHERE SystemModstamp > 2026-01-02T00:00:00Z ORDER BY SystemModstamp ASC"
    )
    assert states["account"]["cursor"] == "2026-01-04T00:00:00+00:00"
    with pytest.raises(ConfigValidationError):
        SalesforceSource.validate_config({"client_id": "c", "client_secret": "s", "username": "u"})


async def test_hubspot_list_for_full_refresh_and_search_for_incremental() -> None:
    def listing(request: httpx.Request) -> dict[str, Any]:
        assert request.url.params["properties"].startswith("email,")
        if "after" not in request.url.params:
            return {
                "results": [
                    {
                        "id": "1",
                        "properties": {"email": "a@x.com"},
                        "updatedAt": "2026-01-01T00:00:00Z",
                    }
                ],
                "paging": {"next": {"after": "2"}},
            }
        return {
            "results": [
                {"id": "2", "properties": {"email": "b@x.com"}, "updatedAt": "2026-01-02T00:00:00Z"}
            ]
        }

    def search(request: httpx.Request) -> dict[str, Any]:
        body = json.loads(request.content)
        flt = body["filterGroups"][0]["filters"][0]
        assert flt == {
            "propertyName": "lastmodifieddate",
            "operator": "GT",
            "value": "1767225600000",
        }
        assert body["sorts"][0]["direction"] == "ASCENDING" and body["limit"] == 100
        return {
            "results": [
                {"id": "3", "properties": {"email": "c@x.com"}, "updatedAt": "2026-01-05T00:00:00Z"}
            ]
        }

    api = FakeApi(
        {"GET /crm/v3/objects/contacts": listing, "POST /crm/v3/objects/contacts/search": search}
    )
    cfg = {"access_token": "pat", "objects": ["contacts"]}
    src = HubSpotSource(
        HubSpotSource.validate_config(cfg), client=api.client("https://api.hubapi.com")
    )
    full, _ = await read_all(src)
    assert [(c["id"], c["email"]) for c in full["contacts"]] == [("1", "a@x.com"), ("2", "b@x.com")]
    inc, states = await read_all(
        src, incremental=True, state={"contacts": {"cursor": "2026-01-01T00:00:00Z"}}
    )
    assert [c["id"] for c in inc["contacts"]] == ["3"]
    assert states["contacts"]["cursor"] == "2026-01-05T00:00:00+00:00"


async def test_hubspot_search_re_anchors_at_the_10000_result_cap() -> None:
    # HubSpot refuses ``after`` past 10 000 search results with a 400: a large gap would
    # never complete and leave no state. Past the cap a new search starts at the last stamp.
    bodies: list[dict[str, Any]] = []

    def search(request: httpx.Request) -> dict[str, Any]:
        body = json.loads(request.content)
        bodies.append(body)
        if "after" in body:
            raise AssertionError("paged past the 10 000 result cap")
        if body["filterGroups"][0]["filters"][0]["operator"] == "GT":  # the saved cursor
            return {
                "results": [{"id": "a", "properties": {}, "updatedAt": "2026-01-03T00:00:00Z"}],
                "paging": {"next": {"after": "10000"}},
            }
        return {
            "results": [
                {"id": "a", "properties": {}, "updatedAt": "2026-01-03T00:00:00Z"},
                {"id": "c", "properties": {}, "updatedAt": "2026-01-04T00:00:00Z"},
            ]
        }

    api = FakeApi({"POST /crm/v3/objects/deals/search": search})
    cfg = {"access_token": "pat", "objects": ["deals"]}
    src = HubSpotSource(
        HubSpotSource.validate_config(cfg), client=api.client("https://api.hubapi.com")
    )
    inc, states = await read_all(
        src, incremental=True, state={"deals": {"cursor": "2026-01-01T00:00:00Z"}}
    )
    # The boundary record is read twice (records sharing its stamp must not be lost); the
    # destination's record keys absorb the duplicate.
    assert [d["id"] for d in inc["deals"]] == ["a", "a", "c"]
    assert bodies[1]["filterGroups"][0]["filters"][0] == {
        "propertyName": "hs_lastmodifieddate",
        "operator": "GTE",
        "value": "1767398400000",
    }
    assert states["deals"]["cursor"] == "2026-01-04T00:00:00+00:00"


async def test_gong_calls_cursor_and_transcript_text() -> None:
    def transcripts(request: httpx.Request) -> dict[str, Any]:
        assert json.loads(request.content)["filter"]["fromDateTime"] == "2020-01-01T00:00:00Z"
        return {
            "callTranscripts": [
                {
                    "callId": "c1",
                    "transcript": [
                        {"speakerId": "s1", "sentences": [{"text": "Hello."}, {"text": "Pricing?"}]}
                    ],
                }
            ],
            "records": {},
        }

    api = FakeApi(
        {
            "/v2/users": {"users": [{"id": "u1"}], "records": {}},
            "/v2/calls": lambda r: (
                {
                    "calls": [{"id": "c1", "started": "2026-01-02T00:00:00Z"}],
                    "records": {"cursor": "n"},
                }
                if "cursor" not in r.url.params
                else {"calls": [{"id": "c2", "started": "2026-01-03T00:00:00Z"}], "records": {}}
            ),
            "POST /v2/calls/transcript": transcripts,
        }
    )
    cfg = {"access_key": "k", "access_key_secret": "s", "start_date": "2020-01-01T00:00:00Z"}
    src = GongSource(GongSource.validate_config(cfg), client=api.client("https://api.gong.io"))
    records, _ = await read_all(
        src, incremental=True, state={"calls": {"cursor": "2026-01-01T00:00:00Z"}}
    )
    assert [c["id"] for c in records["calls"]] == ["c1", "c2"]
    assert records["transcripts"][0]["text"] == "s1: Hello. Pricing?"
    assert api.calls("/v2/calls")[0].url.params["fromDateTime"] == "2026-01-01T00:00:00Z"


async def test_fireflies_skip_paging_and_from_date() -> None:
    def graphql(request: httpx.Request) -> dict[str, Any]:
        variables = json.loads(request.content)["variables"]
        assert variables["fromDate"] == "2026-01-01T00:00:00Z" and variables["limit"] == 1
        if variables["skip"] > 1:
            return {"data": {"transcripts": []}}
        n = variables["skip"] + 1
        return {
            "data": {
                "transcripts": [
                    {
                        "id": f"t{n}",
                        "date": 1767312000000 + n,
                        "sentences": [{"speaker_name": "Ann", "text": "Hi"}],
                    }
                ]
            }
        }

    api = FakeApi({"POST /graphql": graphql})
    cfg = {"api_key": "k", "page_size": 1}
    src = FirefliesSource(
        FirefliesSource.validate_config(cfg), client=api.client("https://api.fireflies.ai")
    )
    records, states = await read_all(
        src, incremental=True, state={"transcripts": {"cursor": "2026-01-01T00:00:00Z"}}
    )
    assert [(t["id"], t["text"]) for t in records["transcripts"]] == [
        ("t1", "Ann: Hi"),
        ("t2", "Ann: Hi"),
    ]
    assert states["transcripts"]["cursor"].startswith("2026-01-02T00:00:00.002")


async def test_highspot_items_per_spot() -> None:
    api = FakeApi(
        {
            "/v1.0/spots": {
                "collection": [{"id": "s1", "title": "Sales"}, {"id": "s2", "title": "Legal"}]
            },
            "/v1.0/items": lambda r: {
                "collection": [
                    {"id": "i-" + r.url.params["spot"], "date_updated": "2026-01-01T00:00:00Z"}
                ]
            },
        }
    )
    cfg = {"key": "k", "secret": "s", "spot_names": ["Sales"]}
    src = HighspotSource(
        HighspotSource.validate_config(cfg), client=api.client("https://api.highspot.com/v1.0")
    )
    records, _ = await read_all(src)
    assert records["items"] == [
        {"id": "i-s1", "date_updated": "2026-01-01T00:00:00Z", "spot_id": "s1"}
    ]
    assert api.calls("/v1.0/items")[0].url.params["start"] == "0"


# ---------------------------------------------------------------------------
# code repositories
# ---------------------------------------------------------------------------


async def test_github_org_repos_issues_without_prs_and_since() -> None:
    api = FakeApi(
        {
            "/orgs/acme/repos": [
                {"id": 1, "full_name": "acme/api"},
                {"id": 2, "full_name": "acme/old", "archived": True},
            ],
            "/repos/acme/api/issues": [
                {"id": 10, "title": "Bug", "updated_at": "2026-01-05T00:00:00Z"},
                {"id": 11, "title": "PR", "pull_request": {}, "updated_at": "2026-01-05T00:00:00Z"},
            ],
            "/repos/acme/api/pulls": [
                {"id": 11, "title": "PR", "updated_at": "2026-01-06T00:00:00Z"},
                {"id": 12, "title": "Old PR", "updated_at": "2025-12-01T00:00:00Z"},
            ],
        }
    )
    cfg = {"token": "ghp", "organization": "acme"}
    src = GitHubSource(
        GitHubSource.validate_config(cfg), client=api.client("https://api.github.com")
    )
    prior = {
        "issues": {
            "cursor": "2026-01-01T00:00:00Z",
            "by_parent": {"acme/api": "2026-01-01T00:00:00Z"},
        },
        "pull_requests": {
            "cursor": "2026-01-01T00:00:00Z",
            "by_parent": {"acme/api": "2026-01-01T00:00:00Z"},
        },
    }
    records, states = await read_all(src, incremental=True, state=prior)
    assert [r["full_name"] for r in records["repositories"]] == ["acme/api"]
    assert [i["id"] for i in records["issues"]] == [10]
    assert [p["id"] for p in records["pull_requests"]] == [11]  # old PR filtered client-side
    # Pull requests cannot be filtered server-side: newest first + stop at the first page
    # already seen, instead of walking the whole PR history each run.
    pulls = api.calls("/repos/acme/api/pulls")[0]
    assert (pulls.url.params["sort"], pulls.url.params["direction"]) == ("updated", "desc")
    assert next(s for s in src.streams() if s.name == "pull_requests").stop_when_page_seen
    call = api.calls("/repos/acme/api/issues")[0]
    assert call.url.params["since"] == "2026-01-01T00:00:00Z" and call.url.params["state"] == "all"
    assert call.headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert states["issues"]["by_parent"] == {"acme/api": "2026-01-05T00:00:00+00:00"}
    with pytest.raises(ConfigValidationError):
        GitHubSource.validate_config({"token": "t"})


async def test_github_explicit_repository_list() -> None:
    api = FakeApi(
        {
            "/repos/acme/api": {"id": 1, "full_name": "acme/api"},
            "/repos/acme/api/issues": [],
            "/repos/acme/api/pulls": [],
        }
    )
    cfg = {"token": "t", "repositories": ["acme/api"]}
    src = GitHubSource(
        GitHubSource.validate_config(cfg), client=api.client("https://api.github.com")
    )
    records, _ = await read_all(src)
    assert [r["full_name"] for r in records["repositories"]] == ["acme/api"]


async def test_bitbucket_next_url_states_and_missing_issue_tracker() -> None:
    def prs(request: httpx.Request) -> dict[str, Any]:
        assert request.url.params.get_list("state") == ["OPEN", "MERGED", "DECLINED", "SUPERSEDED"]
        assert request.url.params["q"] == 'updated_on > "2026-01-01T00:00:00+00:00"'
        return {"values": [{"id": 1, "title": "Fix", "updated_on": "2026-01-02T00:00:00Z"}]}

    api = FakeApi(
        {
            "/2.0/repositories/ws": lambda r: (
                {
                    "values": [{"uuid": "{1}", "slug": "api", "full_name": "ws/api"}],
                    "next": "https://api.bitbucket.org/2.0/repositories/ws?page=2",
                }
                if "page" not in r.url.params
                else {"values": [{"uuid": "{2}", "slug": "web", "full_name": "ws/web"}]}
            ),
            "/2.0/repositories/ws/api/pullrequests": prs,
            "/2.0/repositories/ws/api/issues": httpx.Response(404, json={}),
        }
    )
    cfg = {"workspace": "ws", "username": "u", "app_password": "p", "repository_slugs": ["api"]}
    src = BitbucketSource(
        BitbucketSource.validate_config(cfg), client=api.client("https://api.bitbucket.org/2.0")
    )
    prior = {
        "pull_requests": {
            "cursor": "2026-01-01T00:00:00Z",
            "by_parent": {"ws/api": "2026-01-01T00:00:00Z"},
        }
    }
    records, _ = await read_all(src, incremental=True, state=prior)
    assert [r["slug"] for r in records["repositories"]] == ["api"]
    assert records["pull_requests"][0]["repository"] == "ws/api" and "issues" not in records


async def test_github_without_token_is_anonymous() -> None:
    api = FakeApi(
        {
            "/repos/acme/api": {"id": 1, "full_name": "acme/api"},
            "/repos/acme/api/issues": [],
            "/repos/acme/api/pulls": [],
        }
    )
    src = GitHubSource(
        GitHubSource.validate_config({"repositories": ["acme/api"]}),
        client=api.client("https://api.github.com"),
    )
    assert (await src.check()).ok
    records, _ = await read_all(src)
    assert [r["full_name"] for r in records["repositories"]] == ["acme/api"]
    assert all("authorization" not in r.headers for r in api.requests)
    assert api.requests[0].headers["Accept"] == "application/vnd.github+json"
    with_token = GitHubSource(
        GitHubSource.validate_config({"token": "t", "repositories": ["acme/api"]})
    )
    assert with_token.auth_headers()["Authorization"] == "Bearer t"


async def test_bitbucket_without_credentials_is_anonymous() -> None:
    api = FakeApi(
        {
            "/2.0/repositories/ws": {
                "values": [{"uuid": "{1}", "slug": "api", "full_name": "ws/api"}]
            },
            "/2.0/repositories/ws/api/pullrequests": {"values": []},
            "/2.0/repositories/ws/api/issues": {"values": []},
        }
    )
    src = BitbucketSource(
        BitbucketSource.validate_config({"workspace": "ws"}),
        client=api.client("https://api.bitbucket.org/2.0"),
    )
    records, _ = await read_all(src)
    assert [r["slug"] for r in records["repositories"]] == ["api"]
    assert all("authorization" not in r.headers for r in api.requests)
    with pytest.raises(ConfigValidationError):  # half a basic credential is a mistake
        BitbucketSource.validate_config({"workspace": "ws", "username": "u"})


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


async def test_file_upload_formats_binary_metadata_and_mtime_cursor(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    files = {"rows.csv": b"id,name\n1,a\n", "sub/notes.md": b"# Notes", "scan.pdf": b"%PDF-1.7"}
    for i, (name, data) in enumerate(files.items()):
        path = tmp_path / name
        path.write_bytes(data)
        os.utime(path, (1767225600 + i * 100, 1767225600 + i * 100))
    src = FileUploadSource.from_config({"directory": str(tmp_path)})
    assert (await src.check()).ok
    records, states = await read_all(src, incremental=True)
    by_file = {r["_source_file"]: r for r in records["files"]}
    assert by_file["rows.csv"]["name"] == "a" and by_file["sub/notes.md"]["content"] == "# Notes"
    pdf = by_file["scan.pdf"]
    assert pdf["binary"] is True and pdf["mime_type"] == "application/pdf" and pdf["size"] == 8
    assert Path(pdf["absolute_path"]).is_file()

    again, _ = await read_all(src, incremental=True, state=states)
    assert again == {}
    (tmp_path / "new.txt").write_text("fresh", encoding="utf-8")
    os.utime(tmp_path / "new.txt", (1767229999, 1767229999))
    newer, _ = await read_all(src, incremental=True, state=states)
    assert [r["content"] for r in newer["files"]] == ["fresh"]
    assert not (
        await FileUploadSource.from_config({"directory": str(tmp_path / "nope")}).check()
    ).ok


async def test_braintrust_starting_after_paging_and_dataset_rows() -> None:
    def projects(request: httpx.Request) -> dict[str, Any]:
        after = request.url.params.get("starting_after")
        ids = [f"p{i:03d}" for i in range(1, 121)]
        start = ids.index(after) + 1 if after else 0
        return {
            "objects": [
                {"id": i, "created": "2026-01-01T00:00:00Z"} for i in ids[start : start + 100]
            ]
        }

    api = FakeApi(
        {
            "/v1/project": projects,
            "/v1/experiment": {"objects": []},
            "/v1/prompt": {"objects": []},
            "/v1/dataset": {"objects": [{"id": "d1", "created": "2026-01-01T00:00:00Z"}]},
            "/v1/dataset/d1/fetch": {
                "events": [{"id": "e1", "input": "q", "expected": "a"}],
                "cursor": None,
            },
        }
    )
    cfg = {"api_key": "sk", "project_name": "rag"}
    src = BraintrustSource(
        BraintrustSource.validate_config(cfg), client=api.client("https://api.braintrust.dev")
    )
    records, _ = await read_all(src)
    assert len(records["projects"]) == 120
    assert [c.url.params.get("starting_after") for c in api.calls("/v1/project")] == [None, "p100"]
    assert records["dataset_rows"] == [
        {"id": "e1", "input": "q", "expected": "a", "dataset_id": "d1"}
    ]
    assert api.calls("/v1/project")[0].url.params["project_name"] == "rag"


async def test_imap_schema_declares_every_record_field() -> None:
    # Live GreenMail: records carried "cc" but discover() did not declare it.
    fake = _FakeImap({1: _mail("one", "first")})
    cfg = {"host": "mail.test", "username": "u", "password": "p"}
    src = ImapSource(ImapSource.validate_config(cfg), client_factory=lambda c: fake)
    declared = set((await src.discover()).get("messages").json_schema["properties"])
    records, _ = await read_all(src, incremental=False)
    undeclared = set(records["messages"][0]) - declared
    assert not undeclared, undeclared


def test_imap_fetch_reads_the_uid_that_follows_the_literal() -> None:
    # imaplib hands a FETCH item over as (b"1 (UID 5 RFC822 {n}", <bytes>), b")"; a server
    # that lists RFC822 first leaves "UID 5" in the trailing part and the message was dropped.
    class Client:
        def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
            return "OK", [
                (b"1 (RFC822 {10}", b"raw-one---"),
                b" UID 5)",
                (b"2 (UID 6 RFC822 {10}", b"raw-two---"),
                b")",
            ]

    assert ImapSource._fetch(Client(), [5, 6]) == [(5, b"raw-one---"), (6, b"raw-two---")]
