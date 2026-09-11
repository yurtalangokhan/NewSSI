"""MCP category and provider component templates.

Each category exposes an enabled tools multiselect field mapped to its
respective mcp.tools.{category} options source.

Spec: .tmp/flow-canvas-design.md section 7.3.
Briefs: .tmp/flow-canvas-task-29-brief.md, .tmp/flow-canvas-task-30-brief.md
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

CATEGORY_TOOLS = "tools"


def _make_category_template(
    *,
    type_name: str,
    display_name: str,
    description: str,
    icon: str,
    category_key: str,
) -> ComponentTemplate:
    return ComponentTemplate(
        type=type_name,
        category=CATEGORY_TOOLS,
        display_name=display_name,
        description=description,
        icon=icon,
        kind=ComponentKind.RESOURCE,
        inputs={
            "tools": InputField(
                type=FieldType.MULTISELECT,
                display_name="Enabled tools",
                required=True,
                options_source=f"mcp.tools.{category_key}",
            ),
        },
        handles=ComponentHandles(
            outputs=[Handle(name="tools", types=[PortType.TOOLS])],
        ),
    )


MCP_TEMPLATES: list[ComponentTemplate] = [
    _make_category_template(
        type_name="CalculatorTools",
        display_name="Calculator Tools",
        description="Mathematical calculations and expression evaluation.",
        icon="SvgHash",
        category_key="calculator",
    ),
    _make_category_template(
        type_name="CodeTools",
        display_name="Code Tools",
        description="Execute and inspect code snippets in various languages.",
        icon="SvgCode",
        category_key="code",
    ),
    _make_category_template(
        type_name="CommandTools",
        display_name="Command Tools",
        description="Execute system commands and shell operations.",
        icon="SvgTerminal",
        category_key="command",
    ),
    _make_category_template(
        type_name="DockerTools",
        display_name="Docker Tools",
        description="Manage Docker containers, images, and volumes.",
        icon="SvgCloud",
        category_key="docker",
    ),
    _make_category_template(
        type_name="FileTools",
        display_name="File Tools",
        description="Read, write, and manipulate local filesystem files.",
        icon="SvgFiles",
        category_key="file",
    ),
    _make_category_template(
        type_name="GitTools",
        display_name="Git Tools",
        description="Clone, commit, push, and inspect Git repositories.",
        icon="SvgBranch",
        category_key="git",
    ),
    _make_category_template(
        type_name="JavaTools",
        display_name="Java Tools",
        description="Java development tools and runtime inspection.",
        icon="SvgCode",
        category_key="java",
    ),
    _make_category_template(
        type_name="JsonTools",
        display_name="JSON Tools",
        description="Parse, validate, and manipulate JSON data.",
        icon="SvgFileBraces",
        category_key="json",
    ),
    _make_category_template(
        type_name="PdfTools",
        display_name="PDF Tools",
        description="Extract text, metadata, and analyze PDF documents.",
        icon="SvgFileText",
        category_key="pdf",
    ),
    _make_category_template(
        type_name="ServiceTools",
        display_name="Service Tools",
        description="Inspect and interact with system services.",
        icon="SvgServer",
        category_key="service",
    ),
    _make_category_template(
        type_name="TextTools",
        display_name="Text Tools",
        description="Text processing, formatting, and string transformations.",
        icon="SvgTextLines",
        category_key="text",
    ),
    _make_category_template(
        type_name="TimeTools",
        display_name="Time Tools",
        description="Time, date, and scheduling utility functions.",
        icon="SvgClock",
        category_key="time",
    ),
    _make_category_template(
        type_name="UtilityTools",
        display_name="Utility Tools",
        description="General utility tools and helper functions.",
        icon="SvgSliders",
        category_key="utility",
    ),
    _make_category_template(
        type_name="WebTools",
        display_name="Web Tools",
        description="Fetch web pages, scrape content, and search the web.",
        icon="SvgGlobe",
        category_key="web",
    ),
    # Task 30 templates:
    ComponentTemplate(
        type="MailTools",
        category=CATEGORY_TOOLS,
        display_name="Mail Tools",
        description="Read, search, draft, and send emails.",
        icon="SvgBubbleText",
        kind=ComponentKind.RESOURCE,
        inputs={
            "tools": InputField(
                type=FieldType.MULTISELECT,
                display_name="Enabled tools",
                required=True,
                options_source="mcp.tools.mail",
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="mail_config", types=[PortType.DATA])],
            outputs=[Handle(name="tools", types=[PortType.TOOLS])],
        ),
    ),
    ComponentTemplate(
        type="MailConfig",
        category=CATEGORY_TOOLS,
        display_name="Mail Config",
        description="Configure email sending identity and SMTP connection.",
        icon="SvgServer",
        kind=ComponentKind.RESOURCE,
        inputs={
            "config_id": InputField(
                type=FieldType.OPTIONS,
                display_name="Mail configuration",
                required=True,
                options_source="mail.configs",
            ),
        },
        handles=ComponentHandles(
            outputs=[Handle(name="data", types=[PortType.DATA])],
        ),
    ),
    ComponentTemplate(
        type="ExternalMCPServer",
        category=CATEGORY_TOOLS,
        display_name="External MCP Server",
        description="Bind a tenant-registered external MCP provider.",
        icon="SvgMcp",
        kind=ComponentKind.RESOURCE,
        inputs={
            "provider": InputField(
                type=FieldType.OPTIONS,
                display_name="Provider",
                required=True,
                options_source="mcp.providers",
            ),
            "tools": InputField(
                type=FieldType.MULTISELECT,
                display_name="Enabled tools",
                required=False,
                options_source="mcp.external_tools",
                info="Only the tools selected here are bound to the agent. "
                "Leave empty to bind none.",
            ),
        },
        handles=ComponentHandles(
            outputs=[Handle(name="tools", types=[PortType.TOOLS])],
        ),
    ),
]


def register_mcp_templates(registry: ComponentRegistry) -> None:
    for template in MCP_TEMPLATES:
        registry.register(template)
