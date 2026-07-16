from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

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
    """Load lazy agents if needed."""
    graph_like = agents[agent_id].graph_like
    if isinstance(graph_like, LazyLoadingAgent):
        await graph_like.load()


def get_agent(agent_id: str) -> AgentGraph:
    """Get an agent graph, loading lazy agents if needed."""
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
        raise KeyError(f"Agent {agent_id} not found")

    agent_graph = agents[agent_id].graph_like

    # If it's a lazy loading agent, return the instance (not the graph)
    if isinstance(agent_graph, LazyLoadingAgent):
        if not agent_graph._loaded:
            raise RuntimeError(f"Agent {agent_id} not loaded. Call load() first.")
        return agent_graph

    # Otherwise return the graph directly
    return agent_graph


def get_all_agent_info() -> list[AgentInfo]:
    return [
        AgentInfo(key=agent_id, description=agent.description) for agent_id, agent in agents.items()
    ]
