"""Tests for ``EntityExtractor.extract_from_text`` — previously covered only
for its timeout behaviour (``test_write_guards_and_background_tasks.py``).
These cover the actual entity/relation mapping: deduplication, auto-adding
nodes a relationship references but the transformer omitted from its own
node list, and graceful degradation on failure.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from openai import OpenAIError

from src.graph.entity_extractor import EntityExtractor


def _node(node_id: str, node_type: str = "Entity", properties: dict[str, Any] | None = None):
    return SimpleNamespace(id=node_id, type=node_type, properties=properties or {})


def _relationship(source, target, rel_type: str = "RELATED_TO", properties=None):
    return SimpleNamespace(
        source=source, target=target, type=rel_type, properties=properties or {}
    )


def _graph_document(nodes=(), relationships=()):
    return SimpleNamespace(nodes=list(nodes), relationships=list(relationships))


class _FakeTransformer:
    def __init__(self, graph_documents=None, *, error: Exception | None = None) -> None:
        self._graph_documents = graph_documents or []
        self._error = error

    async def aconvert_to_graph_documents(self, docs):
        if self._error:
            raise self._error
        return self._graph_documents


def _extractor(monkeypatch, graph_documents=None, *, error: Exception | None = None):
    extractor = EntityExtractor()
    monkeypatch.setattr(
        extractor, "_transformer", _FakeTransformer(graph_documents, error=error)
    )
    return extractor


@pytest.mark.asyncio
async def test_blank_text_short_circuits_without_calling_the_transformer(monkeypatch):
    extractor = _extractor(monkeypatch)
    monkeypatch.setattr(
        extractor,
        "_get_transformer",
        lambda: (_ for _ in ()).throw(AssertionError("must not build a transformer")),
    )

    result = await extractor.extract_from_text("   ", chunk_id="c1")

    assert result.entities == []
    assert result.relations == []
    assert result.chunk_id == "c1"


@pytest.mark.asyncio
async def test_maps_nodes_and_relationships_into_extraction_result(monkeypatch):
    alice = _node("Alice", "Person")
    acme = _node("Acme", "Company")
    graph_doc = _graph_document(
        nodes=[alice, acme],
        relationships=[_relationship(alice, acme, "WORKS_AT")],
    )
    extractor = _extractor(monkeypatch, [graph_doc])

    result = await extractor.extract_from_text("Alice works at Acme.")

    assert {e.name for e in result.entities} == {"Alice", "Acme"}
    assert len(result.relations) == 1
    assert result.relations[0].source == "Alice"
    assert result.relations[0].target == "Acme"
    assert result.relations[0].type == "WORKS_AT"


@pytest.mark.asyncio
async def test_deduplicates_entities_by_id_and_type(monkeypatch):
    alice_a = _node("Alice", "Person")
    alice_b = _node("Alice", "Person")  # same id:type, extracted twice
    graph_doc = _graph_document(nodes=[alice_a, alice_b])
    extractor = _extractor(monkeypatch, [graph_doc])

    result = await extractor.extract_from_text("Alice. Alice again.")

    assert len(result.entities) == 1


@pytest.mark.asyncio
async def test_same_id_different_type_is_not_deduplicated(monkeypatch):
    alice_person = _node("Alice", "Person")
    alice_company = _node("Alice", "Company")  # same id, different type
    graph_doc = _graph_document(nodes=[alice_person, alice_company])
    extractor = _extractor(monkeypatch, [graph_doc])

    result = await extractor.extract_from_text("Alice the person and Alice the company.")

    assert len(result.entities) == 2


@pytest.mark.asyncio
async def test_auto_adds_a_relationship_endpoint_missing_from_the_node_list(monkeypatch):
    """LLMGraphTransformer sometimes references a node in a relationship's
    source/target without also listing it in graph_doc.nodes -- every such
    endpoint must still end up in the entity list, or the relationship
    would point at a node that was never created.
    """
    alice = _node("Alice", "Person")
    acme = _node("Acme", "Company")  # never listed in `nodes`
    graph_doc = _graph_document(
        nodes=[alice],  # Acme is missing here on purpose
        relationships=[_relationship(alice, acme, "WORKS_AT")],
    )
    extractor = _extractor(monkeypatch, [graph_doc])

    result = await extractor.extract_from_text("Alice works at Acme.")

    names = {e.name for e in result.entities}
    assert names == {"Alice", "Acme"}


@pytest.mark.asyncio
async def test_degrades_to_empty_result_on_unexpected_extraction_failure(monkeypatch):
    extractor = _extractor(monkeypatch, error=OpenAIError("LLM provider error"))

    result = await extractor.extract_from_text("some text", chunk_id="c1")

    assert result.entities == []
    assert result.relations == []
    assert result.chunk_id == "c1"


@pytest.mark.asyncio
async def test_relation_without_explicit_properties_defaults_to_empty_dict(monkeypatch):
    alice = _node("Alice", "Person")
    bob = _node("Bob", "Person")
    rel = SimpleNamespace(source=alice, target=bob, type="KNOWS")  # no .properties at all
    graph_doc = _graph_document(nodes=[alice, bob], relationships=[rel])
    extractor = _extractor(monkeypatch, [graph_doc])

    result = await extractor.extract_from_text("Alice knows Bob.")

    assert result.relations[0].properties == {}
