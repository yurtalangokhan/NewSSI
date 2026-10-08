"""Box source.

Stream ``files``: walks the folder tree from ``folder_ids`` (default: root ``0``).
Auth is either a ready ``access_token`` or the Client Credentials Grant of a
server app (``client_id`` / ``client_secret`` plus the enterprise or user to act
as).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..base import secret_field
from ..common.declarative import OffsetPagination, StreamSpec
from ..common.folder_tree import FolderTreeSource
from ..common.oauth2 import OAuth2BearerMixin, OAuth2Token
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

ITEM_FIELDS = (
    "id,type,name,size,modified_at,created_at,content_modified_at,path_collection,"
    "shared_link,sha1,extension,description,owned_by,modified_by,parent"
)


class BoxConfig(BaseModel):
    access_token: str | None = secret_field(default=None, description="Developer / OAuth token.")
    client_id: str | None = None
    client_secret: str | None = secret_field(default=None)
    enterprise_id: str | None = Field(default=None, description="Act as the service account.")
    user_id: str | None = Field(default=None, description="Act as this user instead.")
    folder_ids: list[str] = Field(default_factory=lambda: ["0"], description="'0' is the root.")
    timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def _credentials(self) -> BoxConfig:
        ccg = self.client_id and self.client_secret and (self.enterprise_id or self.user_id)
        if not self.access_token and not ccg:
            raise ValueError(
                "provide access_token, or client_id + client_secret + enterprise_id/user_id"
            )
        return self


class BoxSource(OAuth2BearerMixin, FolderTreeSource[BoxConfig]):
    definition = ConnectorDefinition(
        name="box",
        display_name="Box",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://developer.box.com/reference/",
        icon="box.svg",
        tags=frozenset({"saas", "storage", "documents"}),
    )
    Config = BoxConfig

    def base_url(self) -> str:
        return "https://api.box.com"

    def static_token(self) -> str | None:
        return self.config.access_token

    def oauth2_token(self) -> OAuth2Token:
        c = self.config
        return OAuth2Token(
            "https://api.box.com/oauth2/token",
            {
                "grant_type": "client_credentials",
                "client_id": c.client_id,
                "client_secret": c.client_secret,
                "box_subject_type": "enterprise" if c.enterprise_id else "user",
                "box_subject_id": c.enterprise_id or c.user_id,
            },
        )

    def streams(self) -> list[StreamSpec]:
        return [
            StreamSpec(
                name="files",
                path="/2.0/folders/0/items",
                records_path="entries",
                params={"fields": ITEM_FIELDS},
                paginator=OffsetPagination(page_size=1000, total_path="total_count"),
                cursor_field="modified_at",
                client_side_filter=True,
                transform=_with_path,
            )
        ]

    def root_folders(self) -> list[Any]:
        return list(self.config.folder_ids)

    def folder_spec(self, spec: StreamSpec, folder: Any) -> StreamSpec:
        return replace(spec, path=f"/2.0/folders/{folder}/items")

    def subfolder(self, item: dict[str, Any]) -> Any | None:
        return item.get("id") if item.get("type") == "folder" else None


def _with_path(rec: dict[str, Any]) -> dict[str, Any] | None:
    if rec.get("type") == "web_link":
        return None
    parts = [e.get("name", "") for e in (rec.get("path_collection") or {}).get("entries") or []]
    rec["path"] = "/".join([*parts, rec.get("name", "")])
    return rec
