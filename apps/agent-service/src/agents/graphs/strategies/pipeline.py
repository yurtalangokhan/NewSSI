"""Pipeline graph schema strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from agents.graphs.schemas import GraphSchemaType
from agents.graphs.strategies.base import GraphSchemaStrategy
from core.logger import get_logger

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.pregel import Pregel

logger = get_logger(__name__)


class PipelineGraphStrategy(GraphSchemaStrategy):
    """
    Strategy for pipeline - sequential stage execution.

    Pipeline stages execute in deterministic order based on their position
    in the stages list. The graph encodes this order in the supervisor prompt
    and agent handoff order.
    """

    schema_type = GraphSchemaType.PIPELINE

    def validate(self, config: dict[str, Any]) -> tuple[str, ...]:
        """
        Validate pipeline configuration.

        Pipeline requires stages to be a non-empty list.
        Stage order is preserved - validation doesn't change order.
        """
        errors: list[str] = []

        stages = config.get("stages", [])
        if stages is None:
            errors.append("pipeline: stages is required")
        elif not isinstance(stages, list):
            errors.append("pipeline: stages must be a list")
        elif len(stages) == 0:
            errors.append("pipeline: stages list cannot be empty")

        # Validate each stage has required fields
        if isinstance(stages, list):
            for i, stage in enumerate(stages):
                if not isinstance(stage, dict):
                    errors.append(f"pipeline: stage[{i}] must be a dict")
                    continue
                if "name" not in stage:
                    errors.append(f"pipeline: stage[{i}] missing required 'name' field")

        return tuple(errors)

    async def build(self, config: dict[str, Any]) -> CompiledStateGraph | Pregel:
        """
        Build pipeline graph with sequential stages.

        Stage order is deterministic - stages are processed in the order they
        appear in the stages list. This order is encoded in the supervisor
        prompt and the agent list order passed to create_supervisor.
        """
        from langgraph_supervisor import create_supervisor

        model = self._get_model(config.get("model"))
        pipeline_prompt = config.get("pipeline_prompt", "Process through all stages sequentially.")

        stages_config = config.get("stages", [])
        if not stages_config:
            logger.warning("No stages configured for pipeline, using fallback")
            fallback_agent = create_react_agent(
                model=model,
                tools=[],
                name="fallback",
                prompt="You are a helpful assistant.",
            )
            workflow = create_supervisor(
                [fallback_agent],
                model=model,
                prompt="No stages configured.",
                add_handoff_back_messages=True,
                output_mode="full_history",
            )
            return workflow.compile(checkpointer=self.checkpointer)

        agents_list = []
        stage_names = []

        # Process stages in order - this guarantees deterministic execution order
        for stage_cfg in stages_config:
            if not isinstance(stage_cfg, dict):
                continue

            name = stage_cfg.get("name", "stage")
            if config.get("user_id") and not stage_cfg.get("user_id"):
                stage_cfg["user_id"] = config["user_id"]
            if config.get("mail_attachments") and not stage_cfg.get("mail_attachments"):
                stage_cfg["mail_attachments"] = config["mail_attachments"]
            agent = self._build_sub_agent_graph(stage_cfg)

            agents_list.append(agent)
            stage_names.append(name)

        # Encode deterministic stage order in the supervisor prompt
        # Stages are listed in order they appear in the config
        enhanced_prompt = (
            f"{pipeline_prompt}\n\nYou are a sequential pipeline."
            f" Process input through each stage in order.\nStages in order: {stage_names}"
        )

        workflow = create_supervisor(
            agents_list,
            model=model,
            prompt=enhanced_prompt,
            add_handoff_back_messages=True,
            output_mode="full_history",
        )

        return workflow.compile(checkpointer=self.checkpointer, name=config.get("name"))

    def _build_sub_agent_graph(self, agent_config: dict[str, Any]) -> CompiledStateGraph | Pregel:
        """Build a sub-agent graph for a pipeline stage."""
        from langgraph.prebuilt import create_react_agent

        from agents.graphs.schemas import GraphSchemaType
        from agents.mail_tooling import append_email_tool_policy

        schema_value = agent_config.get("graph_schema")
        try:
            schema_type = GraphSchemaType(schema_value) if schema_value else GraphSchemaType.REACT
        except ValueError:
            schema_type = GraphSchemaType.REACT

        # Recursively handle nested supervisor/pipeline
        if schema_type in (GraphSchemaType.SUPERVISOR, GraphSchemaType.PIPELINE):
            from agents.graphs.strategies.pipeline import PipelineGraphStrategy
            from agents.graphs.strategies.supervisor import SupervisorGraphStrategy

            nested_strategy_class = (
                SupervisorGraphStrategy
                if schema_type == GraphSchemaType.SUPERVISOR
                else PipelineGraphStrategy
            )
            nested_strategy = nested_strategy_class(
                model=self._get_model(agent_config.get("model")),
                system_prompt=agent_config.get("system_prompt", self.system_prompt),
                tools=self.tools,
                mcp_tools_map=self.mcp_tools_map,
                memory_enabled=self.memory_enabled,
                checkpointer=self.checkpointer,
                repository=self.repository,
            )
            return nested_strategy.build(agent_config)

        name = agent_config.get("name", "agent")
        tool_names = agent_config.get("mcp_tools", [])
        system_prompt = append_email_tool_policy(
            agent_config.get("system_prompt", "You are a helpful agent."),
            tool_names,
            mail_attachments=agent_config.get("mail_attachments"),
        )
        agent_model = self._get_model(agent_config.get("model"))
        agent_tools = self._get_tools_for_names(
            tool_names,
            tool_configs=agent_config.get("mcp_tool_configs") or {},
            user_id=agent_config.get("user_id"),
            mail_attachments=agent_config.get("mail_attachments"),
        )

        agent_tools, system_prompt = self._apply_document_tools(agent_tools, system_prompt)

        return create_react_agent(
            model=agent_model,
            tools=agent_tools,
            name=name,
            prompt=SystemMessage(content=system_prompt),
        )
