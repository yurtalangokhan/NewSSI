"""Assistant schema service.

Builds assistant configuration schemas and resolves available Ollama models.
"""

from typing import Any

import httpx

from agents import get_all_agent_info
from core import settings


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

        all_agents = get_all_agent_info()
        available_models = await self.get_ollama_models()
        model_options = [{"label": m, "value": m} for m in available_models]

        model_field = {
            "type": "string",
            "title": "Model",
            "default": settings.OLLAMA_MODEL,
            "x_oap_ui_config": {
                "type": "select",
                "options": model_options,
            },
        }

        long_term_memory_field = {
            "type": "boolean",
            "title": "Long-Term Memory",
            "description": (
                "Enable cross-thread long-term memory. When enabled, the agent "
                "will remember facts and preferences about you across conversations."
            ),
            "default": False,
            "x_oap_ui_config": {"type": "boolean"},
        }

        agent_list = [a.key for a in all_agents]
        agent_options = [{"label": a, "value": a} for a in agent_list]

        aws_region_options = [
            {"label": "US East (N. Virginia)", "value": "us-east-1"},
            {"label": "US West (Oregon)", "value": "us-west-2"},
            {"label": "EU (Ireland)", "value": "eu-west-1"},
            {"label": "EU (Frankfurt)", "value": "eu-central-1"},
            {"label": "Asia Pacific (Tokyo)", "value": "ap-northeast-1"},
        ]

        command_options = [
            {"label": "Docker", "value": "docker"},
            {"label": "Git", "value": "git"},
            {"label": "NPM", "value": "npm"},
            {"label": "Python", "value": "python"},
            {"label": "Node", "value": "node"},
            {"label": "Curl", "value": "curl"},
        ]

        pipeline_options = [
            {"label": "Test", "value": "test"},
            {"label": "Build", "value": "build"},
            {"label": "Security Scan", "value": "security-scan"},
            {"label": "Deploy", "value": "deploy"},
            {"label": "Notify", "value": "notify"},
        ]

        action_options = [
            {"label": "Cancel", "value": "cancel"},
            {"label": "Pause", "value": "pause"},
            {"label": "Resume", "value": "resume"},
            {"label": "Prioritize", "value": "prioritize"},
        ]

        GRAPH_SCHEMAS: dict[str, dict] = {
            "chatbot": {
                "model": model_field,
                "long_term_memory": long_term_memory_field,
            },
            "research-assistant": {
                "model": model_field,
                "long_term_memory": long_term_memory_field,
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
                "model": model_field,
                "long_term_memory": long_term_memory_field,
                "datasource_ids": {
                    "type": "array",
                    "title": "Data Sources",
                    "items": {"type": "string"},
                    "x_oap_ui_config": {"type": "multiselect"},
                },
            },
            "graph-rag-assistant": {
                "model": model_field,
                "long_term_memory": long_term_memory_field,
                "datasource_ids": {
                    "type": "array",
                    "title": "Data Sources",
                    "items": {"type": "string"},
                    "x_oap_ui_config": {"type": "multiselect"},
                },
            },
            "command-agent": {
                "model": model_field,
                "long_term_memory": long_term_memory_field,
                "commands": {
                    "type": "array",
                    "title": "Available Commands",
                    "items": {"type": "string", "enum": command_options},
                    "x_oap_ui_config": {"type": "multiselect", "options": command_options},
                },
            },
            "bg-task-agent": {
                "model": model_field,
                "aws_region": {
                    "type": "string",
                    "title": "AWS Region",
                    "x_oap_ui_config": {"type": "select", "options": aws_region_options},
                },
                "pipeline": {
                    "type": "string",
                    "title": "Pipeline Stage",
                    "x_oap_ui_config": {"type": "select", "options": pipeline_options},
                },
                "actions": {
                    "type": "array",
                    "title": "Actions",
                    "items": {"type": "string"},
                    "x_oap_ui_config": {"type": "multiselect", "options": action_options},
                },
            },
            "configurable-mcp-agent": {
                "model": model_field,
                "long_term_memory": long_term_memory_field,
                "mcp_servers": {
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
                },
            },
            "langgraph-supervisor-agent": {
                "model": model_field,
                "long_term_memory": long_term_memory_field,
                "agents": {
                    "type": "array",
                    "title": "Sub-Agents",
                    "items": {"type": "string", "enum": agent_options},
                    "x_oap_ui_config": {"type": "multiselect", "options": agent_options},
                },
            },
            "langgraph-supervisor-hierarchy-agent": {
                "model": model_field,
                "long_term_memory": long_term_memory_field,
                "agents": {
                    "type": "array",
                    "title": "Sub-Agents",
                    "items": {"type": "string", "enum": agent_options},
                    "x_oap_ui_config": {"type": "multiselect", "options": agent_options},
                },
            },
        }

        return GRAPH_SCHEMAS.get(assistant_id, {})
