# Agentic AI Platform

Enterprise-grade multi-agent orchestration and conversational AI platform with unified governance, observability, resilience, and security.

## Architecture & Services

The platform consists of specialized microservices communicating via HTTP/REST, Server-Sent Events (SSE), and the Model Context Protocol (MCP), routed through the APISIX gateway and secured with Keycloak OIDC.

| Service | Port | Description | Stack |
|---|---|---|---|
| **agent-service** | `8123` | Core LangGraph multi-agent orchestration engine, state graph management, checkpointing, and agent composition. | FastAPI, LangGraph, psycopg, PostgreSQL |
| **user-service** | `8090` | Identity, enterprise RBAC/ABAC authorization, user management, and Keycloak synchronization. | FastAPI, PostgreSQL, Keycloak |
| **rag-service** | `8083` | Retrieval-Augmented Generation engine, knowledge graph traversal, hybrid vector search. | FastAPI, Milvus, Neo4j, pgvector |
| **tools-service** | `8003` | Tool execution engine: a FastAPI application with the FastMCP transport mounted at `/mcp`. | FastAPI, FastMCP |
| **web** | `3000` | Enterprise Next.js web application and dashboard interface. | Next.js, React, TypeScript |
| **apisix** | `8000` | API gateway: reverse proxy whose `gateway-auth` plugin performs Keycloak login, token introspection, and UMA authorization. No rate limiting at the edge. | APISIX 3.18 |

## Canonical Database Stack

Strictly standardized on three core database technologies:
- **PostgreSQL 18 (+ pgvector):** Relational state, sessions, LangGraph checkpointers, and relational vector indices.
- **Milvus:** High-scale, low-latency dense vector storage and semantic search.
- **Neo4j 5.24:** Knowledge graph, entity-relationship graphs, and Graph RAG traversal.

## Shared Packages

- `packages/error-contract`: The shared `ErrorEnvelope`, the exception handlers that produce it, and `ERROR_RESPONSES` for declaring it in OpenAPI.
- `packages/metrics`: Prometheus metrics (`prometheus_client`) and ASGI middleware exposing `/metrics`. Series are labelled by route *template*, so cardinality stays bounded.
- `packages/security`: Safe reading of `SecretStr` settings; the mask is truthy, so an unwrapped secret authenticates silently with the wrong value.
- `packages/security`: Bounded retries with exponential backoff and circuit breaker isolation (`configs/resilience.yaml`).
- `packages/localization`: Cross-service internationalization and localized error messages.
- `packages/idempotency`: Distributed idempotency enforcement via Redis locks and cache.

## Getting Started Locally

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ / uv
- Node.js 20+

### Running Infrastructure & Services

```bash
# 1. Start core infrastructure (Postgres, Keycloak, APISIX, Milvus, Neo4j)
docker compose -f configs/docker-compose-services.yml up -d

# 2. Start platform application services
docker compose -f configs/docker-compose-dev.yml up -d
```

### Health & Observability

- Agent Service Health: `http://localhost:8123/api/v1/health`
- Agent Service Metrics: `http://localhost:8123/metrics`
- User Service Health: `http://localhost:8090/api/v1/health/`
- User Service Metrics: `http://localhost:8090/metrics`
- Tools Service Health: `http://localhost:8003/health`
- Tools Service Metrics: `http://localhost:8003/metrics`
- RAG Service Health: `http://localhost:8083/api/v1/health`
- RAG Service Metrics: `http://localhost:8083/metrics`

## Security & Governance

Run the gate the way CI does:

```bash
make governance-scan     # package lint/tests, repository rules, and the API + metrics contract of all four services
```

- **Secrets** never live in the repository. Compose files and the rendered
  APISIX configuration read them from `.env`, which is gitignored; each has a
  committed `.env.example` holding placeholders only. Operators provide
  `configs/.env` and its credentials explicitly.
- **API contract.** Every service publishes an OpenAPI 3.1 document with real
  `info` metadata, an `operationId` and a success response on every operation,
  and the shared `ErrorEnvelope` on every documented failure.
- **Observability.** Every service exposes `/metrics` in Prometheus text format,
  labelled by route template. `/metrics` is not routed through the gateway.
- **Resilience.** Retry budgets, backoff and circuit-breaker thresholds come from
  [`configs/resilience.yaml`](configs/resilience.yaml); no call site hardcodes them.
- **Architecture catalog** validated against the OPA baseline in
  [`docs/architecture/service-catalog.yaml`](docs/architecture/service-catalog.yaml).
