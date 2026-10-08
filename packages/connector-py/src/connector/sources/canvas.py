"""Canvas LMS source: courses and, per course, pages, assignments and announcements."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..base import secret_field
from ..common.declarative import DeclarativeRestSource, LinkHeaderPagination, StreamSpec
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind

_PAGER = LinkHeaderPagination(size_param="per_page", page_size=100)


class CanvasConfig(BaseModel):
    base_url: str = Field(description="e.g. https://acme.instructure.com")
    access_token: str = secret_field(description="Canvas API access token.")
    enrollment_state: str | None = Field(default="active", description="Course filter.")
    timeout_seconds: float = 30.0


class CanvasSource(DeclarativeRestSource[CanvasConfig]):
    definition = ConnectorDefinition(
        name="canvas",
        display_name="Canvas LMS",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://canvas.instructure.com/doc/api/",
        icon="canvas.svg",
        tags=frozenset({"saas", "lms", "education"}),
    )
    Config = CanvasConfig

    def base_url(self) -> str:
        return self.config.base_url

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.access_token}"}

    def streams(self) -> list[StreamSpec]:
        def per_course(name: str, path: str, pk: str = "id", **params: str) -> StreamSpec:
            return StreamSpec(
                name=name,
                path=f"/api/v1/courses/{{parent[id]}}/{path}",
                params=params,
                paginator=_PAGER,
                parent="courses",
                parent_field="course_id",
                primary_key=(pk,),
                cursor_field="updated_at",
                client_side_filter=True,
            )

        return [
            StreamSpec(
                name="courses",
                path="/api/v1/courses",
                params={"enrollment_state": self.config.enrollment_state},
                paginator=_PAGER,
            ),
            per_course("pages", "pages", "page_id", **{"include[]": "body"}),
            per_course("assignments", "assignments"),
            per_course("announcements", "discussion_topics", only_announcements="true"),
        ]
