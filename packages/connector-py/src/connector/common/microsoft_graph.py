"""Microsoft Graph plumbing shared by the Outlook, SharePoint, Teams and Microsoft 365 sources.

Authentication is the OAuth2 *client credentials* flow (an Entra ID app
registration with application permissions), which is what a background sync
needs: no user is present. The token is cached and refreshed shortly before
expiry. Paging follows ``@odata.nextLink``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Collection
from typing import Any, ClassVar, TypeVar

import httpx
from pydantic import BaseModel, Field

from ..base import secret_field
from .oauth2 import OAuth2BearerMixin, OAuth2Token
from .rest_source import RestSource

logger = logging.getLogger("connector.graph")

ConfigT = TypeVar("ConfigT", bound="GraphConfigBase")

GRAPH_URL = "https://graph.microsoft.com/v1.0"
LOGIN_URL = "https://login.microsoftonline.com"


class GraphConfigBase(BaseModel):
    tenant_id: str = Field(description="Entra ID tenant (directory) id.")
    client_id: str = Field(description="App registration (client) id.")
    client_secret: str = secret_field(description="App registration client secret.")
    graph_url: str = Field(default=GRAPH_URL, description="Override for national clouds.")
    login_url: str = Field(default=LOGIN_URL)
    page_size: int = Field(default=100, ge=1, le=999)
    timeout_seconds: float = 30.0


class DeltaQuery:
    """An OData delta query, read page by page.

    Iterate it for the changed items. Once the last page has been read,
    ``delta_link`` holds the URL the next sync continues from; until then it is
    ``None``, so a query that was abandoned half way leaves nothing to save.

    ``resume_from`` is the delta link a previous sync stored. Graph keeps the
    state behind such a link for a limited time and answers ``410 Gone`` once it
    has dropped it; the query then starts over from ``path`` and lists everything
    again, instead of failing every run until someone resets the stored state.
    """

    def __init__(
        self,
        source: GraphSource[Any],
        path: str,
        params: dict[str, Any] | None = None,
        *,
        resume_from: str | None = None,
    ) -> None:
        self._source = source
        self._path = path
        self._params = params
        self._resume_from = resume_from
        self.delta_link: str | None = None

    async def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        page = await self._first_page()
        while True:
            for item in (page or {}).get("value", []) or []:
                yield item
            url = (page or {}).get("@odata.nextLink")
            if not url:
                self.delta_link = (page or {}).get("@odata.deltaLink")
                return
            page = await self._source.get_json(url)

    async def _first_page(self) -> Any:
        if self._resume_from:
            try:
                return await self._source.get_json(self._resume_from)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != httpx.codes.GONE:
                    raise
                logger.warning("delta link of %s has expired; starting over", self._path)
        return await self._source.get_json(self._path, params=self._params)


class GraphSource(OAuth2BearerMixin, RestSource[ConfigT]):
    """Base for Graph-backed sources: token handling + ``@odata.nextLink`` paging."""

    check_path: ClassVar[str] = "/organization"

    def base_url(self) -> str:
        return self.config.graph_url

    def oauth2_token(self) -> OAuth2Token:
        c = self.config
        return OAuth2Token(
            f"{c.login_url.rstrip('/')}/{c.tenant_id}/oauth2/v2.0/token",
            {
                "grant_type": "client_credentials",
                "client_id": c.client_id,
                "client_secret": c.client_secret,
                "scope": f"{c.graph_url.rstrip('/').rsplit('/', 1)[0]}/.default",
            },
        )

    async def paginate(
        self, path: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield every item across ``@odata.nextLink`` pages."""
        url: str | None = path
        first = True
        while url:
            page = await self.get_json(url, params=params if first else None, headers=headers)
            first = False
            for item in page.get("value", []) or []:
                yield item
            url = page.get("@odata.nextLink")

    def delta(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        resume_from: str | None = None,
    ) -> DeltaQuery:
        """A delta query of ``path``, continued from a stored delta link when one is given."""
        return DeltaQuery(self, path, params, resume_from=resume_from)


def graph_error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            return exc.response.json().get("error", {}).get("message") or str(exc)
        except ValueError:
            return str(exc)
    return str(exc)


# ---- drive items (SharePoint document libraries, OneDrive) -----------------------------


def identity_name(value: Any) -> str | None:
    """Display name (or e-mail) of an ``identitySet``."""
    if not isinstance(value, dict):
        return None
    user = value.get("user") or {}
    return user.get("displayName") or user.get("email")


def keep_drive_item(
    raw: dict[str, Any], *, include_folders: bool, file_extensions: Collection[str] | None
) -> bool:
    """Is this delta entry a file (or folder) the source was asked for?"""
    if raw.get("root") is not None:
        return False  # the drive's root folder itself
    if "folder" in raw:
        return include_folders
    if file_extensions:
        extension = (raw.get("name") or "").rsplit(".", 1)[-1].lower()
        return extension in {e.lower().lstrip(".") for e in file_extensions}
    return True


def drive_item_record(raw: dict[str, Any]) -> dict[str, Any]:
    """The fields every drive item record carries, whatever drive it came from."""
    parent = raw.get("parentReference") or {}
    folder_path = parent.get("path") or ""
    name = raw.get("name")
    return {
        "id": raw.get("id"),
        "drive_id": parent.get("driveId"),
        "name": name,
        "path": f"{folder_path}/{name}" if folder_path else name,
        "is_folder": "folder" in raw,
        "size": raw.get("size"),
        "mime_type": (raw.get("file") or {}).get("mimeType"),
        "web_url": raw.get("webUrl"),
        "download_url": raw.get("@microsoft.graph.downloadUrl"),
        "deleted": "deleted" in raw,
        "created_by": identity_name(raw.get("createdBy")),
        "last_modified_by": identity_name(raw.get("lastModifiedBy")),
        "last_modified": raw.get("lastModifiedDateTime"),
    }
