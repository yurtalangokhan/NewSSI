"""Resolving a model must not block the event loop.

Building a graph resolves its model, and resolving a model can go to the
network: inside a running loop get_model takes the direct-lookup branch,
which asks Ollama whether the model supports reasoning over a synchronous
httpx client with a three second timeout. That call happens on the first
use of each model, on whatever loop the request arrived on -- so one cold
model stalls every other request in the process, health checks included,
for as long as Ollama takes to answer (or to time out).

The probe result is cached per model, so this is not a per-request cost;
it is a rare, large one, which is exactly the kind that shows up as an
unexplained latency spike rather than as a slow endpoint.
"""

from __future__ import annotations

import threading

import pytest

from agents.graphs.builder import GraphBuilder


@pytest.fixture
def model_resolution_threads(monkeypatch) -> list[str]:
    """Record which thread each model resolution ran on."""
    threads: list[str] = []

    def fake_get_model(model_name=None):
        threads.append(threading.current_thread().name)
        return object()

    monkeypatch.setattr("infrastructure.llm.llm.get_model", fake_get_model)
    monkeypatch.setattr("infrastructure.llm.get_model", fake_get_model)
    return threads


@pytest.mark.asyncio
async def test_building_a_react_graph_resolves_its_model_off_the_loop(
    monkeypatch, model_resolution_threads
) -> None:
    monkeypatch.setattr("agents.graphs.strategies.react.create_agent", lambda **_kw: object())
    loop_thread = threading.current_thread().name

    await GraphBuilder().build_async("react", {"system_prompt": "Be helpful."})

    assert model_resolution_threads, "no model was resolved"
    assert loop_thread not in model_resolution_threads, (
        "get_model ran on the event loop thread; its Ollama capability probe "
        "blocks every other request in the process"
    )


@pytest.mark.asyncio
async def test_building_a_plan_execute_graph_resolves_its_model_off_the_loop(
    monkeypatch, model_resolution_threads
) -> None:
    monkeypatch.setattr(
        "agents.graphs.strategies.plan_execute.create_react_agent", lambda **_kw: object()
    )
    loop_thread = threading.current_thread().name

    await GraphBuilder().build_async("plan_execute", {"system_prompt": "Plan."})

    assert model_resolution_threads
    assert loop_thread not in model_resolution_threads


@pytest.mark.asyncio
async def test_an_injected_model_is_used_without_going_to_the_network(
    monkeypatch, model_resolution_threads
) -> None:
    """A caller that already has a model must not trigger a lookup at all."""
    monkeypatch.setattr("agents.graphs.strategies.react.create_agent", lambda **_kw: object())
    injected = object()

    await GraphBuilder(model=injected).build_async("react", {"system_prompt": "Be helpful."})

    assert model_resolution_threads == []
