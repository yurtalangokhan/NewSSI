import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.tools import connector_tools as tools


@pytest.mark.asyncio
async def test_live_endpoint_override_preserves_credentials_and_saved_config(monkeypatch):
    config = {"host": "postgres", "port": 5432, "password": "saved", "database": "source"}
    monkeypatch.setattr(
        tools,
        "get_settings",
        lambda: SimpleNamespace(
            connector_postgres_endpoints=json.dumps(
                {"assigned": {"host": "published", "port": 8124}}
            )
        ),
    )
    monkeypatch.setattr(
        tools,
        "_resolve_connector",
        AsyncMock(
            return_value={
                "config": config,
                "streams": ["public.roles"],
                "connector_type": "source-postgres",
            }
        ),
    )
    read = AsyncMock(return_value=[{"name": "real-role"}])
    monkeypatch.setattr(tools, "_read_postgres", read)
    await tools.connector_read("assigned", "public.roles")
    assert read.await_args.args[0] == {**config, "host": "published", "port": 8124}
    assert config["host"] == "postgres"


@pytest.mark.asyncio
async def test_endpoint_override_cannot_change_credentials(monkeypatch):
    monkeypatch.setattr(
        tools,
        "get_settings",
        lambda: SimpleNamespace(
            connector_postgres_endpoints=json.dumps({"assigned": {"password": "replacement"}})
        ),
    )
    monkeypatch.setattr(
        tools,
        "_resolve_connector",
        AsyncMock(
            return_value={"config": {}, "streams": ["roles"], "connector_type": "source-postgres"}
        ),
    )
    read = AsyncMock()
    monkeypatch.setattr(tools, "_read_postgres", read)
    result = json.loads(await tools.connector_read("assigned", "roles"))
    assert result["success"] is False
    assert result["error_category"] == "configuration"
    read.assert_not_called()
