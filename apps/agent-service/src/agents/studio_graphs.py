"""LangGraph Studio entrypoints built from built-in recipes.

These replace the monolithic legacy agent modules (``research_assistant``,
``rag_assistant``, ``graph_rag_assistant``) so Studio no longer imports them.
Each entrypoint is a callable that builds and returns a compiled graph from a
recipe config using ``GraphBuilder``. Building is deferred until Studio requests
the graph, which avoids constructing LLM models at import time.
"""

from __future__ import annotations

from typing import Any

from agents.graphs.builder import GraphBuilder


def _build(recipe: dict[str, Any]) -> Any:
    """Build a compiled graph for a recipe config via the strategy registry."""
    schema = recipe.get("graph_schema", "zero_shot")
    builder = GraphBuilder(
        system_prompt=recipe.get("system_prompt", "You are a helpful AI assistant."),
        memory_enabled=recipe.get("memory_type") == "long_term",
    )
    return builder.build(schema, recipe)


def chatbot() -> Any:
    """Built-in chatbot graph (zero-shot)."""
    return _build(
        {
            "name": "chatbot",
            "graph_schema": "zero_shot",
            "system_prompt": "You are a helpful AI assistant.",
        }
    )


def research_assistant() -> Any:
    """Research assistant graph (react with tool-calling capability)."""
    return _build(
        {
            "name": "research-assistant",
            "graph_schema": "react",
            "system_prompt": (
                "You are a helpful research assistant with the ability to search "
                "the web and use other tools."
            ),
            "mcp_tools": [],
        }
    )


def rag_assistant() -> Any:
    """RAG assistant graph (react)."""
    return _build(
        {
            "name": "rag-assistant",
            "graph_schema": "react",
            "system_prompt": "You are a helpful RAG assistant.",
            "mcp_tools": [],
        }
    )


def graph_rag_assistant() -> Any:
    """Graph RAG assistant graph (react)."""
    return _build(
        {
            "name": "graph-rag-assistant",
            "graph_schema": "react",
            "system_prompt": "You are a helpful graph RAG assistant.",
            "mcp_tools": [],
        }
    )
