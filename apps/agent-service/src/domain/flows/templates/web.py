"""Web search and crawling component templates (P8 Task 46).

Spec: .tmp/flow-canvas-design.md section 7.6.
Brief: .tmp/flow-canvas-task-46-brief.md
"""

from __future__ import annotations

from domain.flows.registry import ComponentRegistry
from domain.flows.templates.core import apply_tool_mode
from models.flows import (
    ComponentHandles,
    ComponentKind,
    ComponentTemplate,
    FieldType,
    Handle,
    InputField,
    PortType,
)

CATEGORY_WEB = "web"

TEMPLATES: list[ComponentTemplate] = [
    ComponentTemplate(
        type="WebSearch",
        category=CATEGORY_WEB,
        display_name="Web Search",
        description="Search the web and return matching documents.",
        icon="SvgSearch",
        kind=ComponentKind.EXECUTION,
        inputs={
            "provider": InputField(
                type=FieldType.OPTIONS,
                display_name="Provider",
                required=False,
                advanced=True,
                options_source="websearch.providers",
                info="Search provider. Optional — defaults to built-in search.",
            ),
            "query": InputField(
                type=FieldType.STR,
                display_name="Query",
                required=False,
                info="Search query string. Can also be supplied via incoming query handle.",
            ),
            "max_results": InputField(
                type=FieldType.INT,
                display_name="Max Results",
                required=False,
                default=5,
                info="Maximum number of search results to return (default 5).",
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="query", types=[PortType.DATA, PortType.MESSAGE])],
            outputs=[Handle(name="results", types=[PortType.DOCUMENTS, PortType.DATA])],
        ),
    ),
    ComponentTemplate(
        type="FetchWebpage",
        category=CATEGORY_WEB,
        display_name="Fetch Webpage",
        description="Fetch and extract readable text from a single URL.",
        icon="SvgGlobe",
        kind=ComponentKind.EXECUTION,
        inputs={
            "url": InputField(
                type=FieldType.STR,
                display_name="URL",
                required=False,
                info="Webpage URL to fetch. Can also be supplied via incoming url handle.",
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="url", types=[PortType.DATA, PortType.MESSAGE])],
            outputs=[Handle(name="content", types=[PortType.DATA, PortType.MESSAGE])],
        ),
    ),
    ComponentTemplate(
        type="ContentCrawl",
        category=CATEGORY_WEB,
        display_name="Content Crawl",
        description="Fetch and extract structured content from multiple URLs (newline-separated).",
        icon="SvgFileText",
        kind=ComponentKind.EXECUTION,
        inputs={
            "urls": InputField(
                type=FieldType.STR,
                display_name="URLs",
                required=False,
                multiline=True,
                info="Newline-separated list of webpage URLs to fetch. Can also be supplied via incoming urls handle.",
            ),
            "provider": InputField(
                type=FieldType.OPTIONS,
                display_name="Provider",
                required=True,
                options_source="websearch.content_providers",
                info="Content crawler provider.",
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="urls", types=[PortType.DATA, PortType.MESSAGE])],
            outputs=[Handle(name="documents", types=[PortType.DOCUMENTS, PortType.DATA])],
        ),
    ),
]


def register_web_templates(registry: ComponentRegistry) -> None:
    """Register web search and crawl templates."""
    for t in TEMPLATES:
        registry.register(apply_tool_mode(t))
