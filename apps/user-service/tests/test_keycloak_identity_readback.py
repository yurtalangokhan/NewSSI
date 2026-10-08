"""Importer readback is bounded, ordered, and refuses incomplete identity pages."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.service.keycloak_identity_import import user_profiles


def response(value):
    return httpx.Response(200, json=value, request=httpx.Request("GET", "https://kc.invalid/users"))


async def test_user_readback_prefetch_is_bounded_and_ordered():
    active = maximum = 0
    offsets = []

    async def request(method, path, **kwargs):
        nonlocal active, maximum
        params = kwargs["params"]
        assert method == "GET" and path == "/users"
        assert params["max"] == 1000 and params["briefRepresentation"] == "false"
        first = params["first"]
        offsets.append(first)
        active += 1
        maximum = max(maximum, active)
        try:
            await asyncio.sleep(0)
            return response([{"id": str(i)} for i in range(first, min(first + 1000, 10001))])
        finally:
            active -= 1

    rows = await user_profiles(SimpleNamespace(_keycloak_request=request))
    assert [row["id"] for row in rows] == [str(i) for i in range(10001)]
    assert maximum == 8 and active == 0
    assert offsets == list(range(0, 17000, 1000))


@pytest.mark.parametrize(
    "payload", [{}, [None], [{}], [{"id": ""}], [{"id": "one"}, {"id": "one"}]]
)
async def test_user_readback_rejects_invalid_page_and_duplicate_ids(payload):
    keycloak = SimpleNamespace(_keycloak_request=AsyncMock(return_value=response(payload)))
    with pytest.raises(ValueError, match="inventory"):
        await user_profiles(keycloak)


async def test_user_readback_empty_inventory_fetches_once():
    keycloak = SimpleNamespace(_keycloak_request=AsyncMock(return_value=response([])))
    assert await user_profiles(keycloak) == []
    keycloak._keycloak_request.assert_awaited_once()


async def test_user_readback_detects_duplicate_across_pages():
    async def request(method, path, **kwargs):
        first = kwargs["params"]["first"]
        return response([{"id": "one"}] if first <= 1 else [])

    with pytest.raises(ValueError, match="repeated IDs"):
        await user_profiles(SimpleNamespace(_keycloak_request=request), page_size=1)


async def test_user_readback_waits_for_failed_wave_before_propagating():
    active = 0

    async def request(method, path, **kwargs):
        nonlocal active
        first = kwargs["params"]["first"]
        active += 1
        try:
            await asyncio.sleep(0)
            if first == 2:
                raise RuntimeError("readback failed")
            return response([{"id": str(first)}])
        finally:
            active -= 1

    with pytest.raises(RuntimeError, match="readback failed"):
        await user_profiles(SimpleNamespace(_keycloak_request=request), page_size=1)
    assert active == 0
