"""XenForo source: forums (nodes), threads and posts through the REST API (XF 2.1+)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import (
    DeclarativeRestSource,
    PageNumberPagination,
    StreamSpec,
    from_epoch_seconds,
)
from ..common.text import html_to_text
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = PageNumberPagination(
    page_param="page", size_param=None, last_page_path="pagination.last_page"
)


class XenForoConfig(BaseModel):
    base_url: str = Field(description="Forum root, e.g. https://community.acme.com")
    api_key: str = secret_field(description="API key (super user or user scoped).")
    api_user_id: int | None = Field(default=None, description="Act as this user (super user keys).")
    include_posts: bool = True
    timeout_seconds: float = 60.0
    verify_ssl: bool = True


class XenForoSource(DeclarativeRestSource[XenForoConfig]):
    definition = ConnectorDefinition(
        name="xenforo",
        display_name="XenForo",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.MESSAGING,
        documentation_url="https://xenforo.com/community/pages/api-endpoints/",
        icon="xenforo.svg",
        tags=frozenset({"forum", "community", "self-hosted"}),
    )
    Config = XenForoConfig

    def base_url(self) -> str:
        return self.config.base_url.rstrip("/") + "/api"

    def auth_headers(self) -> dict[str, str]:
        headers = {"XF-Api-Key": self.config.api_key}
        if self.config.api_user_id is not None:
            headers["XF-Api-User"] = str(self.config.api_user_id)
        return headers

    def streams(self) -> list[StreamSpec]:
        specs = [
            StreamSpec(name="nodes", path="/nodes", records_path="nodes", primary_key=("node_id",)),
            StreamSpec(
                name="threads",
                path="/threads",
                records_path="threads",
                # Ordered by the cursor newest first: an incremental run stops at the
                # first page of threads it has already seen.
                params={"order": "last_post_date", "direction": "desc"},
                paginator=_PAGER,
                primary_key=("thread_id",),
                cursor_field="last_post_date",
                client_side_filter=True,
                stop_when_page_seen=True,
                transform=_thread,
            ),
        ]
        if self.config.include_posts:
            specs.append(
                StreamSpec(
                    name="posts",
                    path="/threads/{parent[thread_id]}/posts",
                    records_path="posts",
                    paginator=_PAGER,
                    primary_key=("post_id",),
                    parent="threads",
                    parent_key="thread_id",
                    # A new post moves its thread's last_post_date: an incremental run
                    # visits only the threads that changed since the posts cursor.
                    parent_uses_cursor=True,
                    cursor_field="post_date",
                    client_side_filter=True,
                    transform=_post,
                )
            )
        return specs


def _thread(rec: dict[str, Any]) -> dict[str, Any]:
    rec["last_post_at"] = from_epoch_seconds(rec.get("last_post_date"))
    return rec


def _post(rec: dict[str, Any]) -> dict[str, Any]:
    rec["posted_at"] = from_epoch_seconds(rec.get("post_date"))
    rec["text"] = html_to_text(rec.get("message_parsed")) or rec.get("message")
    return rec
