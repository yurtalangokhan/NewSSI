"""OpenSearch source: the Elasticsearch reader with OpenSearch connection settings.

Covers self-managed OpenSearch and Amazon OpenSearch Service with basic
(internal user) authentication. IAM / SigV4 request signing is not supported.
"""

from __future__ import annotations

from ..base import secret_field
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind
from .elasticsearch import ElasticsearchSource, SearchIndexOptions


class OpenSearchConfig(SearchIndexOptions):
    username: str | None = None
    password: str | None = secret_field(default=None)


class OpenSearchSource(ElasticsearchSource[OpenSearchConfig]):
    definition = ConnectorDefinition(
        name="opensearch",
        display_name="OpenSearch",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.SEARCH_ENGINE,
        documentation_url="https://opensearch.org/docs/latest/api-reference/",
        icon="opensearch.svg",
        tags=frozenset({"search", "index", "self-hosted", "aws"}),
    )
    Config = OpenSearchConfig
