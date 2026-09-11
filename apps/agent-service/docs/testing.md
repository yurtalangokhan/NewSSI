# Agent service testing

Use this document to choose validation for agent-service changes. Prefer the
smallest meaningful command while you work, then run the service validation gate
before the change is ready.

## Commands

Run commands from `apps/agent-service/`.

```sh
make test
make test-file FILE=tests/path/to/test.py
make lint
make typecheck
make validate
```

The default `make test` target skips `tests/app`, `tests/voice`, and
`tests/integration`. Use `make test-all` when a change touches those surfaces.

## Focus areas

Choose tests by ownership:

- Agent composition: `tests/agent_composition/` and `tests/agents/`.
- Agent definitions API: `tests/controller/`, `tests/service/`, and route tests
  near `agent_definition`.
- Streaming: `tests/service/` files that cover `agent_message_stream`.
- Graph strategies: `tests/agents/graphs/`.
- Tool gateway and knowledge selection: gateway, catalog, and knowledge selector
  tests under `tests/agent_composition/` and `tests/agents/`.

Run `make quality-staged` from the repository root before committing or pushing.
