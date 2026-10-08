"""Cloudflare R2 source: the S3 reader with Cloudflare R2 connection settings."""

from __future__ import annotations

from ..common.s3_connection import CloudflareR2Connection
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind
from .s3 import S3Source, S3SourceOptions


class CloudflareR2Config(CloudflareR2Connection, S3SourceOptions):
    """Cloudflare R2 source configuration."""


class CloudflareR2Source(S3Source[CloudflareR2Config]):
    definition = ConnectorDefinition(
        name="cloudflare_r2",
        display_name="Cloudflare R2",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://developers.cloudflare.com/r2/api/s3/api/",
        icon="cloudflare_r2.svg",
        tags=frozenset({"file", "cloud", "storage", "s3-compatible"}),
    )
    Config = CloudflareR2Config
    extra_name = "s3"
