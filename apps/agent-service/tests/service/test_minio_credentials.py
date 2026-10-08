"""MinIO must receive plaintext credentials, not the SecretStr wrapper."""

import sys
import types

import pytest


@pytest.fixture
def captured_minio(monkeypatch):
    """Install a stub ``minio`` module and capture the constructor kwargs."""
    captured: dict[str, object] = {}

    class _StubMinio:
        def __init__(self, endpoint, **kwargs):
            captured["endpoint"] = endpoint
            captured.update(kwargs)

        def bucket_exists(self, bucket):  # pragma: no cover - trivial stub
            return True

    minio_module = types.ModuleType("minio")
    minio_module.Minio = _StubMinio
    error_module = types.ModuleType("minio.error")
    error_module.S3Error = type("S3Error", (Exception,), {})

    monkeypatch.setitem(sys.modules, "minio", minio_module)
    monkeypatch.setitem(sys.modules, "minio.error", error_module)
    return captured


def test_secret_key_reaches_the_client_unmasked(monkeypatch, captured_minio) -> None:
    from service.storage import minio_service as MinioService

    monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "s3cr3t")
    MinioService._get_client.cache_clear()

    MinioService._get_client()

    assert captured_minio["secret_key"] == "s3cr3t"
    assert "*" not in str(captured_minio["secret_key"])


def test_client_is_built_with_a_bounded_timeout(monkeypatch, captured_minio) -> None:
    """An unreachable MinIO must fail, not block the request thread forever.

    ``bucket_exists`` is called while building the client. With urllib3's default
    (no timeout) a blackholed endpoint hangs the caller indefinitely, and file
    upload runs on the request path.
    """
    from service.storage import minio_service as MinioService

    monkeypatch.setenv("MINIO_ACCESS_KEY", "key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "secret")
    MinioService._get_client.cache_clear()

    MinioService._get_client()

    http_client = captured_minio.get("http_client")
    assert http_client is not None, "MinIO was built with urllib3's unbounded default"
    timeout = http_client.connection_pool_kw.get("timeout")
    assert timeout is not None
    assert timeout.connect_timeout and timeout.connect_timeout > 0
    assert timeout.read_timeout and timeout.read_timeout > 0
