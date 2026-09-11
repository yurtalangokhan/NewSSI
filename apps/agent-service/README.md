# Agent service

Agent service owns LangGraph-based agent orchestration for the Agentic AI
Platform. It serves chat and agent endpoints, composes built-in and dynamic
agents, streams runtime events, and connects agents to tools-service through a
trusted gateway.

## Documentation

Start with the service-local docs for agent-service work:

- [Overview](docs/overview.md) maps the source tree and durable docs.
- [Architecture](docs/architecture.md) explains service boundaries.
- [Agent composition](docs/agent-composition.md) is the canonical runtime
  reference for built-in and dynamic agents.
- [API](docs/api.md) documents public endpoints.
- [Testing](docs/testing.md) lists focused and full validation commands.
- [Runbook](docs/runbook.md) covers local startup and runtime checks.

Provider-specific notes live next to the service docs:

- [File-based credentials](docs/file-based-credentials.md)
- [Google models](docs/google-models.md)
- [Ollama](docs/ollama.md)

## Source map

| Area | Location |
|---|---|
| FastAPI routes | `src/api/routes/` |
| Controllers | `src/controller/` |
| Services | `src/service/` |
| Repositories | `src/repository/` |
| Database models and migrations | `src/core/db/` |
| Agent composition | `src/agent_composition/` |
| LangGraph graph strategies | `src/agents/graphs/` |
| Studio graph entrypoints | `src/agents/studio_graphs.py` |
| Tests | `tests/` |

## Local commands

Run commands from this directory.

```sh
make dev-install
make run
make test
make validate
```

Use `FAKE_MODEL=true` for local smoke checks that must not call a real LLM
provider. Runtime model selection must resolve through configured provider
defaults unless a caller explicitly supplies an override.
