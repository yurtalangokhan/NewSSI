"""Long-lived HTTP clients, one per logical peer. Spec T5.

Constructing an AsyncClient per request throws away connection reuse and
opens several new sockets per call to the same peer.
"""

import httpx
import pytest

from security.http import close_all, get_shared_client


@pytest.fixture(autouse=True)
async def _reset_pool():
    yield
    await close_all()


@pytest.mark.asyncio
async def test_same_name_returns_the_same_client():
    a = get_shared_client("user-service")
    b = get_shared_client("user-service")
    assert a is b


@pytest.mark.asyncio
async def test_different_names_are_isolated():
    assert get_shared_client("a") is not get_shared_client("b")


@pytest.mark.asyncio
async def test_close_all_closes_every_client():
    client = get_shared_client("x")
    await close_all()
    assert client.is_closed


@pytest.mark.asyncio
async def test_a_closed_client_is_replaced_on_next_access():
    first = get_shared_client("y")
    await close_all()
    second = get_shared_client("y")
    assert second is not first
    assert not second.is_closed


@pytest.mark.asyncio
async def test_clients_have_bounded_connection_pools():
    client = get_shared_client("z")
    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.connect is not None


# --- synchronous callers ----------------------------------------------------
# Module-level httpx.get/httpx.post build and discard a client (and therefore a
# connection pool) on every call. The sync twin below exists so blocking callers
# get the same reuse the async ones do.


def test_same_name_returns_the_same_sync_client():
    from security.http import get_shared_sync_client

    a = get_shared_sync_client("user-service")
    b = get_shared_sync_client("user-service")
    assert a is b
    assert isinstance(a, httpx.Client)
    a.close()


def test_sync_and_async_registries_are_separate():
    """A name must not hand a sync caller an async client, or vice versa."""
    from security.http import get_shared_sync_client

    async_client = get_shared_client("shared-name")
    sync_client = get_shared_sync_client("shared-name")

    assert isinstance(async_client, httpx.AsyncClient)
    assert isinstance(sync_client, httpx.Client)
    assert sync_client is not async_client
    sync_client.close()


def test_different_names_are_isolated_for_sync_clients():
    from security.http import get_shared_sync_client

    a = get_shared_sync_client("sync-a")
    b = get_shared_sync_client("sync-b")

    assert a is not b
    a.close()
    b.close()


def test_a_closed_sync_client_is_replaced_on_next_access():
    from security.http import get_shared_sync_client

    first = get_shared_sync_client("sync-replace")
    first.close()
    second = get_shared_sync_client("sync-replace")

    assert second is not first
    assert not second.is_closed
    second.close()


def test_close_all_sync_closes_only_the_sync_registry():
    from security.http import close_all_sync, get_shared_sync_client

    sync_client = get_shared_sync_client("sync-close")
    async_client = get_shared_client("async-untouched")

    close_all_sync()

    assert sync_client.is_closed
    assert not async_client.is_closed


@pytest.mark.asyncio
async def test_close_all_closes_sync_clients_too():
    """The lifespan shutdown hook drains both registries."""
    from security.http import get_shared_sync_client

    sync_client = get_shared_sync_client("sync-drained")
    async_client = get_shared_client("async-drained")

    await close_all()

    assert sync_client.is_closed
    assert async_client.is_closed


def test_sync_clients_have_bounded_connection_pools():
    from security.http import get_shared_sync_client

    client = get_shared_sync_client("sync-limits")

    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.connect is not None
    client.close()
