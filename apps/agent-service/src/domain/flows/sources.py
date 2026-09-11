"""Dynamic option sources referenced by component templates.

A template field declares `options_source` as a key from this set; Task 5's
resolvers turn each key into the calling user's real data. Keeping the keys in
one place lets the registry tests reject a template that names a source nobody
resolves.

See `.tmp/flow-canvas-design.md` section 4.2 for the backing call of each key.
"""

from __future__ import annotations

from typing import Final

from domain.flows.mcp_catalog import MCP_CATEGORY_OPTION_SOURCES

KNOWN_OPTIONS_SOURCES: Final[frozenset[str]] = frozenset(
    {
        # LLM providers and models
        "llm.providers",
        "llm.models",
        "ollama.models",
        # Knowledge
        "rag.collections",
        "rag.graph_collections",
        "rag.knowledge_selector",
        # Tools
        "mcp.tools_by_category",
        "mcp.providers",
        "mcp.external_tools",
        # MCP per-category tools — one key per built-in category (see mcp_catalog)
        *MCP_CATEGORY_OPTION_SOURCES,
        # Mail
        "mail.configs",
        # Composition
        "agents.definitions",
        # Run Flow targets: flow-backed definitions with a published spec
        "flows.published",
        # Datasources and web
        "datasources.list",
        "websearch.providers",
        "websearch.content_providers",
    }
)
