from datetime import datetime

from pydantic import BaseModel


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
