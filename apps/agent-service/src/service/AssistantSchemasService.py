"""Assistant schema service.

Builds assistant configuration schemas and resolves available Ollama models.
"""

from typing import Any

import httpx

from core import settings


def _model_field(model_options: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "type": "string",
        "title": "Model",
        "default": settings.OLLAMA_MODEL,
        "x_oap_ui_config": {
            "type": "select",
            "options": model_options,
        },
    }


def _long_term_memory_field() -> dict[str, Any]:
    return {
        "type": "boolean",
        "title": "Long-Term Memory",
        "description": (
            "Enable cross-thread long-term memory. When enabled, the agent "
            "will remember facts and preferences about you across conversations."
        ),
        "default": False,
        "x_oap_ui_config": {"type": "boolean"},
    }


def _datasource_ids_field() -> dict[str, Any]:
    return {
        "type": "array",
        "title": "Data Sources",
        "items": {"type": "string"},
        "x_oap_ui_config": {"type": "multiselect"},
    }


def _mcp_servers_field() -> dict[str, Any]:
    return {
        "type": "array",
        "title": "MCP Servers",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "endpoint": {"type": "string"},
            },
        },
        "x_oap_ui_config": {"type": "array"},
    }


def _build_graph_schemas(
    model_field: dict[str, Any],
    long_term_memory_field: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    base_fields = {
        "model": model_field,
        "long_term_memory": long_term_memory_field,
    }
    return {
        "chatbot": base_fields,
        "research-assistant": {
            **base_fields,
            "web_search": {
                "type": "boolean",
                "title": "Web Search",
                "default": True,
                "x_oap_ui_config": {"type": "boolean"},
            },
            "calculator": {
                "type": "boolean",
                "title": "Calculator",
                "default": True,
                "x_oap_ui_config": {"type": "boolean"},
            },
            "weather": {
                "type": "boolean",
                "title": "Weather",
                "default": False,
                "x_oap_ui_config": {"type": "boolean"},
            },
        },
        "rag-assistant": {
            **base_fields,
            "datasource_ids": _datasource_ids_field(),
        },
        "graph-rag-assistant": {
            **base_fields,
            "datasource_ids": _datasource_ids_field(),
        },
        "configurable-mcp-agent": {
            **base_fields,
            "mcp_servers": _mcp_servers_field(),
        },
    }


class AssistantSchemasService:
    """Service for assistant configuration schema generation."""

    async def get_ollama_models(self) -> list[str]:
        """Return a best-effort list of available Ollama models."""
        ollama_url = settings.OLLAMA_BASE_URL or "http://localhost:11434"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{ollama_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    models = [m["name"] for m in data.get("models", []) if isinstance(m, dict)]
                    if models:
                        return models
        except Exception:
            pass
        return [settings.OLLAMA_MODEL]

    async def get_assistant_schemas(self, assistant_id: str) -> dict[str, Any]:
        """Return graph-specific assistant configuration schemas."""
        if not assistant_id:
            raise ValueError("assistant_id is required")

        available_models = await self.get_ollama_models()
        model_options = [{"label": m, "value": m} for m in available_models]
        graph_schemas = _build_graph_schemas(
            _model_field(model_options),
            _long_term_memory_field(),
        )
        return graph_schemas.get(assistant_id, {})
