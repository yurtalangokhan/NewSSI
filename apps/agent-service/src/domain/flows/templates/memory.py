"""Memory resource templates and AgentRef template.

Spec: .tmp/flow-canvas-design.md section 7.5.
Brief: .tmp/flow-canvas-task-35-brief.md
"""

from __future__ import annotations

from domain.flows.registry import ComponentRegistry
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FieldType,
    Handle,
    InputField,
    PortType,
)

CATEGORY_MEMORY = "memory"
CATEGORY_AGENTS = "agents"

MEMORY_TEMPLATES: list[ComponentTemplate] = [
    ComponentTemplate(
        type="LongTermMemory",
        category=CATEGORY_MEMORY,
        display_name="Long-Term Memory",
        description="Recalls facts the platform has learned about this user.",
        icon="SvgBooksStackSmall",
        kind=ComponentKind.RESOURCE,
        handles=ComponentHandles(
            outputs=[Handle(name="memory", types=[PortType.MEMORY])],
        ),
    ),
    ComponentTemplate(
        type="ThreadCheckpointer",
        category=CATEGORY_MEMORY,
        display_name="Thread Checkpointer",
        description="Every flow is thread-persistent by default; this node shows that on the canvas.",
        icon="SvgHardDrive",
        kind=ComponentKind.RESOURCE,
        handles=ComponentHandles(
            outputs=[Handle(name="checkpointer", types=[PortType.DATA])],
        ),
    ),
    ComponentTemplate(
        type="AgentRef",
        category=CATEGORY_AGENTS,
        display_name="Agent Reference",
        description="Embeds an existing classic agent, unmodified, as a step in this flow.",
        icon="SvgUsers",
        kind=ComponentKind.EXECUTION,
        inputs={
            "agent_id": InputField(
                type=FieldType.OPTIONS,
                display_name="Agent",
                required=True,
                options_source="agents.definitions",
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="input", types=[PortType.MESSAGE])],
            outputs=[Handle(name="output", types=[PortType.MESSAGE])],
        ),
    ),
]


def register_memory_templates(registry: ComponentRegistry) -> None:
    for template in MEMORY_TEMPLATES:
        registry.register(template)
