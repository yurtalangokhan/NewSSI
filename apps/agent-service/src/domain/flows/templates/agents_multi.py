"""Multi-agent execution component templates: Supervisor & PipelineStage.

Spec: .tmp/flow-canvas-design.md section 7.5.
Brief: .tmp/flow-canvas-task-37-brief.md & .tmp/flow-canvas-task-38-brief.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.flows.templates.core import (
    CATEGORY_AGENTS,
    _memory_in,
    _message_in,
    _message_out,
    _model_in,
    _tools_in,
)
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FieldType,
    InputField,
)

if TYPE_CHECKING:
    from domain.flows.registry import ComponentRegistry


def _supervisor() -> ComponentTemplate:
    return ComponentTemplate(
        type="Supervisor",
        category=CATEGORY_AGENTS,
        display_name="Supervisor",
        description="Delegates each request to the most suitable of several agents.",
        icon="SvgUserManage",
        kind=ComponentKind.EXECUTION,
        inputs={
            "supervisor_prompt": InputField(
                type=FieldType.PROMPT,
                display_name="Supervisor prompt",
                required=True,
                value="You are a team supervisor.",
            ),
            "sub_agents": InputField(
                type=FieldType.MULTISELECT,
                display_name="Sub-agents",
                required=True,
                options_source="agents.definitions",
            ),
        },
        handles=ComponentHandles(
            inputs=[_message_in()],
            outputs=[_message_out()],
        ),
    )


def _pipeline_stage() -> ComponentTemplate:
    return ComponentTemplate(
        type="PipelineStage",
        category=CATEGORY_AGENTS,
        display_name="Pipeline Stage",
        description="One labeled step in a sequential multi-agent pipeline.",
        icon="SvgWorkflow",
        kind=ComponentKind.EXECUTION,
        inputs={
            "name": InputField(
                type=FieldType.STR,
                display_name="Stage name",
                required=True,
                info="Labels this step in traces and the canvas; does not affect execution.",
            ),
            "system_prompt": InputField(
                type=FieldType.PROMPT,
                display_name="System prompt",
                required=True,
                value="",
            ),
        },
        handles=ComponentHandles(
            inputs=[_message_in(), _model_in(), _tools_in(), _memory_in()],
            outputs=[_message_out()],
        ),
    )


def register_multi_agent_templates(registry: ComponentRegistry) -> None:
    registry.register(_supervisor())
    registry.register(_pipeline_stage())
