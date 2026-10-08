"""LumApps source: published content of an instance (``content/list``)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import CursorPagination, DeclarativeRestSource, StreamSpec
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class LumAppsConfig(BaseModel):
    base_url: str = Field(default="https://sites.lumapps.com", description="LumApps cell URL.")
    access_token: str = secret_field(description="OAuth2 bearer token of a service account.")
    instance_id: str | None = Field(default=None, description="Restrict to one site (instance).")
    lang: str = "en"
    content_types: list[str] | None = Field(default=None, description="e.g. ['news', 'page'].")
    timeout_seconds: float = 60.0


class LumAppsSource(DeclarativeRestSource[LumAppsConfig]):
    definition = ConnectorDefinition(
        name="lumapps",
        display_name="LumApps",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://apiv1.lumapps.com/",
        icon="lumapps.svg",
        tags=frozenset({"saas", "intranet"}),
    )
    Config = LumAppsConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.access_token}"}

    def streams(self) -> list[StreamSpec]:
        body = {
            "lang": self.config.lang,
            "instanceId": self.config.instance_id,
            "type": self.config.content_types,
            "sortOrder": ["updatedAt"],
        }
        return [
            StreamSpec(
                name="contents",
                path="/_ah/api/lumapps/v1/content/list",
                method="POST",
                body={k: v for k, v in body.items() if v is not None},
                records_path="items",
                paginator=CursorPagination(
                    cursor_path="cursor",
                    cursor_param="cursor",
                    in_body=True,
                    size_param="maxResults",
                    page_size=100,
                    has_more_path="more",
                ),
                cursor_field="updatedAt",
                client_side_filter=True,
            )
        ]
