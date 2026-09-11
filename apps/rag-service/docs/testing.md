# RAG service testing

Use this document to choose validation for RAG service changes.

## Commands

Run commands from `apps/rag-service/`.

```sh
make test
make test TEST_FILE=tests/path/to/test.py
make lint
make typecheck
make validate
```

The default `make test` command runs unit tests with `IS_TESTING=true`. Use an
explicit test path when a change affects broader test groups.

## Focus areas

- API changes: route and service tests under `tests/`.
- Retrieval changes: retrieval service tests and tools-service knowledge tool
  integration tests.
- Graph changes: graph build, graph query, and collection lifecycle tests.

Run `make quality-staged` from the repository root before committing or pushing.
