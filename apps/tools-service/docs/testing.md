# Tools service testing

Use this document to choose validation for tools-service changes.

## Commands

Run commands from `apps/tools-service/`.

```sh
make test
make lint
make typecheck
make validate
```

Use focused pytest paths for one tool category, then run `make validate` before
marking the service change ready.

## Focus areas

- Registry changes: `tests/test_registry.py`.
- Tool category changes: the matching `tests/test_*_tools.py` file.
- Knowledge retrieval: `tests/test_knowledge_tools.py` plus agent-service
  gateway or selector tests when the agent contract changes.

Run `make quality-staged` from the repository root before committing or pushing.
