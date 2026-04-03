"""Supervisor manager - coordinates multiple sub-agents."""

import logging
import os
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.pregel import Pregel
from langgraph_supervisor import create_supervisor

from agents.base.manager import AgentManager, SupervisorManager, TaskResult, DelegateRequest
from agents.perceptrons.mcp_perceptron import MCPPerceptron

logger = logging.getLogger(__name__)

DEFAULT_SUPERVISOR_PROMPT = """You are a team supervisor managing multiple specialized agents.
Your job is to analyze each user request and delegate to the most appropriate agent.

IMPORTANT RULES:
1. Always delegate tasks to the appropriate specialized agent - do NOT answer directly yourself.
2. If the user provides a URL or asks about web content, delegate to an agent with fetch_webpage tool.
3. If the user asks for fact-checking or verification, delegate to an agent with web_search tool.
4. After receiving results from agents, synthesize the information and provide a coherent response.
5. You can delegate to multiple agents if the task requires different expertise."""


class DynamicFlatSupervisor(SupervisorManager):
    """
    Dynamic flat supervisor that manages multiple named sub-agents.

    Configuration (via config):
        - supervisor_prompt: Custom system prompt
        - sub_agents: List of sub-agent definitions
        - mcp_server_url: MCP server URL for tools
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._default_graph: CompiledStateGraph | Pregel | None = None
        self._mcp_perceptron: MCPPerceptron | None = None

    @property
    def name(self) -> str:
        return "supervisor"

    @property
    def agent_type(self) -> str:
        return "manager"

    @property
    def manager_type(self) -> str:
        return "supervisor"

    @property
    def description(self) -> str:
        return "A dynamic supervisor that coordinates multiple agents working in parallel"

    async def load(self) -> None:
        """Create a default graph and load MCP tools."""
        if self._loaded:
            return

        # Load MCP tools
        mcp_url = self.get_config("mcp_server_url") or os.environ.get("MCP_SERVER_URL")
        if mcp_url:
            self._mcp_perceptron = MCPPerceptron(mcp_servers=[{"name": "mcp", "url": mcp_url}])
            await self._mcp_perceptron.load()

        # Create default graph
        sub_agents = self.get_config("sub_agents", [])
        if sub_agents:
            self._default_graph = self._create_supervisor_graph(sub_agents)
        else:
            self._default_graph = self._create_fallback_graph()

        self._loaded = True

    def _create_fallback_graph(self) -> CompiledStateGraph:
        """Create a minimal fallback graph."""
        from core import get_model, settings

        model = get_model(settings.DEFAULT_MODEL)

        agent = create_react_agent(
            model=model,
            tools=[],
            name="fallback-agent",
            prompt="You are a helpful assistant. MCP tools are not available.",
        )

        workflow = create_supervisor(
            [agent],
            model=model,
            prompt="You are a supervisor. Currently no sub-agents are configured.",
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        return workflow.compile()

    def _create_supervisor_graph(
        self,
        sub_agents_config: list[dict[str, Any]],
        supervisor_prompt: str | None = None,
        model_name: str | None = None,
    ) -> CompiledStateGraph | Pregel:
        """Create a supervisor graph with sub-agents."""
        from core import get_model, settings

        supervisor_model_name = model_name or self.get_config("model", settings.DEFAULT_MODEL)
        supervisor_model = get_model(supervisor_model_name)

        prompt = supervisor_prompt or self.get_config(
            "supervisor_prompt", DEFAULT_SUPERVISOR_PROMPT
        )

        agents_list = []
        agent_descriptions = []

        mcp_tools = self._mcp_perceptron._tools if self._mcp_perceptron else {}

        for agent_config in sub_agents_config:
            agent_name = agent_config.get("name", "agent")
            system_prompt = agent_config.get("system_prompt", "You are a helpful assistant.")
            mcp_tool_names = agent_config.get("mcp_tools", [])

            # Get agent-specific model
            agent_model_name = agent_config.get("model") or supervisor_model_name
            agent_model = get_model(agent_model_name)

            # Collect tools
            agent_tools = []
            for tool_name in mcp_tool_names:
                if tool_name in mcp_tools:
                    agent_tools.append(mcp_tools[tool_name])

            # Enhance system prompt
            tool_names_str = ", ".join(mcp_tool_names) if mcp_tool_names else "none"
            enhanced_prompt = f"""{system_prompt}

CRITICAL INSTRUCTIONS:
- You have access to these tools: {tool_names_str}
- You MUST use your tools to complete tasks."""

            # Create agent
            agent = create_react_agent(
                model=agent_model,
                tools=agent_tools,
                name=agent_name,
                prompt=SystemMessage(content=enhanced_prompt),
            )

            agents_list.append(agent)

            tool_list = ", ".join(mcp_tool_names) if mcp_tool_names else "no tools"
            agent_descriptions.append(
                f"- {agent_name}: {system_prompt[:80]}... (tools: {tool_list})"
            )

        # Enhance supervisor prompt
        enhanced_prompt = f"""{prompt}

Available agents and their capabilities:
{chr(10).join(agent_descriptions)}

Analyze the user's request and delegate to the most appropriate agent(s)."""

        workflow = create_supervisor(
            agents_list,
            model=supervisor_model,
            prompt=enhanced_prompt,
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        return workflow.compile()

    async def delegate(
        self,
        request: DelegateRequest,
        config: RunnableConfig | None = None,
    ) -> TaskResult:
        """Delegate task to sub-agent(s)."""
        await self.ensure_loaded()

        if not self._default_graph:
            return TaskResult(
                agent_name="",
                output=None,
                success=False,
                error="No graph loaded",
            )

        try:
            configurable = (config or {}).get("configurable", {})

            # Check for dynamic config
            sub_agents = configurable.get("sub_agents", [])

            if sub_agents:
                graph = self._create_supervisor_graph(sub_agents)
                result = await graph.ainvoke(
                    {"messages": [{"role": "user", "content": request.task}]}
                )
            else:
                result = await self._default_graph.ainvoke(
                    {"messages": [{"role": "user", "content": request.task}]}
                )

            return TaskResult(
                agent_name="supervisor",
                output=result,
                success=True,
            )
        except Exception as e:
            logger.error(f"Supervisor delegation error: {e}")
            return TaskResult(
                agent_name="supervisor",
                output=None,
                success=False,
                error=str(e),
            )

    async def create_team(self, agent_definitions: list[dict[str, Any]]) -> None:
        """Create team from definitions."""
        self.update_config({"sub_agents": agent_definitions})

    def get_graph(self) -> CompiledStateGraph | Pregel:
        """Get the supervisor graph."""
        if not self._loaded:
            raise RuntimeError("Supervisor not loaded")
        return self._default_graph


# Singleton for backward compatibility
_supervisor_instance: DynamicFlatSupervisor | None = None


def get_supervisor(config: dict[str, Any] | None = None) -> DynamicFlatSupervisor:
    """Get or create supervisor instance."""
    global _supervisor_instance
    if _supervisor_instance is None or config:
        _supervisor_instance = DynamicFlatSupervisor(config)
    return _supervisor_instance
