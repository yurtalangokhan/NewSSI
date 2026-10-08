"""Wikipedia source: the MediaWiki reader pointed at a language edition.

Crawling all of Wikipedia through the API is neither polite nor useful, so the
config requires ``titles`` or ``categories``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ..base import secret_field
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind
from .mediawiki import WikiScope, WikiSource


class WikipediaEdition(BaseModel):
    language: str = Field(default="en", description="Language edition, e.g. 'en', 'tr', 'de'.")


class WikipediaConfig(WikiScope, WikipediaEdition):
    """The language edition (listed first in the form), then what to read from it."""

    titles: list[str] | None = Field(default=None, description="Article titles to read.")
    bearer_token: str | None = secret_field(default=None)
    user_agent: str = Field(
        default="connector-py/0.1 (wikipedia source)",
        description="Wikimedia asks for a descriptive User-Agent with contact details.",
    )

    @model_validator(mode="after")
    def _needs_scope(self) -> WikipediaConfig:
        if not self.titles and not self.categories:
            raise ValueError("wikipedia source requires titles or categories")
        return self


class WikipediaSource(WikiSource[WikipediaConfig]):
    definition = ConnectorDefinition(
        name="wikipedia",
        display_name="Wikipedia",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.KNOWLEDGE_BASE,
        documentation_url="https://www.mediawiki.org/wiki/API:Main_page",
        icon="wikipedia.svg",
        tags=frozenset({"wiki", "public"}),
    )
    Config = WikipediaConfig

    def api_url(self) -> str:
        return f"https://{self.config.language}.wikipedia.org/w/api.php"
