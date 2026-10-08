"""
MinioService — MinIO object storage client for document persistence.

Files uploaded to chats or projects are stored in MinIO under the
``agent-service-documents`` bucket (configurable via MINIO_BUCKET env).

Object key format:
    documents/{user_id}/{file_id}/{filename}

This allows easy retrieval by file_id and scoping by user.
"""

from __future__ import annotations

from functools import lru_cache
import io
from typing import TYPE_CHECKING

from config_manager import env
from security import require_secret, timeout_for

from core.observability.logger import get_logger

if TYPE_CHECKING:
    from minio import Minio

logger = get_logger(__name__)


def _build_object_key(user_id: str, file_id: str, filename: str) -> str:
    """Build a deterministic MinIO object key for a file."""
    # Sanitize filename to avoid path traversal
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"documents/{user_id}/{file_id}/{safe_name}"


def _bounded_http_client():
    """An HTTP pool that gives up instead of blocking forever.

    MinIO calls happen on the request path. urllib3 defaults to no timeout at
    all, so an endpoint that accepts the connection and then goes quiet — or one
    that blackholes packets — parks the worker indefinitely. The budget comes
    from ``configs/resilience.yaml`` so it is tuned in one place with every other
    outbound call.
    """
    import urllib3

    budget = timeout_for("minio")
    return urllib3.PoolManager(
        timeout=urllib3.Timeout(connect=min(budget, 5.0), read=budget),
        retries=urllib3.Retry(total=2, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504]),
    )


@lru_cache(maxsize=1)
def _get_client() -> Minio:
    """Return a cached MinIO client, ensuring the bucket exists."""
    from minio import Minio
    from minio.error import S3Error

    client = Minio(
        f"{env.MINIO_HOST}:{env.MINIO_PORT}",
        access_key=require_secret(env.MINIO_ACCESS_KEY, "MINIO_ACCESS_KEY"),
        secret_key=require_secret(env.MINIO_SECRET_KEY, "MINIO_SECRET_KEY"),
        secure=env.MINIO_SECURE,
        http_client=_bounded_http_client(),
    )

    bucket = env.MINIO_BUCKET
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("Created MinIO bucket: %s", bucket)
    except (S3Error, OSError) as exc:
        # A missing bucket must not stop the client from being returned: uploads
        # surface their own error, and callers already treat MinIO as optional.
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
        env.MINIO_BUCKET,
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
    response = client.get_object(env.MINIO_BUCKET, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_file(object_key: str) -> None:
    """Remove an object from MinIO (best-effort — logs on error)."""
    try:
        client = _get_client()
        client.remove_object(env.MINIO_BUCKET, object_key)
        logger.info("Deleted MinIO object: %s", object_key)
    except Exception as exc:
        logger.warning("Could not delete MinIO object '%s': %s", object_key, exc)
