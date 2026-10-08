"""Connection settings and client factory shared by the S3 / MinIO connectors.

Amazon S3 and MinIO speak the same API but are configured differently by their
users (AWS: region + IAM keys; MinIO: endpoint + access/secret key, path-style
URLs). Each flavour gets its own pydantic mixin that knows how to turn itself
into ``boto3.client`` keyword arguments; sources and destinations combine a
mixin with their own options and never touch boto3 directly.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..base import secret_field
from ..extras import require_extra


class AwsConnection(BaseModel):
    """Amazon S3 (or any endpoint that accepts AWS-style settings)."""

    region: str | None = None
    endpoint_url: str | None = Field(default=None, description="Custom S3-compatible endpoint.")
    aws_access_key_id: str | None = secret_field(default=None)
    aws_secret_access_key: str | None = secret_field(default=None)
    aws_session_token: str | None = secret_field(default=None)

    def client_kwargs(self) -> dict[str, Any]:
        return {
            "region_name": self.region,
            "endpoint_url": self.endpoint_url,
            "aws_access_key_id": self.aws_access_key_id,
            "aws_secret_access_key": self.aws_secret_access_key,
            "aws_session_token": self.aws_session_token,
        }


class MinioConnection(BaseModel):
    """MinIO server. Uses path-style addressing and SigV4, as MinIO expects."""

    endpoint: str = Field(
        description="Host and port, e.g. 'minio:9000'. A full URL (http://...) is accepted too."
    )
    access_key: str = secret_field(description="MinIO access key.")
    secret_key: str = secret_field(description="MinIO secret key.")
    secure: bool = Field(default=False, description="Use HTTPS when `endpoint` has no scheme.")
    region: str = Field(default="us-east-1", description="MinIO default region.")
    verify_ssl: bool = True

    def endpoint_url(self) -> str:
        if self.endpoint.startswith(("http://", "https://")):
            return self.endpoint.rstrip("/")
        return f"{'https' if self.secure else 'http'}://{self.endpoint.rstrip('/')}"

    def client_kwargs(self) -> dict[str, Any]:
        return {
            "region_name": self.region,
            "endpoint_url": self.endpoint_url(),
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "verify": self.verify_ssl,
            "path_style": True,
        }


class GcsHmacConnection(BaseModel):
    """Google Cloud Storage through its S3-compatible XML API (HMAC keys)."""

    hmac_access_id: str = secret_field(description="HMAC access id (Interoperability settings).")
    hmac_secret: str = secret_field(description="HMAC secret.")
    endpoint: str = Field(default="https://storage.googleapis.com")

    def client_kwargs(self) -> dict[str, Any]:
        return {
            "region_name": "auto",
            "endpoint_url": self.endpoint.rstrip("/"),
            "aws_access_key_id": self.hmac_access_id,
            "aws_secret_access_key": self.hmac_secret,
            "path_style": True,
        }


class OracleObjectStorageConnection(BaseModel):
    """OCI Object Storage through the Amazon S3 Compatibility API (customer secret keys)."""

    namespace: str = Field(description="Object Storage namespace of the tenancy.")
    region: str = Field(description="OCI region identifier, e.g. 'eu-frankfurt-1'.")
    access_key: str = secret_field(description="Customer secret key: access key.")
    secret_key: str = secret_field(description="Customer secret key: secret.")

    def endpoint_url(self) -> str:
        return f"https://{self.namespace}.compat.objectstorage.{self.region}.oraclecloud.com"

    def client_kwargs(self) -> dict[str, Any]:
        return {
            "region_name": self.region,
            "endpoint_url": self.endpoint_url(),
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "path_style": True,
        }


class CloudflareR2Connection(BaseModel):
    """Cloudflare R2 (S3-compatible; region is always ``auto``)."""

    account_id: str = Field(description="Cloudflare account id.")
    access_key_id: str = secret_field(description="R2 API token: access key id.")
    secret_access_key: str = secret_field(description="R2 API token: secret access key.")
    jurisdiction: str | None = Field(default=None, description="'eu' or 'fedramp', if used.")

    def endpoint_url(self) -> str:
        suffix = f".{self.jurisdiction}" if self.jurisdiction else ""
        return f"https://{self.account_id}{suffix}.r2.cloudflarestorage.com"

    def client_kwargs(self) -> dict[str, Any]:
        return {
            "region_name": "auto",
            "endpoint_url": self.endpoint_url(),
            "aws_access_key_id": self.access_key_id,
            "aws_secret_access_key": self.secret_access_key,
        }


def build_s3_client(kwargs: dict[str, Any], *, extra_name: str = "s3") -> Any:
    """Create a boto3 S3 client from ``client_kwargs()`` output."""
    boto3 = require_extra("boto3", extra=extra_name, feature=f"the {extra_name} connector")
    botocore_config = require_extra("botocore.config", extra=extra_name)
    kwargs = dict(kwargs)
    path_style = kwargs.pop("path_style", False)
    config = botocore_config.Config(
        signature_version="s3v4",
        s3={"addressing_style": "path" if path_style else "auto"},
        retries={"max_attempts": 5, "mode": "standard"},
    )
    return boto3.client("s3", config=config, **kwargs)
