# RAG service runbook

Use this runbook for startup, storage dependencies, and operational checks.

## Startup

Run these commands from `apps/rag-service/`.

```sh
make dev-install
make run
```

RAG service requires Postgres with pgvector and may require Neo4j and Milvus for
graph and vector workflows. Start shared infrastructure from the repository root
when local dependencies are missing.

Set `INTERNAL_USER_SERVICE_URL` to the gateway's `/internal/user-service`
base for identity and permission calls. RAG service requires this value and
does not read the web runtime `USER_SERVICE_URL`.

## Health checks

Use the service health endpoints documented in [api.md](api.md). Through the
gateway, the public health route is under `/rag-service`.
