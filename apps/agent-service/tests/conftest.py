import os
from pathlib import Path
from unittest.mock import patch

from localization import init_localization
import pytest

init_localization(Path(__file__).resolve().parents[1] / "locales")


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


def _drop_shared_http_clients() -> None:
    """Drop every pooled outbound client, tolerating clients whose loop is gone.

    ``security.close_all`` closes clients in the caller's event loop. A client
    a previous test created belongs to that test's loop, which has since closed,
    so closing it raises ``RuntimeError: Event loop is closed`` — and it could
    not serve anyone again anyway. Test isolation only needs the registries to
    start empty, so an unclosable client is dropped rather than fatal.
    """
    import asyncio

    import security.http as security_http

    clients = list(security_http._ASYNC_CLIENTS.values())
    security_http._ASYNC_CLIENTS.clear()
    security_http.close_all_sync()

    async def _close() -> None:
        for client in clients:
            try:
                await client.aclose()
            except RuntimeError:
                pass

    asyncio.run(_close())


@pytest.fixture
def patch_sync_outbound_client(monkeypatch):
    """Install a test double as the shared *sync* outbound client.

    ``outbound.get_sync_client`` reuses one ``httpx.Client`` per dependency for
    the life of the process; these tests are about the request a caller builds,
    not about how a socket opens, so they supply the client instead.
    """
    import contextlib

    from core.http import outbound

    def _install(client):
        monkeypatch.setattr(outbound, "get_sync_client", lambda dependency: client)
        # A no-op context manager, so call sites can keep the `with` shape of
        # the patch() calls they replace; teardown is monkeypatch's job.
        return contextlib.nullcontext()

    return _install


@pytest.fixture
def shared_http_clients():
    """Callable that empties the pooled-client registry for test isolation."""
    return _drop_shared_http_clients


@pytest.fixture
def patch_outbound_request(monkeypatch):
    """Route ``core.http.outbound.request`` through test doubles.

    The outbound transport is process-wide and pooled, so tests intercept it at
    this seam instead of patching ``httpx.AsyncClient``: what these tests are
    about is the request a caller builds, not how a socket gets opened. Each
    handler is called as ``handler(url, **kwargs)``, so an ``AsyncMock`` still
    exposes ``call_args.kwargs`` for assertions.
    """
    import contextlib
    import inspect

    from core.http import outbound

    def _install(*, get=None, post=None, default=None):
        async def _request(dependency, method, url, **kwargs):
            handler = {"GET": get, "POST": post}.get(method.upper()) or default
            if handler is None:
                raise AssertionError(f"unexpected outbound {method} {url}")
            result = handler(url, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result

        monkeypatch.setattr(outbound, "request", _request)
        # Returns a no-op context manager so call sites can use `with` for
        # symmetry with the patch() calls they replace; teardown is the
        # monkeypatch fixture's job either way.
        return contextlib.nullcontext()

    return _install


@pytest.fixture
def outbound_transport(monkeypatch):
    """Install a MockTransport-backed client as the shared outbound client."""
    import httpx

    from core.http import outbound

    def _install(handler) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        monkeypatch.setattr(outbound, "get_shared_client", lambda name, **kwargs: client)
        return client

    return _install


@pytest.fixture
def mock_env():
    """Fixture to ensure environment is clean for each test."""
    with patch.dict(os.environ, {}, clear=True):
        yield


@pytest.fixture(autouse=True)
def _reset_db_engine_singletons():
    """Keep the async DB engine per-test instead of process-global.

    ``infrastructure.db.engine`` caches the ``AsyncEngine`` and session factory in
    module-level singletons, but pytest-asyncio gives every test its own
    event loop. Without this, a connection pool created by one test's
    ``TestClient(app)`` lifespan stays bound to that (now-closed) loop and
    the next full-app test crashes with "attached to a different loop".
    Dropping the references forces the next ``get_db_engine()`` call to
    rebuild on the current loop; the orphaned pool is GC'd.
    """
    try:
        import infrastructure.db.engine as db_engine
    except ImportError:
        yield
        return

    db_engine._engine = None
    db_engine._session_factory = None
    yield
    db_engine._engine = None
    db_engine._session_factory = None


class _FakeTestRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        px: int | None = None,
        ex: int | None = None,
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args) -> int:
        if not keys_and_args:
            return 0
        key = keys_and_args[0]
        token = keys_and_args[1] if len(keys_and_args) > 1 else None
        if token is not None and self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if self.values.pop(key, None) is not None:
                deleted += 1
        return deleted

    async def aclose(self) -> None:
        self.values.clear()


@pytest.fixture(autouse=True)
def _reset_idempotency_redis_pool(monkeypatch):
    """Ensure idempotency uses in-memory fake redis during tests.

    Avoids attempting live network connections to external REDIS_HOST.
    """
    try:
        from idempotency import AsyncRedisPool
    except ImportError:
        yield
        return

    fake_redis = _FakeTestRedis()

    async def _mock_connect(config) -> _FakeTestRedis:
        return fake_redis

    monkeypatch.setattr(AsyncRedisPool, "connect", _mock_connect)
    AsyncRedisPool._pool = fake_redis
    yield
    AsyncRedisPool._pool = None
