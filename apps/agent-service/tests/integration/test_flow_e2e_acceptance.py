import pytest

from agents.graphs.flow_builder import FlowGraphBuilder
from domain.flows.validator import validate
from models.flows import FlowEdge, FlowNode, FlowSpec


@pytest.mark.asyncio
async def test_flow_e2e_acceptance_scenario():
    """
    Acceptance #1: ChatInput -> LLMModel -> ReActAgent -> ChatOutput
    Validates, builds LangGraph execution graph, and asserts valid topology.
    """
    nodes = [
        FlowNode(
            id="node_in",
            type="ChatInput",
            template_version=1,
            position={"x": 50, "y": 200},
            values={},
        ),
        FlowNode(
            id="node_llm",
            type="LLMModel",
            template_version=1,
            position={"x": 400, "y": 50},
            values={"model": "gpt-4o", "provider": "openai", "temperature": 0.7},
        ),
        FlowNode(
            id="node_agent",
            type="ReActAgent",
            template_version=1,
            position={"x": 400, "y": 200},
            values={"system_prompt": "You are a helpful assistant."},
        ),
        FlowNode(
            id="node_out",
            type="ChatOutput",
            template_version=1,
            position={"x": 800, "y": 200},
            values={},
        ),
    ]

    edges = [
        FlowEdge(
            id="e1",
            source="node_in",
            source_handle="message",
            target="node_agent",
            target_handle="message",
        ),
        FlowEdge(
            id="e2",
            source="node_agent",
            source_handle="message",
            target="node_out",
            target_handle="message",
        ),
        FlowEdge(
            id="e3",
            source="node_llm",
            source_handle="model",
            target="node_agent",
            target_handle="model",
        ),
    ]

    spec = FlowSpec(nodes=nodes, edges=edges)

    # 1. Validation
    validation_result = validate(spec)
    assert validation_result.valid, f"Validation failed: {validation_result.errors}"
    assert len(validation_result.errors) == 0

    # 2. Graph compilation
    builder = FlowGraphBuilder()
    compiled_graph = await builder.build(spec)
    assert compiled_graph is not None

    # 3. Verify graph nodes & topology
    graph_nodes = compiled_graph.get_graph().nodes
    assert "node_in" in graph_nodes
    assert "node_agent" in graph_nodes
    assert "node_out" in graph_nodes
