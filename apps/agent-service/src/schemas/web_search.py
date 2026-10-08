from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WebContent(BaseModel):
    title: str
    link: str
    full_content: str
    published_date: datetime | None = None
    scrape_successful: bool = True
    failure_reason: str | None = None


class FailedFetch(BaseModel):
    url: str
    failure_reason: str | None = None


class RenderedPage(BaseModel):
    html: str
    final_url: str
    last_modified: str | None = None
    status: int | None = None


class SearchProviderResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int | str | None = None
    name: str | None = None
    provider_type: str | None = None
    is_active: bool = True
    config: dict[str, Any] | None = None


class ContentProviderResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int | str
    name: str
    provider_type: str
    is_active: bool = True
    config: dict[str, Any] | None = None
    has_api_key: bool = False


class CrawlUrlResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str | None = None
    content: str | None = None
    scrape_successful: bool = True
    failure_reason: str | None = None


class WebSearchIdStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str = "ok"
    id: int | str
