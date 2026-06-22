"""
MinioService — MinIO object storage client for document persistence.

Files uploaded to chats or projects are stored in MinIO under the
``agent-service-documents`` bucket (configurable via MINIO_BUCKET env).

Object key format:
    documents/{user_id}/{file_id}/{filename}

This allows easy retrieval by file_id and scoping by user.
"""

from __future__ import annotations

import io
import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from core.settings import settings

if TYPE_CHECKING:
    from minio import Minio

logger = logging.getLogger(__name__)


def _build_object_key(user_id: str, file_id: str, filename: str) -> str:
    """Build a deterministic MinIO object key for a file."""
    # Sanitize filename to avoid path traversal
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"documents/{user_id}/{file_id}/{safe_name}"


@lru_cache(maxsize=1)
def _get_client() -> Minio:
    """Return a cached MinIO client, ensuring the bucket exists."""
    from minio import Minio
    from minio.error import S3Error

    client = Minio(
        f"{settings.MINIO_HOST}:{settings.MINIO_PORT}",
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )

    bucket = settings.MINIO_BUCKET
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("Created MinIO bucket: %s", bucket)
    except S3Error as exc:
        logger.warning("Could not ensure MinIO bucket '%s' exists: %s", bucket, exc)

    return client


def upload_file(
    user_id: str,
    file_id: str,
    filename: str,
    data: bytes,
    mime_type: str,
) -> str:
    """Upload bytes to MinIO and return the object key.

    Raises on failure — callers should handle exceptions if MinIO is optional.
    """
    client = _get_client()
    object_key = _build_object_key(user_id, file_id, filename)
    client.put_object(
        settings.MINIO_BUCKET,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=mime_type,
    )
    logger.info("Uploaded file to MinIO: %s (%d bytes)", object_key, len(data))
    return object_key


def download_file(object_key: str) -> bytes:
    """Download and return the raw bytes of an object from MinIO."""
    client = _get_client()
    response = client.get_object(settings.MINIO_BUCKET, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_file(object_key: str) -> None:
    """Remove an object from MinIO (best-effort — logs on error)."""
    try:
        client = _get_client()
        client.remove_object(settings.MINIO_BUCKET, object_key)
        logger.info("Deleted MinIO object: %s", object_key)
    except Exception as exc:
        logger.warning("Could not delete MinIO object '%s': %s", object_key, exc)


def get_presigned_url(object_key: str, expires_seconds: int = 3600) -> str:
    """Return a presigned GET URL valid for ``expires_seconds``."""
    from datetime import timedelta

    client = _get_client()
    return client.presigned_get_object(
        settings.MINIO_BUCKET,
        object_key,
        expires=timedelta(seconds=expires_seconds),
    )
