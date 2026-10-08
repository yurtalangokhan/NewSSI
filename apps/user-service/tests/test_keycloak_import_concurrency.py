"""Bounded parallel user imports remain resumable after uncertain responses."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from src.service import keycloak_identity_import as importer


class BatchServer:
    def __init__(self, fail=False):
        self.users = []
        self.active = self.peak = self.posts = self.reads = 0
        self.fail = fail

    async def _keycloak_request(self, method, path, **kwargs):
        if method == "GET" and path == "/users":
            self.reads += 1
            data = list(self.users)
        else:
            assert path == "/partialImport"
            self.posts += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
            batch = kwargs["json"]["users"]
            try:
                await asyncio.sleep(0)
                if self.fail and batch[0]["username"] == "u0":
                    raise TimeoutError("Uncertain batch response")
                self.users.extend({"id": "kc-" + row["username"], **row} for row in batch)
                data = {}
            finally:
                self.active -= 1
        return httpx.Response(200, json=data, request=httpx.Request(method, "https://kc" + path))


def source():
    return {
        "users": [{"id": str(i), "username": f"u{i}", "role": "enduser"} for i in range(7)],
        "organizations": [],
    }


@pytest.mark.parametrize("concurrency", [1, 3, 8])
async def test_batch_workers_bound_inflight_and_report_monotonic_success(monkeypatch, concurrency):
    monkeypatch.setattr(importer, "group_profiles", AsyncMock(return_value={}))
    server = BatchServer()
    updates = []
    result = await importer.import_missing_identities(
        server,
        source(),
        batch_size=2,
        concurrency=concurrency,
        progress=lambda *args: updates.append(args),
    )
    assert server.peak == min(concurrency, 4)
    assert server.posts == 4 and server.active == 0
    assert len(result["users"]) == 7
    completed = [done for kind, done, total in updates if kind == "users"]
    assert completed == sorted(completed) and completed[-1] == 7


async def test_failed_batch_stops_new_work_and_never_returns_or_reports_complete(monkeypatch):
    monkeypatch.setattr(importer, "group_profiles", AsyncMock(return_value={}))
    server = BatchServer(fail=True)
    updates = []
    with pytest.raises(TimeoutError, match="Uncertain"):
        await importer.import_missing_identities(
            server,
            source(),
            batch_size=1,
            concurrency=2,
            progress=lambda *args: updates.append(args),
        )
    assert server.posts <= 2 and server.active == 0
    assert server.reads == 1  # No final inventory/mapping is presented after failure.
    assert all(done < total for kind, done, total in updates if kind == "users")


@pytest.mark.parametrize("concurrency", [0, 9])
async def test_invalid_concurrency_fails_before_io(concurrency):
    server = BatchServer()
    with pytest.raises(ValueError, match="concurrency"):
        await importer.import_missing_identities(server, source(), concurrency=concurrency)
    assert server.reads == server.posts == 0
