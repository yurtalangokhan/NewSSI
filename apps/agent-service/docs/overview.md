# Agent service overview

Agent service owns LangGraph agent orchestration, chat streaming, dynamic agent
definitions, built-in agent recipes, and the bridge from agents to tools-service.
Use this document first when you need to understand where agent behavior lives.

## Source map

The service keeps delivery, orchestration, business logic, persistence, and
agent runtime code in separate modules.

| Area | Location |
|---|---|
| FastAPI routes | `src/api/routes/` |
| Controllers | `src/controller/` |
| Business services | `src/service/` |
| Repositories and persistence | `src/repository/`, `src/core/db/` |
| Agent composition | `src/agent_composition/` |
| LangGraph schemas and strategies | `src/agents/graphs/` |
| Backward-compatible agent facade | `src/agents/agents.py` |
| Studio graph entrypoints | `src/agents/studio_graphs.py` |
| Tests | `tests/` |

## Documentation

Use the smallest set of local documents for the task:

- [Architecture](architecture.md) for module boundaries and runtime flow.
- [Agent composition](agent-composition.md) for dynamic and built-in agent
  construction.
- [API](api.md) for public endpoint behavior.
- [Testing](testing.md) before changing validation scope.
- [Runbook](runbook.md) for startup, environment, and operations.
- [File-based credentials](file-based-credentials.md), [Ollama](ollama.md),
  and [Google models](google-models.md) for provider-specific setup.
