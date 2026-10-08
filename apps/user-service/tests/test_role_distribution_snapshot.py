"""The role distribution is served from a snapshot and never computed on the request path."""

import asyncio

import pytest

from src.service.role_distribution import RoleDistributionSnapshot

DISTRIBUTION = [{"role": "enduser", "count": 3}]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Directory:
    """A distribution computation the test releases explicitly."""

    def __init__(self):
        self.calls = 0
        self.release = asyncio.Event()
        self.result = DISTRIBUTION
        self.error: Exception | None = None

    async def compute(self):
        self.calls += 1
        await self.release.wait()
        if self.error is not None:
            raise self.error
        return self.result


async def settle():
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.fixture
def setup():
    directory, clock = Directory(), Clock()
    snapshot = RoleDistributionSnapshot(
        directory.compute, refresh_after=300.0, retry_after=30.0, clock=clock
    )
    return snapshot, directory, clock


@pytest.mark.asyncio
async def test_a_cold_read_returns_pending_at_once_and_computes_in_the_background(setup):
    snapshot, directory, _ = setup

    first = await asyncio.wait_for(snapshot.read(), timeout=0.5)

    assert first == {"status": "pending", "distribution": [], "computed_at": None}
    directory.release.set()
    await settle()
    ready = await snapshot.read()
    assert ready["status"] == "ready"
    assert ready["distribution"] == DISTRIBUTION
    assert ready["computed_at"] is not None


@pytest.mark.asyncio
async def test_concurrent_reads_share_one_computation(setup):
    snapshot, directory, _ = setup

    await asyncio.gather(*(snapshot.read() for _ in range(5)))
    await snapshot.read()

    assert directory.calls == 1


@pytest.mark.asyncio
async def test_a_fresh_value_is_served_without_recomputing(setup):
    snapshot, directory, clock = setup
    directory.release.set()
    await snapshot.read()
    await settle()

    clock.now += 299
    assert (await snapshot.read())["status"] == "ready"
    await settle()

    assert directory.calls == 1


@pytest.mark.asyncio
async def test_a_stale_value_is_served_while_one_refresh_runs(setup):
    snapshot, directory, clock = setup
    directory.release.set()
    await snapshot.read()
    await settle()
    directory.release.clear()
    directory.result = [{"role": "auditor", "count": 9}]

    clock.now += 301
    stale = await snapshot.read()
    await settle()
    await snapshot.read()
    await settle()

    assert stale["status"] == "ready" and stale["distribution"] == DISTRIBUTION
    assert directory.calls == 2
    directory.release.set()
    await settle()
    assert (await snapshot.read())["distribution"] == [{"role": "auditor", "count": 9}]


@pytest.mark.asyncio
async def test_a_failed_refresh_keeps_the_last_good_value(setup):
    snapshot, directory, clock = setup
    directory.release.set()
    await snapshot.read()
    await settle()
    directory.error = TimeoutError("keycloak")

    clock.now += 301
    await snapshot.read()
    await settle()

    assert (await snapshot.read())["distribution"] == DISTRIBUTION


@pytest.mark.asyncio
async def test_a_failure_without_a_value_is_unavailable_until_the_retry_delay(setup):
    snapshot, directory, clock = setup
    directory.error = TimeoutError("keycloak")
    directory.release.set()
    await snapshot.read()
    await settle()

    assert (await snapshot.read())["status"] == "unavailable"
    assert directory.calls == 1

    clock.now += 31
    directory.error = None
    assert (await snapshot.read())["status"] == "pending"
    await settle()
    assert (await snapshot.read())["status"] == "ready"
    assert directory.calls == 2
