"""Smoke tests for the graph entrypoints published to LangGraph Studio."""

import importlib
import json
from pathlib import Path

import pytest

LANGGRAPH_CONFIG = Path(__file__).parents[2] / "langgraph.json"


def _load_graph_entries() -> dict[str, str]:
    with LANGGRAPH_CONFIG.open(encoding="ascii") as config_file:
        config = json.load(config_file)

    assert isinstance(config, dict)
    graphs = config.get("graphs")
    assert isinstance(graphs, dict)
    assert graphs
    return graphs


def _entrypoint_cases() -> list[tuple[str, str, str]]:
    cases = []
    for graph_name, entrypoint in _load_graph_entries().items():
        assert isinstance(graph_name, str)
        assert isinstance(entrypoint, str)
        module_path, separator, attribute = entrypoint.rpartition(":")
        assert separator and module_path and attribute

        source_path = Path(module_path)
        assert source_path.parts[0] == "src"
        module_name = ".".join(source_path.with_suffix("").parts[1:])
        cases.append((graph_name, module_name, attribute))
    return cases


def test_langgraph_config_parses_and_lists_graphs() -> None:
    graphs = _load_graph_entries()

    assert set(graphs) == {
        "chatbot",
        "research-assistant",
        "rag-assistant",
        "graph-rag-assistant",
    }


@pytest.mark.parametrize(
    ("graph_name", "module_name", "attribute"),
    _entrypoint_cases(),
    ids=lambda case: case if isinstance(case, str) else str(case),
)
def test_langgraph_entrypoint_imports_and_exports_graph(
    graph_name: str, module_name: str, attribute: str
) -> None:
    module = importlib.import_module(module_name)

    assert hasattr(module, attribute), f"{graph_name} must export {attribute}"
    assert getattr(module, attribute) is not None


@pytest.mark.parametrize(
    ("graph_name", "module_name", "attribute"),
    _entrypoint_cases(),
    ids=lambda case: case if isinstance(case, str) else str(case),
)
def test_langgraph_studio_recipes_do_not_pin_a_model(
    graph_name: str, module_name: str, attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Studio recipes must let runtime provider defaults choose the model."""
    module = importlib.import_module(module_name)
    captured: dict[str, object] = {}

    class FakeGraphBuilder:
        def __init__(self, **kwargs):
            captured["builder_kwargs"] = kwargs

        def build(self, schema, recipe):
            captured["schema"] = schema
            captured["recipe"] = recipe
            return object()

    monkeypatch.setattr(module, "GraphBuilder", FakeGraphBuilder)

    graph = getattr(module, attribute)()

    assert graph is not None
    recipe = captured["recipe"]
    assert isinstance(recipe, dict)
    assert "model" not in recipe, f"{graph_name} Studio recipe must not hardcode a model"
