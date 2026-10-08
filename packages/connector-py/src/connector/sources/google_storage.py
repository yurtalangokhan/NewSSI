"""Google Cloud Storage source: the S3 reader with Google Cloud Storage connection settings."""

from __future__ import annotations

from ..common.s3_connection import GcsHmacConnection
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind
from .s3 import S3Source, S3SourceOptions


class GoogleStorageConfig(GcsHmacConnection, S3SourceOptions):
    """Google Cloud Storage source configuration."""


class GoogleStorageSource(S3Source[GoogleStorageConfig]):
    definition = ConnectorDefinition(
        name="google_storage",
        display_name="Google Cloud Storage",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://cloud.google.com/storage/docs/interoperability",
        icon="google_storage.svg",
        tags=frozenset({"file", "cloud", "storage", "google", "s3-compatible"}),
    )
    Config = GoogleStorageConfig
    extra_name = "s3"
