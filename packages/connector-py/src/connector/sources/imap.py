"""Generic e-mail source over IMAP (standard library only).

Stream ``messages``: every message of the configured folders, parsed into
headers, a plain-text body and attachment names. Incremental sync remembers the
highest UID per folder (together with ``UIDVALIDITY``; if the server resets it,
the folder is read again from the start).

``imaplib`` is blocking, so all protocol work runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import email
import imaplib
import re
import ssl
from collections.abc import AsyncIterator, Callable
from email import policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Any

from pydantic import BaseModel, Field

from ..base import BaseSource, secret_field
from ..common.text import html_to_text
from ..errors import SourceError
from ..models import (
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    Record,
    State,
    Stream,
    SyncMode,
    SyncState,
)

ClientFactory = Callable[["ImapConfig"], Any]
_UIDVALIDITY = re.compile(rb"UIDVALIDITY (\d+)")
_UID = re.compile(rb"UID (\d+)")


class ImapConfig(BaseModel):
    host: str
    port: int = 993
    username: str
    password: str = secret_field(description="Password or app password.")
    use_ssl: bool = True
    verify_ssl: bool = Field(
        default=True,
        description="Verify the server certificate (off only for a self-signed test server).",
    )
    folders: list[str] = Field(default_factory=lambda: ["INBOX"])
    since: str | None = Field(
        default=None, description="Only mail on/after this date (DD-Mon-YYYY)."
    )
    fetch_batch_size: int = Field(default=50, ge=1, le=500)
    max_body_chars: int = Field(default=200_000, ge=0)
    timeout_seconds: float = 60.0


def _default_client(config: ImapConfig) -> Any:
    if config.use_ssl:
        # imaplib's own default context does not verify the server: build one that does.
        context = ssl.create_default_context()
        if not config.verify_ssl:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        client: Any = imaplib.IMAP4_SSL(
            config.host, config.port, ssl_context=context, timeout=config.timeout_seconds
        )
    else:
        client = imaplib.IMAP4(config.host, config.port, timeout=config.timeout_seconds)
    client.login(config.username, config.password)
    return client


class ImapSource(BaseSource[ImapConfig]):
    definition = ConnectorDefinition(
        name="imap",
        display_name="Email (IMAP)",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.MESSAGING,
        documentation_url="https://datatracker.ietf.org/doc/html/rfc3501",
        icon="imap.svg",
        tags=frozenset({"email", "self-hosted"}),
    )
    Config = ImapConfig

    def __init__(self, config: ImapConfig, client_factory: ClientFactory | None = None) -> None:
        super().__init__(config)
        self._factory = client_factory or _default_client

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    async def check(self) -> CheckResult:
        def _sync() -> None:
            client = self._factory(self.config)
            try:
                status, _ = client.select(_quote(self.config.folders[0]), readonly=True)
                if status != "OK":
                    raise SourceError(f"cannot select folder {self.config.folders[0]}")
            finally:
                _logout(client)

        try:
            await asyncio.to_thread(_sync)
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=self.redacted(str(exc)))
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        return Catalog(
            streams=[
                Stream(
                    name="messages",
                    json_schema={
                        "type": "object",
                        "properties": {
                            "folder": {"type": "string"},
                            "uid": {"type": "integer"},
                            "message_id": {"type": "string"},
                            "subject": {"type": "string"},
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "cc": {"type": "string"},
                            "date": {"type": "string", "format": "date-time"},
                            "body": {"type": "string"},
                            "parse_error": {"type": ["string", "null"]},
                            "attachments": {"type": "array"},
                        },
                    },
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["uid"],
                    source_defined_primary_key=[["folder"], ["uid"]],
                )
            ]
        )

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        configured = next((s for s in catalog.streams if s.stream.name == "messages"), None)
        if configured is None:
            return
        incremental = configured.sync_mode is SyncMode.INCREMENTAL
        folders_state: dict[str, dict[str, int]] = dict(
            ((state or SyncState()).get("messages").get("folders") or {}) if incremental else {}
        )
        client = await asyncio.to_thread(self._factory, self.config)
        try:
            for folder in self.config.folders:
                prior = folders_state.get(folder) or {}
                validity, uids = await asyncio.to_thread(self._list_uids, client, folder, prior)
                last_uid = prior.get("last_uid", 0) if prior.get("uidvalidity") == validity else 0
                size = self.config.fetch_batch_size
                for i in range(0, len(uids), size):
                    chunk = uids[i : i + size]
                    for uid, raw in await asyncio.to_thread(self._fetch, client, chunk):
                        last_uid = max(last_uid, uid)
                        yield Record(stream="messages", data=self._parse(folder, uid, raw))
                    if incremental:
                        folders_state[folder] = {"uidvalidity": validity, "last_uid": last_uid}
                        yield State(stream="messages", data={"folders": dict(folders_state)})
        finally:
            await asyncio.to_thread(_logout, client)

    # ---- blocking helpers (run in a thread) ------------------------------------------

    def _list_uids(self, client: Any, folder: str, prior: dict[str, int]) -> tuple[int, list[int]]:
        status, data = client.select(_quote(folder), readonly=True)
        if status != "OK":
            raise SourceError(f"cannot select folder {folder}: {data!r}")
        _, resp = client.response("UIDVALIDITY")
        match = _UIDVALIDITY.search(b" ".join(x for x in (resp or []) if x) or b"")
        validity = int(match.group(1)) if match else int((resp or [b"0"])[0] or 0)
        start = prior.get("last_uid", 0) + 1 if prior.get("uidvalidity") == validity else 1
        criteria = [f"UID {start}:*"]
        if self.config.since:
            criteria.append(f"SINCE {self.config.since}")
        status, data = client.uid("SEARCH", None, *criteria)
        if status != "OK":
            raise SourceError(f"search failed in {folder}: {data!r}")
        uids = sorted(int(u) for u in (data[0] or b"").split())
        return validity, [u for u in uids if u >= start]  # "n:*" always returns the last UID

    @staticmethod
    def _fetch(client: Any, uids: list[int]) -> list[tuple[int, bytes]]:
        status, data = client.uid("FETCH", ",".join(map(str, uids)), "(UID RFC822)")
        if status != "OK":
            raise SourceError(f"fetch failed: {data!r}")
        out: list[tuple[int, bytes]] = []
        items = list(data or [])
        for index, item in enumerate(items):
            if not (isinstance(item, tuple) and len(item) == 2):
                continue
            match = _UID.search(item[0])
            if match is None and index + 1 < len(items) and isinstance(items[index + 1], bytes):
                # A server that lists RFC822 first leaves "UID n" after the literal:
                # (b"1 (RFC822 {n}", <raw>), b" UID 5)".
                match = _UID.search(items[index + 1])
            if match:
                out.append((int(match.group(1)), item[1]))
        return out

    def _parse(self, folder: str, uid: int, raw: bytes) -> dict[str, Any]:
        msg: EmailMessage = email.message_from_bytes(raw, policy=policy.default)
        body, parse_error = "", None
        try:
            body_part = msg.get_body(preferencelist=("plain", "html"))
            if body_part is not None:
                content = body_part.get_content()
                if body_part.get_content_subtype() == "html":
                    content = html_to_text(content)
                body = content
        except (LookupError, UnicodeDecodeError, ValueError, KeyError) as exc:
            # An unknown charset or transfer encoding must not fail the run for one message:
            # the headers are still indexed and the UID advances past it.
            parse_error = f"{type(exc).__name__}: {exc}"
        date = None
        if msg["date"]:
            try:
                date = parsedate_to_datetime(str(msg["date"])).isoformat()
            except (TypeError, ValueError):
                date = None
        return {
            "folder": folder,
            "uid": uid,
            "message_id": str(msg["message-id"] or "").strip() or None,
            "subject": str(msg["subject"] or ""),
            "from": str(msg["from"] or ""),
            "to": str(msg["to"] or ""),
            "cc": str(msg["cc"] or ""),
            "date": date,
            "body": body[: self.config.max_body_chars] if self.config.max_body_chars else body,
            "parse_error": parse_error,
            "attachments": [
                {"filename": p.get_filename(), "content_type": p.get_content_type()}
                for p in msg.iter_attachments()
            ],
        }


def _quote(folder: str) -> str:
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _logout(client: Any) -> None:
    with contextlib.suppress(Exception):  # best effort cleanup
        client.logout()
