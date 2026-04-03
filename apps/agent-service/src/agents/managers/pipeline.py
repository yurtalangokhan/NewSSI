"""Pipeline manager - sequential stage execution."""

import logging
import os
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.pregel import Pregel
from langgraph_supervisor import create_supervisor

from agents.base.manager import AgentManager, PipelineManager, TaskResult, DelegateRequest
from agents.perceptrons.mcp_perceptron import MCPPerceptron

logger = logging.getLogger(__name__)

DEFAULT_STAGE_PROMPTS = {
    "enricher": "You are a project enricher. Analyze the input and expand it with more details.",
    "implementer": "You are a code implementer. Take the enriched spec and create the implementation.",
    "documenter": "You are a technical writer. Create comprehensive documentation.",
    "deployer": "You are a deployment specialist. Prepare and deploy the project.",
}


class DynamicPipelineSupervisor(PipelineManager):
    """
    Dynamic pipeline supervisor that executes stages sequentially.

    Configuration (via config):
        - pipeline_stages: List of stage configurations
        - retry_count: Number of retries on stage failure
        - on_error: Error handling strategy ('abort' or 'skip')
        - mcp_server_url: MCP server URL
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self._default_graph: CompiledStateGraph | Pregel | None = None
        self._mcp_perceptron: MCPPerceptron | None = None
        self._graph_cache: dict[str, CompiledStateGraph | Pregel] = {}

    @property
    def name(self) -> str:
        return "pipeline"

    @property
    def agent_type(self) -> str:
        return "manager"

    @property
    def manager_type(self) -> str:
        return "pipeline"

    @property
    def description(self) -> str:
        return "A dynamic pipeline supervisor that executes stages sequentially"

    async def load(self) -> None:
        """Create a default graph and load MCP tools."""
        if self._loaded:
            return

        # Load MCP tools
        mcp_url = self.get_config("mcp_server_url") or os.environ.get("MCP_SERVER_URL")
        if mcp_url:
            self._mcp_perceptron = MCPPerceptron([{"name": "mcp", "url": mcp_url}])
            await self._mcp_perceptron.load()

        # Create default graph
        stages = self.get_config("stages", [])
        if stages:
            self._default_graph = self._create_pipeline_graph(stages)
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
            name="fallback",
            prompt="You are a helpful assistant.",
        )

        workflow = create_supervisor(
            [agent],
            model=model,
            prompt="You are a pipeline. No stages configured.",
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        return workflow.compile()

    def _create_pipeline_graph(
        self,
        stages_config: list[dict[str, Any]],
    ) -> CompiledStateGraph | Pregel:
        """Create a pipeline graph with stages."""
        from core import get_model, settings

        model_name = self.get_config("model", settings.DEFAULT_MODEL)
        model = get_model(model_name)

        mcp_tools = self._mcp_perceptron._tools if self._mcp_perceptron else {}

        agents_list = []

        for stage_config in stages_config:
            stage_name = stage_config.get("name", "stage")
            system_prompt = stage_config.get("system_prompt", "You are a helpful assistant.")
            mcp_tool_names = stage_config.get("mcp_tools", [])

            # Get tools
            stage_tools = [mcp_tools[t] for t in mcp_tool_names if t in mcp_tools]

            agent = create_react_agent(
                model=model,
                tools=stage_tools,
                name=stage_name,
                prompt=SystemMessage(content=system_prompt),
            )

            agents_list.append(agent)

        # Create supervisor with agents as sequential pipeline
        workflow = create_supervisor(
            agents_list,
            model=model,
            prompt="You are a sequential pipeline. Process tasks through each stage in order.",
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        return workflow.compile()

    async def delegate(
        self,
        request: DelegateRequest,
        config: RunnableConfig | None = None,
    ) -> TaskResult:
        """Execute task through pipeline."""
        await self.ensure_loaded()

        if not self._default_graph:
            return TaskResult(
                agent_name="pipeline",
                output=None,
                success=False,
                error="No graph loaded",
            )

        try:
            result = await self._default_graph.ainvoke(
                {"messages": [{"role": "user", "content": request.task}]}
            )

            return TaskResult(
                agent_name="pipeline",
                output=result,
                success=True,
            )
        except Exception as e:
            logger.error(f"Pipeline execution error: {e}")
            return TaskResult(
                agent_name="pipeline",
                output=None,
                success=False,
                error=str(e),
            )

    async def create_team(self, agent_definitions: list[dict[str, Any]]) -> None:
        """Create pipeline stages from definitions."""
        self.update_config({"stages": agent_definitions})


# Singleton for backward compatibility
_pipeline_instance: DynamicPipelineSupervisor | None = None


def get_pipeline(config: dict[str, Any] | None = None) -> DynamicPipelineSupervisor:
    """Get or create pipeline instance."""
    global _pipeline_instance
    if _pipeline_instance is None or config:
        _pipeline_instance = DynamicPipelineSupervisor(config)
    return _pipeline_instance
