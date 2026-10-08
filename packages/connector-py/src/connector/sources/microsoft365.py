"""Microsoft 365 source via Microsoft Graph: directory, OneDrive files and OneNote pages.

Streams:

* ``users``          - member users of the tenant (guests and disabled accounts optional)
* ``groups``         - Microsoft 365 and security groups
* ``onedrive_files`` - files in the selected users' OneDrives through the Graph
                       *delta* API; every user's ``deltaLink`` is the stored state
* ``onenote_pages``  - OneNote pages with their content flattened to text;
                       a ``lastModifiedDateTime`` cursor is kept per user

Mail and calendars, SharePoint sites and Teams channels have their own
connectors (``outlook``, ``sharepoint``, ``microsoft_teams``). Requires
application permissions ``User.Read.All``, ``Group.Read.All``,
``Files.Read.All`` and ``Notes.Read.All`` with admin consent. File content is
not downloaded; records carry ``download_url`` for the ingestion layer.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import Field

from ..common.cursor import later
from ..common.declarative import as_iso_z
from ..common.microsoft_graph import (
    GraphConfigBase,
    GraphSource,
    drive_item_record,
    keep_drive_item,
)
from ..common.text import html_to_text
from ..models import (
    Catalog,
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

logger = logging.getLogger("connector.microsoft365")

USER_SELECT = (
    "id,displayName,userPrincipalName,mail,jobTitle,department,officeLocation,"
    "accountEnabled,userType,createdDateTime"
)
GROUP_SELECT = (
    "id,displayName,description,mail,mailEnabled,securityEnabled,groupTypes,"
    "visibility,createdDateTime"
)
PAGE_SELECT = "id,title,createdDateTime,lastModifiedDateTime,links,contentUrl"
PAGE_EXPAND = "parentSection($select=displayName),parentNotebook($select=displayName)"
ONENOTE_PAGE_SIZE = 100  # the OneNote API caps $top at 100


class Microsoft365Config(GraphConfigBase):
    user_principal_names: list[str] | None = Field(
        default=None,
        description="Users whose OneDrive and OneNote are read. Default: every enabled member.",
    )
    include_guests: bool = False
    include_disabled_users: bool = False
    max_users: int = Field(default=1000, ge=1)
    file_extensions: list[str] | None = Field(
        default=None, description="Only emit files with these extensions, e.g. ['pdf', 'docx']."
    )
    include_folders: bool = False
    include_onenote_content: bool = Field(
        default=True, description="Fetch every page's HTML and flatten it to text."
    )


class Microsoft365Source(GraphSource[Microsoft365Config]):
    definition = ConnectorDefinition(
        name="microsoft365",
        display_name="Microsoft 365",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.SAAS,
        documentation_url="https://learn.microsoft.com/graph/overview",
        icon="microsoft365.svg",
        tags=frozenset({"saas", "microsoft", "directory", "documents"}),
    )
    Config = Microsoft365Config

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    async def discover(self) -> Catalog:
        def stream(name: str, props: dict[str, Any], incremental: bool) -> Stream:
            return Stream(
                name=name,
                json_schema={"type": "object", "properties": props},
                supported_sync_modes=[SyncMode.FULL_REFRESH]
                + ([SyncMode.INCREMENTAL] if incremental else []),
                source_defined_cursor=incremental,
                default_cursor_field=["last_modified"] if incremental else [],
                source_defined_primary_key=[["id"]],
            )

        return Catalog(
            streams=[
                stream(
                    "users",
                    {
                        "id": {"type": "string"},
                        "display_name": {"type": "string"},
                        "user_principal_name": {"type": "string"},
                        "mail": {"type": "string"},
                        "job_title": {"type": "string"},
                        "department": {"type": "string"},
                        "account_enabled": {"type": "boolean"},
                        "user_type": {"type": "string"},
                    },
                    False,
                ),
                stream(
                    "groups",
                    {
                        "id": {"type": "string"},
                        "display_name": {"type": "string"},
                        "description": {"type": "string"},
                        "mail": {"type": "string"},
                        "group_types": {"type": "array"},
                    },
                    False,
                ),
                stream(
                    "onedrive_files",
                    {
                        "id": {"type": "string"},
                        "owner": {"type": "string"},
                        "name": {"type": "string"},
                        "path": {"type": "string"},
                        "size": {"type": "integer"},
                        "mime_type": {"type": "string"},
                        "web_url": {"type": "string"},
                        "download_url": {"type": "string"},
                        "deleted": {"type": "boolean"},
                        "last_modified": {"type": "string", "format": "date-time"},
                    },
                    True,
                ),
                stream(
                    "onenote_pages",
                    {
                        "id": {"type": "string"},
                        "owner": {"type": "string"},
                        "title": {"type": "string"},
                        "notebook": {"type": "string"},
                        "section": {"type": "string"},
                        "content": {"type": "string"},
                        "web_url": {"type": "string"},
                        "last_modified": {"type": "string", "format": "date-time"},
                    },
                    True,
                ),
            ]
        )

    # ---- read ------------------------------------------------------------------------

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        modes = {s.stream.name: s.sync_mode for s in catalog.streams}
        if "groups" in modes:
            params = {"$select": GROUP_SELECT, "$top": self.config.page_size}
            async for raw in self.paginate("/groups", params=params):
                yield Record(stream="groups", data=_group(raw))
        if not modes.keys() & {"users", "onedrive_files", "onenote_pages"}:
            return
        users = await self._users()
        if "users" in modes:
            for raw in users:
                yield Record(stream="users", data=_user(raw))
        if "onedrive_files" in modes:
            incremental = modes["onedrive_files"] is SyncMode.INCREMENTAL
            async for item in self._onedrive(users, state, incremental):
                yield item
        if "onenote_pages" in modes:
            incremental = modes["onenote_pages"] is SyncMode.INCREMENTAL
            async for item in self._onenote(users, state, incremental):
                yield item

    async def _users(self) -> list[dict[str, Any]]:
        c = self.config
        if c.user_principal_names:
            users: list[dict[str, Any]] = []
            for upn in c.user_principal_names:
                try:
                    users.append(
                        await self.get_json(f"/users/{upn}", params={"$select": USER_SELECT})
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise
                    logger.warning("microsoft365: user %s not found", upn)
            return users
        params: dict[str, Any] = {"$select": USER_SELECT, "$top": c.page_size}
        if not c.include_disabled_users:
            params["$filter"] = "accountEnabled eq true"  # a plain filter: no advanced query
        selected: list[dict[str, Any]] = []
        async for u in self.paginate("/users", params=params):
            # ``userType`` needs an advanced query (ConsistencyLevel: eventual) to filter on;
            # kept client-side.
            if not c.include_guests and (u.get("userType") or "Member") != "Member":
                continue
            if not (c.include_disabled_users or u.get("accountEnabled", True)):
                continue
            selected.append(u)
            if len(selected) >= c.max_users:
                break  # stop paging a large directory once the cap is reached
        return selected

    async def _onedrive(
        self, users: list[dict[str, Any]], state: SyncState, incremental: bool
    ) -> AsyncIterator[Record | State]:
        links: dict[str, str] = (
            dict(state.get("onedrive_files").get("delta_links") or {}) if incremental else {}
        )
        new_links: dict[str, str] = {}
        for user in users:
            uid = user["id"]
            changes = self.delta(f"/users/{uid}/drive/root/delta", resume_from=links.get(uid))
            try:
                async for raw in changes:
                    record = self._drive_item(raw, user)
                    if record is not None:
                        yield Record(stream="onedrive_files", data=record)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (403, 404):
                    logger.info("microsoft365: no OneDrive for %s", user.get("userPrincipalName"))
                    continue
                raise
            if changes.delta_link:
                new_links[uid] = changes.delta_link
        if incremental and new_links:
            yield State(stream="onedrive_files", data={"delta_links": {**links, **new_links}})

    def _drive_item(self, raw: dict[str, Any], user: dict[str, Any]) -> dict[str, Any] | None:
        if not keep_drive_item(
            raw,
            include_folders=self.config.include_folders,
            file_extensions=self.config.file_extensions,
        ):
            return None
        return {**drive_item_record(raw), "owner": user.get("userPrincipalName")}

    async def _onenote(
        self, users: list[dict[str, Any]], state: SyncState, incremental: bool
    ) -> AsyncIterator[Record | State]:
        by_user: dict[str, str] = (
            dict(state.get("onenote_pages").get("by_user") or {}) if incremental else {}
        )
        new_by_user: dict[str, str] = {}
        for user in users:
            uid = user["id"]
            last = by_user.get(uid)
            max_seen = last
            params: dict[str, Any] = {
                "$select": PAGE_SELECT,
                "$expand": PAGE_EXPAND,
                "$top": min(self.config.page_size, ONENOTE_PAGE_SIZE),
                "$orderby": "lastModifiedDateTime asc",
            }
            if last:
                params["$filter"] = f"lastModifiedDateTime gt {as_iso_z(last)}"
            try:
                async for raw in self.paginate(f"/users/{uid}/onenote/pages", params=params):
                    content = await self._page_content(uid, raw["id"])
                    modified = raw.get("lastModifiedDateTime")
                    max_seen = later(max_seen, modified)
                    yield Record(
                        stream="onenote_pages",
                        data={
                            "id": raw.get("id"),
                            "owner": user.get("userPrincipalName"),
                            "title": raw.get("title"),
                            "notebook": (raw.get("parentNotebook") or {}).get("displayName"),
                            "section": (raw.get("parentSection") or {}).get("displayName"),
                            "content": content,
                            "web_url": ((raw.get("links") or {}).get("oneNoteWebUrl") or {}).get(
                                "href"
                            ),
                            "created": raw.get("createdDateTime"),
                            "last_modified": modified,
                        },
                    )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (403, 404):
                    logger.info("microsoft365: no OneNote for %s", user.get("userPrincipalName"))
                    continue
                raise
            if max_seen and max_seen != last:
                new_by_user[uid] = max_seen
        if incremental and new_by_user:
            yield State(stream="onenote_pages", data={"by_user": {**by_user, **new_by_user}})

    async def _page_content(self, uid: str, page_id: str) -> str | None:
        if not self.config.include_onenote_content:
            return None
        try:
            resp = await self.request(
                "GET",
                f"/users/{uid}/onenote/pages/{page_id}/content",
                headers={"Accept": "text/html"},
            )
        except httpx.HTTPStatusError as exc:
            # No access or gone is the page's own state. Anything else must not leave the
            # page indexed without its body while the cursor moves past it.
            if exc.response.status_code in (403, 404):
                return None
            raise
        return html_to_text(resp.text)


def _user(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "display_name": raw.get("displayName"),
        "user_principal_name": raw.get("userPrincipalName"),
        "mail": raw.get("mail"),
        "job_title": raw.get("jobTitle"),
        "department": raw.get("department"),
        "office_location": raw.get("officeLocation"),
        "account_enabled": raw.get("accountEnabled"),
        "user_type": raw.get("userType"),
        "created": raw.get("createdDateTime"),
    }


def _group(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "display_name": raw.get("displayName"),
        "description": raw.get("description"),
        "mail": raw.get("mail"),
        "mail_enabled": raw.get("mailEnabled"),
        "security_enabled": raw.get("securityEnabled"),
        "group_types": raw.get("groupTypes") or [],
        "visibility": raw.get("visibility"),
        "created": raw.get("createdDateTime"),
    }
