"""Pure helper functions for persona/agent catalog serialization.

These are stateless helpers used by ``PersonaController``. They are extracted
into their own module to keep the controller focused on orchestration and to
make the pure logic independently testable.
"""

import re
import uuid
from typing import Any

from i18n import t

from core.env import env
from core.settings import settings

# database_search/graph_search are synthesized from an agent's RAG config
# rather than being real MCP tools, so there's no external catalog to pull a
# name/description from — these come from this service's own locale files
# (translated per-request via the same X-Language mechanism as everything
# else, see i18n-py's middleware) instead of tools-service.
RAG_TOOL_NAMES = ("database_search", "graph_search")


def _rag_tool_metadata(tool_name: str) -> dict[str, str]:
    return {
        "display_name": t(f"rag_tool.{tool_name}.name"),
        "description": t(f"rag_tool.{tool_name}.description"),
    }


# tools-service embeds category/category_label/title tags directly into a
# tool's `description` string so a single field can carry all three pieces
# of per-request-translated metadata (see
# apps/tools-service/src/core/registry.py's `_setup_i18n_wrapper`). Callers
# must strip these before showing the description to a user, and may pull
# the localized display name out of the title tag.
_MCP_TOOL_TAG_RE = re.compile(r"\[(?:category|category_label|title):[^\]]*\]")
_MCP_TOOL_TITLE_TAG_RE = re.compile(r"\[title:([^\]]*)\]")


def _parse_mcp_tool_description(raw_description: str) -> tuple[str, str | None]:
    """Returns (clean_description, localized_title_or_None)."""
    title_match = _MCP_TOOL_TITLE_TAG_RE.search(raw_description)
    title = title_match.group(1).strip() if title_match else None
    clean = _MCP_TOOL_TAG_RE.sub("", raw_description).strip()
    return clean, title or None


def _is_uuid_owner_id(owner_id: str) -> bool:
    try:
        uuid.UUID(owner_id)
    except ValueError:
        return False
    return True


def flow_meta_fields(
    definition: Any | None,
    flow_summaries: dict[Any, Any] | None,
) -> dict[str, Any]:
    """Card-level flow fields for a persona payload.

    Empty for anything that is not a flow, so both serializers can splat
    the result unconditionally without teaching each of them the rule.
    """
    if definition is None or getattr(definition, "graph_schema", None) != "flow":
        return {}

    summary = (flow_summaries or {}).get(definition.id)
    return {
        "flow_published_version_no": summary.published_version_no if summary else None,
        "flow_has_draft": bool(summary.has_draft) if summary else False,
        "flow_updated_at": (
            summary.updated_at.isoformat() if summary and summary.updated_at else None
        ),
    }


def _normalize_model_alias(model_name: str | None) -> str | None:
    """Normalize provider aliases to concrete model names."""
    if model_name is None:
        return None
    normalized = str(model_name).strip()
    if not normalized:
        return None
    lower_name = normalized.lower()
    if lower_name in {"ollama", "default", "provider", "builtin"}:
        return env.OLLAMA_MODEL or settings.OLLAMA_MODEL or settings.DEFAULT_MODEL
    return normalized


def build_agent_availability(
    agent: dict[str, Any],
    *,
    available_models: set[str],
    default_model: str | None,
    available_mcp_tools: set[str],
    available_rag_collections: set[str],
    available_graph_rag_collections: set[str],
    collection_display_names: dict[str, str] | None = None,
    memory_available: bool = True,
) -> dict[str, Any]:
    """Return component-level availability for an agent snapshot."""
    checks: list[dict[str, str]] = []
    raw_selected = agent.get("llm_model_version_override") or agent.get("model")
    selected_model = _normalize_model_alias(raw_selected) if raw_selected else None

    raw_default = default_model or settings.DEFAULT_MODEL or env.DEFAULT_MODEL
    effective_default_model = _normalize_model_alias(raw_default) if raw_default else None

    if effective_default_model and effective_default_model not in available_models:
        ollama_default = env.OLLAMA_MODEL or settings.OLLAMA_MODEL
        if ollama_default and ollama_default in available_models:
            effective_default_model = ollama_default

    if selected_model:
        if selected_model in available_models:
            checks.append(
                {
                    "component": "model",
                    "status": "ok",
                    "message": f"Model '{selected_model}' is available.",
                }
            )
        else:
            checks.append(
                {
                    "component": "model",
                    "status": "error",
                    "message": f"Model '{selected_model}' is selected but is not available.",
                }
            )
    elif effective_default_model:
        if effective_default_model in available_models:
            checks.append(
                {
                    "component": "model",
                    "status": "ok",
                    "message": f"Using default model '{effective_default_model}'.",
                }
            )
        else:
            checks.append(
                {
                    "component": "model",
                    "status": "error",
                    "message": f"Default model '{effective_default_model}' is not available.",
                }
            )
    else:
        checks.append(
            {
                "component": "model",
                "status": "error",
                "message": "No default model is configured.",
            }
        )

    memory_enabled = agent.get("memory_type") == "long_term" or bool(agent.get("long_term_memory"))
    if memory_enabled:
        checks.append(
            {
                "component": "memory",
                "status": "ok" if memory_available else "error",
                "message": (
                    "Long-term memory is available."
                    if memory_available
                    else "Long-term memory is enabled but memory storage is not available."
                ),
            }
        )

    for tool_name in agent.get("mcp_tools") or []:
        checks.append(
            {
                "component": "mcp_tool",
                "status": "ok" if tool_name in available_mcp_tools else "error",
                "message": (
                    f"MCP tool '{tool_name}' is available."
                    if tool_name in available_mcp_tools
                    else f"MCP tool '{tool_name}' is selected but is not available."
                ),
            }
        )

    rag_config = agent.get("rag_config") or {}
    rag_config_display_names = rag_config.get("display_names") or {}
    if not isinstance(rag_config_display_names, dict):
        rag_config_display_names = {}
    collection_display_names = {
        **rag_config_display_names,
        **(collection_display_names or {}),
    }
    for collection in rag_config.get("document_processing") or []:
        display_name = collection_display_names.get(collection, collection)
        checks.append(
            {
                "component": "rag",
                "status": "ok" if collection in available_rag_collections else "error",
                "message": (
                    f"RAG collection '{display_name}' is available."
                    if collection in available_rag_collections
                    else f"RAG collection '{display_name}' is selected but is not available."
                ),
            }
        )

    for collection in rag_config.get("knowledge_graph") or []:
        display_name = collection_display_names.get(collection, collection)
        checks.append(
            {
                "component": "graph_rag",
                "status": "ok" if collection in available_graph_rag_collections else "error",
                "message": (
                    f"Graph RAG collection '{display_name}' is available."
                    if collection in available_graph_rag_collections
                    else f"Graph RAG collection '{display_name}' is selected but is not available."
                ),
            }
        )

    if any(check["status"] == "error" for check in checks):
        status_value = "unavailable"
    elif any(check["status"] == "warning" for check in checks):
        status_value = "degraded"
    else:
        status_value = "available"

    return {"status": status_value, "checks": checks}


def _format_tool_display_name(tool_name: str) -> str:
    return tool_name.replace("_", " ").replace("-", " ").title()


def _has_web_search_tool(tool_names: list[str]) -> bool:
    return any("web_search" in tool_name or "web-search" in tool_name for tool_name in tool_names)
