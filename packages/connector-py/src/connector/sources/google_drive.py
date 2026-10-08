"""Google Drive source.

Stream ``files``: metadata of every non-trashed file the credentials can see
(optionally below ``folder_ids`` or inside shared drives). With
``include_content`` Google Docs / Sheets / Slides are exported as text and
small plain-text files are downloaded; other binaries carry metadata only so
a document pipeline can fetch them via ``webContentLink``.

Incremental sync adds ``modifiedTime > '<cursor>'`` to the Drive query.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx
from pydantic import Field

from ..common.declarative import CursorPagination, PageRequest, StreamSpec, as_iso_z
from ..common.google_auth import GoogleAuthConfig, GoogleSource
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

FILE_FIELDS = (
    "id,name,mimeType,modifiedTime,createdTime,size,webViewLink,webContentLink,parents,"
    "owners(displayName,emailAddress),lastModifyingUser(displayName,emailAddress),driveId,md5Checksum"
)
EXPORT_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}
FOLDER = "application/vnd.google-apps.folder"


class GoogleDriveConfig(GoogleAuthConfig):
    folder_ids: list[str] | None = Field(default=None, description="Only direct children of these.")
    include_shared_drives: bool = True
    mime_types: list[str] | None = Field(default=None, description="Restrict to these MIME types.")
    include_content: bool = Field(default=True, description="Export Google Docs and text files.")
    max_content_bytes: int = Field(default=5_000_000, ge=0)


class GoogleDriveSource(GoogleSource[GoogleDriveConfig]):
    definition = ConnectorDefinition(
        name="google_drive",
        display_name="Google Drive",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://developers.google.com/drive/api/reference/rest/v3",
        icon="google_drive.svg",
        tags=frozenset({"google", "storage", "documents"}),
    )
    Config = GoogleDriveConfig
    scopes: ClassVar[tuple[str, ...]] = ("https://www.googleapis.com/auth/drive.readonly",)

    def base_url(self) -> str:
        return "https://www.googleapis.com"

    def _query(self) -> str:
        clauses = ["trashed = false", f"mimeType != '{FOLDER}'"]
        if self.config.folder_ids:
            clauses.append(
                "(" + " or ".join(f"'{f}' in parents" for f in self.config.folder_ids) + ")"
            )
        if self.config.mime_types:
            clauses.append(
                "(" + " or ".join(f"mimeType = '{m}'" for m in self.config.mime_types) + ")"
            )
        return " and ".join(clauses)

    def streams(self) -> list[StreamSpec]:
        shared = self.config.include_shared_drives
        base_query = self._query()

        def with_cursor(req: PageRequest, cursor: Any) -> None:
            if cursor is not None:
                req.params["q"] = f"{base_query} and modifiedTime > '{as_iso_z(cursor)}'"

        return [
            StreamSpec(
                name="files",
                path="/drive/v3/files",
                records_path="files",
                params={
                    "q": base_query,
                    "fields": f"nextPageToken,files({FILE_FIELDS})",
                    "orderBy": "modifiedTime",
                    "supportsAllDrives": "true" if shared else None,
                    "includeItemsFromAllDrives": "true" if shared else None,
                    "corpora": "allDrives" if shared else None,
                },
                paginator=CursorPagination(
                    cursor_path="nextPageToken",
                    cursor_param="pageToken",
                    size_param="pageSize",
                    page_size=1000,
                ),
                cursor_field="modifiedTime",
                on_request=with_cursor,
                enrich="_load_content" if self.config.include_content else None,
            )
        ]

    async def _load_content(self, rec: dict[str, Any], parent: Any) -> dict[str, Any]:
        mime = rec.get("mimeType", "")
        try:
            if mime in EXPORT_TYPES:
                resp = await self.request(
                    "GET",
                    f"/drive/v3/files/{rec['id']}/export",
                    params={"mimeType": EXPORT_TYPES[mime]},
                )
                rec["content"] = resp.text[: self.config.max_content_bytes]
            elif (
                mime.startswith("text/")
                and int(rec.get("size") or 0) <= self.config.max_content_bytes
            ):
                resp = await self.request(
                    "GET",
                    f"/drive/v3/files/{rec['id']}",
                    params={"alt": "media", "supportsAllDrives": "true"},
                )
                rec["content"] = resp.text
        except httpx.HTTPStatusError as exc:
            # No permission or gone: the file's own state, indexed without its body. Any
            # other failure must not advance the cursor past a body that is merely
            # unavailable right now (it would never be read): the run fails and retries.
            if exc.response.status_code not in (403, 404):
                raise
            rec["content_error"] = f"{exc.response.status_code}"
        return rec
