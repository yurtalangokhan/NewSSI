"""Datasource component templates (P8 Task 47).

Spec: .tmp/flow-canvas-design.md section 7.6.
Brief: .tmp/flow-canvas-task-47-brief.md
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

CATEGORY_DATASOURCES = "datasources"

TEMPLATES: list[ComponentTemplate] = [
    ComponentTemplate(
        type="AirbyteDatasource",
        category=CATEGORY_DATASOURCES,
        display_name="Airbyte Datasource",
        description="Reference an existing Airbyte datasource configuration.",
        icon="SvgHardDrive",
        kind=ComponentKind.RESOURCE,
        inputs={
            "datasource_id": InputField(
                type=FieldType.OPTIONS,
                display_name="Datasource",
                required=True,
                options_source="datasources.list",
                info="Configured data source to reference.",
            ),
        },
        handles=ComponentHandles(
            inputs=[],
            outputs=[Handle(name="data", types=[PortType.DATA])],
        ),
    ),
    ComponentTemplate(
        type="SyncTrigger",
        category=CATEGORY_DATASOURCES,
        display_name="Sync Trigger",
        description="Trigger synchronization for a configured datasource.",
        icon="SvgRefreshCw",
        kind=ComponentKind.EXECUTION,
        inputs={
            "datasource_id": InputField(
                type=FieldType.OPTIONS,
                display_name="Datasource",
                required=True,
                options_source="datasources.list",
                info="Data source to trigger synchronization for.",
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="trigger", types=[PortType.TRIGGER])],
            outputs=[Handle(name="result", types=[PortType.DATA])],
        ),
    ),
]


def register_datasource_templates(registry: ComponentRegistry) -> None:
    """Register datasource templates."""
    for t in TEMPLATES:
        registry.register(t)
