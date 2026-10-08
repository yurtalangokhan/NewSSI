"""MinIO destination: the S3 destination with MinIO connection settings."""

from __future__ import annotations

from ..common.s3_connection import MinioConnection
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind
from .s3 import S3Destination, S3DestinationOptions


class MinioDestinationConfig(MinioConnection, S3DestinationOptions):
    """MinIO destination configuration."""


class MinioDestination(S3Destination[MinioDestinationConfig]):
    definition = ConnectorDefinition(
        name="minio",
        display_name="MinIO",
        kind=ConnectorKind.DESTINATION,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://min.io/docs/minio/linux/developers/python/API.html",
        icon="minio.svg",
        tags=frozenset({"file", "storage", "s3-compatible", "self-hosted"}),
    )
    Config = MinioDestinationConfig
    extra_name = "minio"
