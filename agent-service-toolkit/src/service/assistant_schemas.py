"""
Assistant schema / config endpoint.

GET /assistants/{id}/schemas — returns the graph-specific config
schemas with ``x_oap_ui_config`` metadata consumed by
Open Agent Platform.

The ~310-line GRAPH_SCHEMAS dict lives here so it does not bloat
other modules.
"""
import logging
from typing import Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException

from agents import get_all_agent_info
from core import settings
from service.auth import verify_bearer

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_bearer)])


# =============================================================================
# Helper: fetch Ollama models for dropdown
# =============================================================================

async def _get_ollama_models() -> list[str]:
    """Return a list of available Ollama model names (best-effort)."""
    ollama_url = settings.OLLAMA_BASE_URL or "http://localhost:11434"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{ollama_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                if models:
                    return models
    except Exception:
        pass
    return [settings.OLLAMA_MODEL]


# =============================================================================
# Route
# =============================================================================

@router.get("/assistants/{assistant_id}/schemas")
async def get_assistant_schemas(assistant_id: str) -> Dict:
    """
    Get schemas for an assistant's configuration.
    Returns graph-specific config schemas with x_oap_ui_config metadata
    for Open Agent Platform.
    """
    all_agents = get_all_agent_info()

    # Fetch available models from Ollama for dropdown
    available_models = await _get_ollama_models()
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

    # Long-term memory toggle — shared across all graphs
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

    # Agent options
    agent_list = [a.key for a in all_agents]
    agent_options = [{"label": a, "value": a} for a in agent_list]

    # Static option lists
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

    # ---- Graph-specific config schemas ----
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
            "rag_config": {
                "type": "object",
                "title": "RAG Configuration",
                "x_oap_ui_config": {"type": "rag"},
            },
            "llama_guard_enabled": {
                "type": "boolean",
                "title": "LlamaGuard Safety",
                "default": True,
                "x_oap_ui_config": {"type": "boolean"},
            },
        },
        "command-agent": {
            "model": model_field,
            "long_term_memory": long_term_memory_field,
            "allowed_commands": {
                "type": "string",
                "title": "Allowed Commands",
                "default": "docker",
                "x_oap_ui_config": {
                    "type": "select",
                    "options": command_options,
                },
            },
            "sandbox_mode": {
                "type": "boolean",
                "title": "Sandbox Mode",
                "default": True,
                "x_oap_ui_config": {"type": "boolean"},
            },
        },
        "bg-task-agent": {
            "model": model_field,
            "long_term_memory": long_term_memory_field,
            "max_retries": {
                "type": "number",
                "title": "Max Retries",
                "default": 3,
                "x_oap_ui_config": {"type": "number", "min": 1, "max": 10},
            },
            "timeout_seconds": {
                "type": "number",
                "title": "Timeout (seconds)",
                "default": 3600,
                "x_oap_ui_config": {"type": "number", "min": 60, "max": 86400},
            },
        },
        "configurable-mcp-agent": {
            "model": model_field,
            "long_term_memory": long_term_memory_field,
            "system_prompt": {
                "type": "string",
                "title": "System Prompt",
                "default": (
                    "You are a helpful AI assistant. You have access to various tools "
                    "that help you accomplish tasks. Always be helpful, accurate, and "
                    "provide clear explanations."
                ),
                "x_oap_ui_config": {
                    "type": "textarea",
                    "placeholder": "Enter the system prompt for this agent...",
                },
            },
            "mcp_tools": {
                "type": "array",
                "title": "MCP Tools",
                "description": "Select which MCP tools this agent can use.",
                "x_oap_ui_config": {
                    "type": "mcp",
                    "mcp_url": "http://mcp-server:8001/mcp",
                    "default": {
                        "url": "http://mcp-server:8001/mcp",
                        "tools": [],
                    },
                },
            },
        },
        "interrupt-agent": {
            "model": model_field,
            "long_term_memory": long_term_memory_field,
            "default_action": {
                "type": "string",
                "title": "Default Action",
                "default": "cancel",
                "x_oap_ui_config": {
                    "type": "select",
                    "options": action_options,
                },
            },
        },
        "knowledge-base-agent": {
            "model": model_field,
            "long_term_memory": long_term_memory_field,
            "aws_kb_id": {
                "type": "string",
                "title": "AWS Knowledge Base ID",
                "x_oap_ui_config": {"type": "text", "placeholder": "Enter AWS KB ID"},
            },
            "aws_region": {
                "type": "string",
                "title": "AWS Region",
                "default": "us-east-1",
                "x_oap_ui_config": {
                    "type": "select",
                    "options": aws_region_options,
                },
            },
        },
        "github-mcp-agent": {
            "model": model_field,
            "long_term_memory": long_term_memory_field,
            "mcp_config": {
                "type": "object",
                "title": "MCP Configuration",
                "x_oap_ui_config": {
                    "type": "mcp",
                    "default": {
                        "url": "http://mcp-server:8001/mcp",
                        "tools": [],
                    },
                },
            },
            "workspace_dir": {
                "type": "string",
                "title": "Workspace Directory",
                "default": "/workspace",
                "x_oap_ui_config": {"type": "text"},
            },
        },
        "langgraph-supervisor-agent": {
            "model": model_field,
            "long_term_memory": long_term_memory_field,
            "supervisor_prompt": {
                "type": "string",
                "title": "Supervisor System Prompt",
                "default": (
                    "You are a team supervisor managing multiple specialized agents. "
                    "Analyze each user request and delegate to the most appropriate "
                    "agent based on their capabilities."
                ),
                "x_oap_ui_config": {
                    "type": "textarea",
                    "placeholder": "Enter the supervisor's system prompt...",
                },
            },
            "sub_agents": {
                "type": "array",
                "title": "Sub-Agents (Parallel)",
                "description": (
                    "Configure agents that work in PARALLEL. "
                    "Supervisor delegates to one or more agents based on the request. "
                    "Each sub-agent can optionally use a different model. "
                    "If no model is selected, the supervisor's model is used."
                ),
                "x_oap_ui_config": {
                    "type": "sub_agents_config",
                    "mcp_url": "http://mcp-server:8001/mcp",
                    "model_options": model_options,
                },
            },
        },
        "langgraph-supervisor-hierarchy-agent": {
            "model": model_field,
            "long_term_memory": long_term_memory_field,
            "pipeline_stages": {
                "type": "array",
                "title": "Pipeline Stages (Sequential)",
                "description": (
                    "Configure stages that run in SEQUENCE. "
                    "Each stage's output feeds into the next stage. "
                    "Each stage can optionally use a different model. "
                    "If no model is selected, the supervisor's model is used."
                ),
                "x_oap_ui_config": {
                    "type": "pipeline_stages",
                    "mcp_url": "http://mcp-server:8001/mcp",
                    "model_options": model_options,
                },
            },
            "retry_count": {
                "type": "number",
                "title": "Retry Count",
                "default": 2,
                "x_oap_ui_config": {"type": "number", "min": 0, "max": 5},
            },
            "on_error": {
                "type": "string",
                "title": "On Error",
                "default": "abort",
                "x_oap_ui_config": {
                    "type": "select",
                    "options": [
                        {"label": "Abort Pipeline", "value": "abort"},
                        {"label": "Skip Stage", "value": "skip"},
                    ],
                },
            },
        },
    }

    # Resolve graph_id from assistant_id
    target_graph_id = assistant_id
    from .store import get_assistant_from_store

    stored = await get_assistant_from_store(assistant_id)
    if stored:
        target_graph_id = stored.get("graph_id")
    else:
        found = any(a.key == assistant_id for a in all_agents)
        if not found:
            raise HTTPException(status_code=404, detail=f"Assistant {assistant_id} not found")

    config_props = GRAPH_SCHEMAS.get(target_graph_id, {"model": model_field})

    return {
        "graph_id": target_graph_id,
        "config_schema": {
            "type": "object",
            "properties": config_props,
        },
        "state_schema": {
            "type": "object",
            "properties": {
                "messages": {"type": "array", "items": {"type": "object"}},
            },
        },
    }
