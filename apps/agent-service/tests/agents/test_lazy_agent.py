"""Tests for the LazyLoadingAgent base class."""

from collections.abc import AsyncGenerator
from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage

from agents.lazy_agent import LazyLoadingAgent


class TestLazyLoadingAgent(LazyLoadingAgent):
    """Test implementation of LazyLoadingAgent."""

    def __init__(self):
        super().__init__()

    async def load(self) -> None:
        """Test load implementation."""
        self._loaded = True

    def _create_graph(self):
        """Test graph creation."""
        mock_graph = Mock()
        mock_graph.name = "test-graph"
        return mock_graph


class DummyStreamGraph:
    async def astream(self, input, config=None, **kwargs) -> AsyncGenerator[tuple[str, dict], None]:
        yield ("updates", {"model": {"messages": []}})


class TestLazyLoadingAgentBase:
    """Test the LazyLoadingAgent base class functionality."""

    def test_initialization(self):
        """Test that agent initializes correctly."""
        agent = TestLazyLoadingAgent()
        assert not agent._loaded
        assert agent._graph is None

    @pytest.mark.asyncio
    async def test_load(self):
        """Test that load works correctly."""
        agent = TestLazyLoadingAgent()
        await agent.load()
        assert agent._loaded

    def test_get_graph_before_load(self):
        """Test that get_graph raises error before load."""
        agent = TestLazyLoadingAgent()
        with pytest.raises(RuntimeError, match="Agent not loaded"):
            agent.get_graph()

    def test_get_graph_after_load(self):
        """Test that get_graph works after load."""
        agent = TestLazyLoadingAgent()
        agent._loaded = True
        agent._graph = Mock()

        graph = agent.get_graph()
        assert graph is not None

    def test_get_graph_no_graph_created(self):
        """Test that get_graph raises error if no graph was created."""
        agent = TestLazyLoadingAgent()
        agent._loaded = True
        agent._graph = None

        with pytest.raises(RuntimeError, match="Agent graph not created"):
            agent.get_graph()

    @pytest.mark.asyncio
    async def test_aget_state_history_delegates_to_the_underlying_graph(self):
        """CheckpointBranchService.find_fork_point (retry checkpoint
        forking) calls agent.aget_state_history — every LazyLoadingAgent
        subclass (ConfigurableMCPAgent, DynamicAgent, CommandAgent,
        GitHubMCPAgent, and the supervisor agents) must expose it via the
        same delegate-to-self._graph pattern aget_state already uses,
        or retry silently falls back to append-to-tip for all of them."""

        class DummyHistoryGraph:
            async def aget_state_history(self, config=None, **kwargs):
                yield "snapshot-1"
                yield "snapshot-2"

        agent = TestLazyLoadingAgent()
        agent._loaded = True
        agent._graph = DummyHistoryGraph()

        snapshots = [s async for s in agent.aget_state_history(config={})]

        assert snapshots == ["snapshot-1", "snapshot-2"]

    @pytest.mark.asyncio
    async def test_aget_state_history_ensures_the_agent_is_loaded_first(self):
        class DummyHistoryGraph:
            async def aget_state_history(self, config=None, **kwargs):
                yield "snapshot-1"

        agent = TestLazyLoadingAgent()
        agent._graph = DummyHistoryGraph()
        assert not agent._loaded

        snapshots = [s async for s in agent.aget_state_history(config={})]

        assert agent._loaded
        assert snapshots == ["snapshot-1"]

    @pytest.mark.asyncio
    async def test_aupdate_state_delegates_to_the_underlying_graph(self):
        """AgentHelpers._handle_input calls agent.aupdate_state to replace an
        edited message's content in place on a forked checkpoint — every
        LazyLoadingAgent subclass must expose it via the same
        delegate-to-self._graph pattern aget_state already uses, or editing
        a message sent to a custom agent raises AttributeError."""

        class DummyUpdateGraph:
            def __init__(self):
                self.seen_config = None
                self.seen_values = None

            async def aupdate_state(self, config, values, **kwargs):
                self.seen_config = config
                self.seen_values = values
                return {"configurable": {"checkpoint_id": "new-id"}}

        agent = TestLazyLoadingAgent()
        agent._loaded = True
        graph = DummyUpdateGraph()
        agent._graph = graph

        result = await agent.aupdate_state({"configurable": {}}, {"messages": ["x"]})

        assert result == {"configurable": {"checkpoint_id": "new-id"}}
        assert graph.seen_values == {"messages": ["x"]}

    @pytest.mark.asyncio
    async def test_aupdate_state_ensures_the_agent_is_loaded_first(self):
        class DummyUpdateGraph:
            async def aupdate_state(self, config, values, **kwargs):
                return {"configurable": {}}

        agent = TestLazyLoadingAgent()
        agent._graph = DummyUpdateGraph()
        assert not agent._loaded

        await agent.aupdate_state({"configurable": {}}, {"messages": []})

        assert agent._loaded

    def test_get_langgraph_store_uses_store_service(self):
        """Test that long-term memory resolves the global LangGraph store."""
        agent = TestLazyLoadingAgent()
        store = object()

        with patch(
            "service.LangGraphStoreService.get_langgraph_store",
            return_value=store,
        ):
            assert agent._get_langgraph_store() is store

    @pytest.mark.asyncio
    async def test_astream_emits_memory_recall_custom_event(self):
        """Test that lazy-agent streaming surfaces recalled memories to the UI."""
        agent = TestLazyLoadingAgent()
        agent._loaded = True
        agent._graph = DummyStreamGraph()

        with patch.object(agent, "_get_langgraph_store", return_value=object()):
            with patch(
                "agents.lazy_agent.recall_memories", return_value={"user_facts": ["User likes tea"]}
            ):
                events = [
                    item
                    async for item in agent.astream(
                        {"messages": []},
                        config={"configurable": {"long_term_memory": True, "user_id": "user-1"}},
                    )
                ]

        assert events[0] == (
            "custom",
            {
                "type": "long_term_memory_recall",
                "fact_count": 1,
                "memories": ["User likes tea"],
            },
        )

    def test_tag_output_with_recalled_memories_updates_message_metadata(self):
        """Test that recalled-memory metadata is attached for history reconstruction."""
        message = AIMessage(content="Hello")
        output = ("updates", {"model": {"messages": [message]}})

        result = TestLazyLoadingAgent._tag_output_with_recalled_memories(
            output,
            {"user_facts": ["User likes tea"]},
        )

        assert result[1]["model"]["messages"][-1].additional_kwargs["_ltm_recalled"] == 1

    def test_tag_output_with_recalled_memories_updates_subgraph_chunk_metadata(self):
        """Tagging should also work for 3-tuple chunks emitted with subgraphs=True."""
        message = AIMessage(content="Hello")
        output = (("graph", "node"), "updates", {"model": {"messages": [message]}})

        result = TestLazyLoadingAgent._tag_output_with_recalled_memories(
            output,
            {"user_facts": ["User likes tea"]},
        )

        assert result[2]["model"]["messages"][-1].additional_kwargs["_ltm_recalled"] == 1

    def test_mark_input_with_ltm_recalled_marks_latest_human_message(self):
        """The recalled count should be persisted on the latest user message as refresh fallback."""
        input_payload = {
            "messages": [
                {"type": "system", "content": "context"},
                {"type": "human", "content": "hello", "additional_kwargs": {}},
            ]
        }

        updated = TestLazyLoadingAgent._mark_input_with_ltm_recalled(input_payload, 3)
        assert updated["messages"][-1]["additional_kwargs"]["_ltm_recalled"] == 3
