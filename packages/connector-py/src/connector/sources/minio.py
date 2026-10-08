"""MinIO source.

Same reader as :class:`~connector.sources.s3.S3Source` (globs, csv/jsonl/json,
``LastModified`` cursor); only the connection settings differ. MinIO users think
in terms of *endpoint + access key + secret key*, and the server needs
path-style URLs, so it gets its own catalog entry and config form instead of
asking people to fill an "AWS" form with a custom endpoint.
"""

from __future__ import annotations

from ..common.s3_connection import MinioConnection
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind
from .s3 import S3Source, S3SourceOptions


class MinioConfig(MinioConnection, S3SourceOptions):
    """MinIO source configuration."""


class MinioSource(S3Source[MinioConfig]):
    definition = ConnectorDefinition(
        name="minio",
        display_name="MinIO",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://min.io/docs/minio/linux/developers/python/API.html",
        icon="minio.svg",
        tags=frozenset({"file", "storage", "s3-compatible", "self-hosted"}),
    )
    Config = MinioConfig
    extra_name = "minio"
