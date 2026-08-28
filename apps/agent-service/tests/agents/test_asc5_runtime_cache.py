from __future__ import annotations

import pytest

from agent_composition.application.runtime_cache import (
    AgentRuntimeCache,
    fingerprint_definition,
)
from agent_composition.domain.definitions import (
    AgentDefinition,
    BrainConfig,
    GraphSchemaConfig,
)


class FakeRuntime:
    def __init__(self, key: str) -> None:
        self.key = key
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def definition(
    *,
    identity: str = "agent-1",
    version: str = "1",
    graph_key: str = "react",
    nested: tuple[AgentDefinition, ...] = (),
) -> AgentDefinition:
    return AgentDefinition(
        identity=identity,
        version=version,
        brain=BrainConfig(key="standard_model", settings={"model": "gpt"}),
        graph=GraphSchemaConfig(key=graph_key, settings={"temperature": 0}),
        nested=nested,
    )


def test_definition_fingerprint_ignores_semantic_version():
    first = fingerprint_definition(definition(version="1"))
    second = fingerprint_definition(definition(version="2"))

    assert first == second


def test_definition_fingerprint_includes_nested_runtime_fields():
    first = fingerprint_definition(
        definition(nested=(definition(identity="child", graph_key="react"),))
    )
    second = fingerprint_definition(
        definition(nested=(definition(identity="child", graph_key="pipeline"),))
    )

    assert first != second


@pytest.mark.asyncio
async def test_runtime_cache_reuses_same_fingerprint_and_retires_replaced_runtime():
    cache = AgentRuntimeCache()
    created: list[FakeRuntime] = []

    async def factory(key: str) -> FakeRuntime:
        runtime = FakeRuntime(key)
        created.append(runtime)
        return runtime

    async with cache.lease("agent-1", "fp1", lambda: factory("first")) as first:
        async with cache.lease("agent-1", "fp1", lambda: factory("unused")) as reused:
            assert reused is first
        async with cache.lease("agent-1", "fp2", lambda: factory("second")) as second:
            assert second is not first
            assert not first.closed

        assert not first.closed

    assert first.closed
    assert not created[-1].closed

    await cache.shutdown()
    assert created[-1].closed
