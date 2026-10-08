"""Oracle Object Storage source: the S3 reader with Oracle Object Storage connection settings."""

from __future__ import annotations

from ..common.s3_connection import OracleObjectStorageConnection
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind
from .s3 import S3Source, S3SourceOptions


class OracleStorageConfig(OracleObjectStorageConnection, S3SourceOptions):
    """Oracle Object Storage source configuration."""


class OracleStorageSource(S3Source[OracleStorageConfig]):
    definition = ConnectorDefinition(
        name="oracle_storage",
        display_name="Oracle Object Storage",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.STORAGE,
        documentation_url="https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm",
        icon="oracle_storage.svg",
        tags=frozenset({"file", "cloud", "storage", "s3-compatible"}),
    )
    Config = OracleStorageConfig
    extra_name = "s3"
