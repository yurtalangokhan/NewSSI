"""Tests for SDK run streaming behavior."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from service.RunService import RunService


class DummyAgent:
    async def astream_events(self, input, config=None, stream_mode=None, version="v2"):
        yield {
            "event": "custom",
            "data": {
                "type": "long_term_memory_recall",
                "fact_count": 1,
                "memories": ["User likes tea"],
            },
        }
        yield {"event": "on_chain_end", "run_id": "run-1", "data": {"output": "done"}}


@pytest.mark.asyncio
async def test_event_generator_forwards_custom_ltm_event():
    service = RunService()
    cancel_event = asyncio.Event()

    with patch("service.RunService.register_run", return_value=cancel_event), patch(
        "service.RunService.get_run_context", return_value=None
    ), patch("service.RunService.unregister_run"):
        chunks = [
            chunk
            async for chunk in service.event_generator(
                DummyAgent(),
                [{"type": "human", "content": "hello"}],
                config={"configurable": {}},
                thread_id="thread-1",
                run_id="run-1",
                stream_mode=["custom"],
                user_id="user-1",
            )
        ]

    first_payload = json.loads(chunks[0].removeprefix("data: ").strip())
    assert first_payload["type"] == "long_term_memory_recall"
    assert first_payload["fact_count"] == 1
    assert chunks[-1] == "data: [DONE]\n\n"