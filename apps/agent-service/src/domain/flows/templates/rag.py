"""Vector RAG and Graph RAG component templates.

Spec: .tmp/flow-canvas-design.md sections 7.1, 7.2.
Briefs: .tmp/flow-canvas-task-32-brief.md, .tmp/flow-canvas-task-33-brief.md
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

CATEGORY_KNOWLEDGE = "knowledge"

RAG_TEMPLATES: list[ComponentTemplate] = [
    # Vector RAG & Knowledge Base
    ComponentTemplate(
        type="KnowledgeBase",
        category=CATEGORY_KNOWLEDGE,
        display_name="Knowledge Base",
        description="Connect and retrieve documents from a knowledge base collection.",
        icon="SvgBookOpen",
        kind=ComponentKind.EXECUTION,
        inputs={
            "collection": InputField(
                type=FieldType.OPTIONS,
                display_name="Knowledge Base",
                required=True,
                options_source="rag.collections",
                info="Knowledge base collection to query.",
            ),
            "query": InputField(
                type=FieldType.STR,
                display_name="Query",
                required=False,
                info="Search query string. Can also be supplied via incoming query handle.",
            ),
            "top_k": InputField(
                type=FieldType.INT,
                display_name="Top K",
                required=False,
                default=4,
                info="Number of relevant chunks to retrieve (default 4).",
            ),
            "threshold": InputField(
                type=FieldType.FLOAT,
                display_name="Score threshold",
                required=False,
                default=0.7,
                info="Minimum similarity score threshold (0.0 to 1.0).",
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="query", types=[PortType.DATA, PortType.MESSAGE])],
            outputs=[
                Handle(name="documents", types=[PortType.DOCUMENTS, PortType.DATA]),
                Handle(name="context", types=[PortType.DATA, PortType.MESSAGE]),
            ],
        ),
    ),
    ComponentTemplate(
        type="DocumentSearch",
        category=CATEGORY_KNOWLEDGE,
        display_name="Document Search",
        description="Search knowledge collections for relevant documents.",
        icon="SvgSearch",
        kind=ComponentKind.EXECUTION,
        inputs={
            "collection": InputField(
                type=FieldType.OPTIONS,
                display_name="Collection",
                required=True,
                options_source="rag.collections",
            ),
            "query": InputField(
                type=FieldType.STR,
                display_name="Query",
                required=False,
                info="Search query string. Can also be supplied via incoming query handle.",
            ),
            "top_k": InputField(
                type=FieldType.INT,
                display_name="Top K",
                required=False,
                default=4,
            ),
            "threshold": InputField(
                type=FieldType.FLOAT,
                display_name="Score threshold",
                required=False,
                default=0.7,
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="query", types=[PortType.DATA, PortType.MESSAGE])],
            outputs=[Handle(name="documents", types=[PortType.DOCUMENTS, PortType.DATA])],
        ),
    ),
    ComponentTemplate(
        type="DocumentContext",
        category=CATEGORY_KNOWLEDGE,
        display_name="Document Context",
        description="Format retrieved document chunks as formatted context for prompts.",
        icon="SvgBookOpen",
        kind=ComponentKind.EXECUTION,
        inputs={
            "template": InputField(
                type=FieldType.PROMPT,
                display_name="Context template",
                required=False,
                default="Context:\n{context}\n\nQuery: {query}",
            ),
        },
        handles=ComponentHandles(
            inputs=[
                Handle(name="documents", types=[PortType.DOCUMENTS, PortType.DATA]),
                Handle(name="query", types=[PortType.DATA, PortType.MESSAGE]),
            ],
            outputs=[
                Handle(name="context", types=[PortType.DATA, PortType.MESSAGE]),
            ],
        ),
    ),
    # Graph RAG (Task 33)
    ComponentTemplate(
        type="GraphSearch",
        category=CATEGORY_KNOWLEDGE,
        display_name="Graph Search",
        description="Hybrid semantic search over graph entities and relations.",
        icon="SvgNetworkGraph",
        kind=ComponentKind.EXECUTION,
        inputs={
            "collection": InputField(
                type=FieldType.OPTIONS,
                display_name="Graph collection",
                required=True,
                options_source="rag.graph_collections",
            ),
            "limit": InputField(
                type=FieldType.INT,
                display_name="Limit",
                required=False,
                default=10,
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="query", types=[PortType.DATA, PortType.MESSAGE])],
            outputs=[Handle(name="graph_data", types=[PortType.DOCUMENTS, PortType.DATA])],
        ),
    ),
    ComponentTemplate(
        type="GraphEntitySearch",
        category=CATEGORY_KNOWLEDGE,
        display_name="Graph Entity Search",
        description="Find specific entities in a knowledge graph by name or type.",
        icon="SvgLinkedDots",
        kind=ComponentKind.EXECUTION,
        inputs={
            "collection": InputField(
                type=FieldType.OPTIONS,
                display_name="Graph collection",
                required=True,
                options_source="rag.graph_collections",
            ),
            "entity_type": InputField(
                type=FieldType.STR,
                display_name="Entity type",
                required=False,
            ),
            "limit": InputField(
                type=FieldType.INT,
                display_name="Limit",
                required=False,
                default=10,
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="query", types=[PortType.DATA, PortType.MESSAGE])],
            outputs=[Handle(name="entities", types=[PortType.DOCUMENTS, PortType.DATA])],
        ),
    ),
    ComponentTemplate(
        type="GraphNeighborhood",
        category=CATEGORY_KNOWLEDGE,
        display_name="Graph Neighborhood",
        description="Explore the connected neighborhood of graph entities.",
        icon="SvgBranch",
        kind=ComponentKind.EXECUTION,
        inputs={
            "collection": InputField(
                type=FieldType.OPTIONS,
                display_name="Graph collection",
                required=True,
                options_source="rag.graph_collections",
            ),
            "depth": InputField(
                type=FieldType.INT,
                display_name="Depth",
                required=False,
                default=1,
            ),
            "limit": InputField(
                type=FieldType.INT,
                display_name="Limit",
                required=False,
                default=20,
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="entity_id", types=[PortType.DATA, PortType.MESSAGE])],
            outputs=[Handle(name="subgraph", types=[PortType.DOCUMENTS, PortType.DATA])],
        ),
    ),
    ComponentTemplate(
        type="GraphStats",
        category=CATEGORY_KNOWLEDGE,
        display_name="Graph Stats",
        description="Retrieve summary statistics and schema of a knowledge graph.",
        icon="SvgBarChart",
        kind=ComponentKind.EXECUTION,
        inputs={
            "collection": InputField(
                type=FieldType.OPTIONS,
                display_name="Graph collection",
                required=True,
                options_source="rag.graph_collections",
            ),
        },
        handles=ComponentHandles(
            inputs=[Handle(name="input", types=[PortType.DATA, PortType.MESSAGE])],
            outputs=[Handle(name="stats", types=[PortType.DATA])],
        ),
    ),
]


def register_rag_templates(registry: ComponentRegistry) -> None:
    for template in RAG_TEMPLATES:
        registry.register(apply_tool_mode(template))
