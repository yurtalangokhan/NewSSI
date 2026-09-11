import os
from pathlib import Path
from unittest.mock import patch

import pytest
from i18n import init_service_i18n

init_service_i18n(Path(__file__).resolve().parents[1] / "locales")


def pytest_addoption(parser):
    parser.addoption(
        "--run-docker", action="store_true", default=False, help="run docker integration tests"
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "docker: mark test as requiring docker containers")
    config.addinivalue_line("markers", "integration: mark test as a live/network integration test")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-docker"):
        skip_docker = pytest.mark.skip(reason="need --run-docker option to run")
        for item in items:
            if "docker" in item.keywords:
                item.add_marker(skip_docker)


@pytest.fixture
def mock_env():
    """Fixture to ensure environment is clean for each test."""
    with patch.dict(os.environ, {}, clear=True):
        yield


@pytest.fixture(autouse=True)
def _reset_db_engine_singletons():
    """Keep the async DB engine per-test instead of process-global.

    ``core.db.engine`` caches the ``AsyncEngine`` and session factory in
    module-level singletons, but pytest-asyncio gives every test its own
    event loop. Without this, a connection pool created by one test's
    ``TestClient(app)`` lifespan stays bound to that (now-closed) loop and
    the next full-app test crashes with "attached to a different loop".
    Dropping the references forces the next ``get_db_engine()`` call to
    rebuild on the current loop; the orphaned pool is GC'd.
    """
    try:
        import core.db.engine as db_engine
    except ImportError:
        yield
        return

    db_engine._engine = None
    db_engine._session_factory = None
    yield
    db_engine._engine = None
    db_engine._session_factory = None


@pytest.fixture(autouse=True)
def _reset_idempotency_redis_pool():
    """Same reasoning as ``_reset_db_engine_singletons``, for Redis.

    ``AsyncRedisPool`` caches one ``aioredis.Redis`` on the class. A pool
    opened by one test's ``TestClient(app)`` lifespan stays bound to that
    test's (now-closed) event loop, so the next full-app test fails inside the
    idempotency middleware with "Event loop is closed". Dropping the reference
    makes the next ``connect()`` build a pool on the current loop.
    """
    try:
        from idempotency import AsyncRedisPool
    except ImportError:
        yield
        return

    AsyncRedisPool._pool = None
    yield
    AsyncRedisPool._pool = None
