"""One id space for MCP providers, whichever endpoint you reach.

The admin API exposed two incompatible readings of the same URL segment:

* ``GET  /admin/mcp/server/{id}``   resolved the id as a blake2b hash of the
  provider UUID (``numeric_id_for``);
* ``PATCH``/``DELETE`` on that same path read it as ``MCPProviderModel.int_id``,
  the surrogate integer column.

Those are different numbers for the same provider, so a client that read a
server could not then update it. The DTO the frontend receives carries
``int_id`` (``"id": row["int_id"]``), which settles which reading is correct.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

PROVIDER = {"id": "0b5f1c2e-uuid", "int_id": 4242, "name": "GitHub"}


def _service(*, by_int_id=None, by_uuid=None):
    from service.mcp.mcp_provider_service import MCPProviderService

    svc = MCPProviderService(repo=AsyncMock())
    svc.get_by_int_id = AsyncMock(return_value=by_int_id)
    svc.get_provider = AsyncMock(return_value=by_uuid)
    return svc


@pytest.mark.asyncio
async def test_numeric_id_resolves_through_the_surrogate_column() -> None:
    svc = _service(by_int_id=PROVIDER)

    assert await svc.resolve_provider("4242") == PROVIDER
    svc.get_by_int_id.assert_awaited_once_with(4242)
    svc.get_provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_uuid_resolves_through_the_primary_key() -> None:
    svc = _service(by_uuid=PROVIDER)

    assert await svc.resolve_provider("0b5f1c2e-uuid") == PROVIDER
    svc.get_provider.assert_awaited_once_with("0b5f1c2e-uuid")
    svc.get_by_int_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unknown_id_resolves_to_none() -> None:
    svc = _service()

    assert await svc.resolve_provider("9999") is None
    assert await svc.resolve_provider("no-such-uuid") is None


@pytest.mark.asyncio
async def test_the_id_the_frontend_holds_is_the_one_that_resolves() -> None:
    """`to_mcp_server_dto` publishes `int_id`, so that must be what comes back."""
    svc = _service(by_int_id=PROVIDER)

    resolved = await svc.resolve_provider(str(PROVIDER["int_id"]))

    assert resolved["id"] == PROVIDER["id"]
