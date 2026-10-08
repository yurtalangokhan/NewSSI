"""Dropbox source.

Stream ``files``: recursive listing below ``path`` through
``files/list_folder`` + ``list_folder/continue``. Dropbox access tokens live for
four hours, so production configs should supply ``refresh_token`` together with
the app key and secret; a bare ``access_token`` is accepted for short jobs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, PageRequest, Paginator, StreamSpec
from ..common.oauth2 import OAuth2BearerMixin, OAuth2Token
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

API = "https://api.dropboxapi.com"


@dataclass(frozen=True)
class _ListFolderPagination(Paginator):
    def next(self, req, response, payload, records):  # noqa: ANN001, ANN201
        if not payload or not payload.get("has_more") or not payload.get("cursor"):
            return None
        return PageRequest(
            method="POST",
            url=f"{API}/2/files/list_folder/continue",
            body={"cursor": payload["cursor"]},
            headers=req.headers,
        )


class DropboxConfig(BaseModel):
    access_token: str | None = secret_field(default=None, description="Short-lived access token.")
    refresh_token: str | None = secret_field(default=None)
    app_key: str | None = None
    app_secret: str | None = secret_field(default=None)
    path: str = Field(default="", description="Folder to read; empty string is the root.")
    recursive: bool = True
    timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def _credentials(self) -> DropboxConfig:
        if not self.access_token and not (self.refresh_token and self.app_key and self.app_secret):
            raise ValueError("provide access_token, or refresh_token with app_key and app_secret")
        return self


class DropboxSource(OAuth2BearerMixin, DeclarativeRestSource[DropboxConfig]):
    definition = ConnectorDefinition(
        name="dropbox",
        display_name="Dropbox",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://www.dropbox.com/developers/documentation/http/documentation",
        icon="dropbox.svg",
        tags=frozenset({"saas", "storage", "documents"}),
    )
    Config = DropboxConfig

    def base_url(self) -> str:
        return API

    def static_token(self) -> str | None:
        return self.config.access_token

    def oauth2_token(self) -> OAuth2Token:
        return OAuth2Token(
            "https://api.dropbox.com/oauth2/token",
            {"grant_type": "refresh_token", "refresh_token": self.config.refresh_token},
            basic_auth=(self.config.app_key or "", self.config.app_secret or ""),
            default_ttl=14_400,
        )

    def streams(self) -> list[StreamSpec]:
        return [
            StreamSpec(
                name="files",
                path="/2/files/list_folder",
                method="POST",
                body={
                    "path": "" if self.config.path in ("", "/") else self.config.path,
                    "recursive": self.config.recursive,
                    "include_deleted": False,
                    "limit": 2000,
                },
                records_path="entries",
                paginator=_ListFolderPagination(),
                cursor_field="server_modified",
                client_side_filter=True,
                transform=_files_only,
            )
        ]


def _files_only(rec: dict[str, Any]) -> dict[str, Any] | None:
    if rec.get(".tag") != "file":
        return None
    rec["path"] = rec.get("path_display")
    return rec
