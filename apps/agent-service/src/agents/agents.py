from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from agent_composition.application.compose_agent import AgentFactory
from agent_composition.application.recipes import get_builtin_recipe
from agents.chatbot import chatbot
from agents.configurable_mcp_agent import configurable_mcp_agent
from agents.lazy_agent import LazyLoadingAgent
from core.logger import get_logger
from models.agents import AgentInfo

logger = get_logger(__name__)

DEFAULT_AGENT = "chatbot"

# Type alias to handle LangGraph's different agent patterns
AgentGraph = CompiledStateGraph | Pregel
AgentGraphLike = CompiledStateGraph | Pregel | LazyLoadingAgent


@dataclass
class Agent:
    description: str
    graph_like: AgentGraphLike


agents: dict[str, Agent] = {
    "chatbot": Agent(
        description="A simple chatbot that uses the default model.",
        graph_like=chatbot,
    ),
    "configurable-mcp-agent": Agent(
        description="A configurable agent with custom system prompt and MCP tool selection.",
        graph_like=configurable_mcp_agent,
    ),
}


async def load_agent(agent_id: str) -> None:
    """Load lazy agents if needed.

    Built-in agents that are defined only as recipes (e.g. ``pipeline``,
    ``supervisor``) are composed through ``AgentFactory.create`` so they share the
    exact construction path used by persisted dynamic agents. Keys that still
    live in the legacy static registry (``chatbot``, ``configurable-mcp-agent``)
    are served from that registry to preserve backward compatibility.
    """
    # Already in the static registry: use the existing (backward-compatible) path.
    if agent_id in agents:
        graph_like = agents[agent_id].graph_like
        if isinstance(graph_like, LazyLoadingAgent):
            await graph_like.load()
        return

    # Recipe-only built-in: compose through the canonical factory.
    recipe = get_builtin_recipe(agent_id)
    if recipe is None:
        raise KeyError(f"Agent '{agent_id}' not found")

    agent = await AgentFactory.create(recipe)
    agents[agent_id] = Agent(
        description=recipe.get("description", f"Built-in agent: {agent_id}"),
        graph_like=agent,
    )


def get_agent(agent_id: str) -> AgentGraph:
    """Get an agent graph, loading lazy agents if needed."""
    if agent_id not in agents:
        recipe = get_builtin_recipe(agent_id)
        if recipe is None:
            raise KeyError(f"Agent '{agent_id}' not found")
        raise RuntimeError(f"Agent {agent_id} not loaded. Call load() first.")

    agent_graph = agents[agent_id].graph_like

    # If it's a lazy loading agent, ensure it's loaded and return its graph
    if isinstance(agent_graph, LazyLoadingAgent):
        if not agent_graph._loaded:
            raise RuntimeError(f"Agent {agent_id} not loaded. Call load() first.")
        return agent_graph.get_graph()

    # Otherwise return the graph directly
    return agent_graph


def get_agent_or_lazy(agent_id: str) -> AgentGraphLike:
    """
    Get an agent - returns LazyLoadingAgent instance if applicable.
    This allows the caller to use ainvoke/astream_events with runtime config.
    """
    if agent_id not in agents:
        recipe = get_builtin_recipe(agent_id)
        if recipe is None:
            raise KeyError(f"Agent '{agent_id}' not found")
        raise RuntimeError(f"Agent {agent_id} not loaded. Call load() first.")

    agent_graph = agents[agent_id].graph_like

    # If it's a lazy loading agent, return the instance (not the graph)
    if isinstance(agent_graph, LazyLoadingAgent):
        if not agent_graph._loaded:
            raise RuntimeError(f"Agent {agent_id} not loaded. Call load() first.")
        return agent_graph

    # Otherwise return the graph directly
    return agent_graph


def get_all_agent_info() -> list[AgentInfo]:
    # The static registry remains the source of truth for the public agent
    # catalog (preserving the existing two built-in entries and their persona
    # ordering). Recipe-only built-ins are resolved on demand via load_agent and
    # are intentionally not enumerated here to avoid changing persona counts.
    return [
        AgentInfo(key=agent_id, description=agent.description) for agent_id, agent in agents.items()
    ]
