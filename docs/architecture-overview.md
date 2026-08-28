# Architecture Overview

## System context

```mermaid
flowchart TB
  end_user["End user - Browser/app"]
  admin["Admin - Keycloak / Kong admin"]
  keycloak["Keycloak - Auth provider (OIDC)"]
  kong_api["Kong API Gateway (port 8000)"]
  web["Web (Next.js 16) - Frontend"]
  user_svc["User Service - Auth, users, roles"]
  agent_svc["Agent Service - LangGraph agents"]
  rag_svc["RAG Service - LangConnect"]
  tools_svc["Tools Service - FastMCP server"]
  postgres[("PostgreSQL (pgvector)")]
  neo4j[("Neo4j")]
  milvus[("Milvus")]
  minio[("MinIO")]
  airbyte["Airbyte"]

  end_user -->|"HTTPS"| web
  admin -.->|"admin access"| keycloak
  admin -.->|"admin access"| kong_api
  web -->|"API calls via rewrite/proxy"| kong_api
  kong_api -->|"/user-service/api/v1 (JWT)"| user_svc
  kong_api -->|"/agent-service/api/v1 (JWT)"| agent_svc
  kong_api -->|"/rag-service/api/v1 (JWT)"| rag_svc
  kong_api -->|"/tools-service/mcp (JWT)"| tools_svc
  kong_api -->|"/user-service/api/v1/auth (public subset)"| keycloak

  user_svc -->|"asyncpg"| postgres
  agent_svc -->|"asyncpg"| postgres
  rag_svc -->|"asyncpg"| postgres
  rag_svc -->|"graph store"| neo4j
  rag_svc -->|"vector store"| milvus
```

## Container diagram

```mermaid
flowchart TB
  nextjs["Web frontend: Next.js 16 - TypeScript - App Router, SSR, client components"]
  opal["Web frontend: @onyx/opal lib - TypeScript - Shared components, layouts, icons"]

  user_api["User Service: FastAPI routes - Python 3.11 - /api/v1/users, /api/v1/auth"]
  user_ctrl["User Service: Controllers - Python 3.11 - Orchestration, error translation"]
  user_logic["User Service: Services - Python 3.11 - Business logic"]
  user_repo["User Service: Repositories - Python 3.11 - SQLAlchemy async + Alembic"]

  agent_api["Agent Service: FastAPI routes - Python 3.11 - /api/v1/chat, /api/v1/agents"]
  agent_ctrl["Agent Service: Controllers - Python 3.11 - Orchestration"]
  agent_logic["Agent Service: Services - Python 3.11 - LangGraph agents"]
  agent_repo["Agent Service: Repositories - Python 3.11 - LangGraph checkpoint stores"]
  streamlit["Agent Service: Streamlit UI - Python 3.11 - Dev UI for agent debugging"]

  rag_api["RAG Service: FastAPI routes - Python 3.11 - /api/v1/collections, /api/v1/documents"]
  rag_logic["RAG Service: Services - Python 3.11 - Document processing, graph RAG"]
  rag_db["RAG Service: Database layer - Python 3.11 - pgvector + Neo4j + Milvus"]

  mcp_server["Tools Service: FastMCP server - Python 3.11 - HTTP transport at /mcp"]
  tool_registry["Tools Service: Tool Registry - Python 3.11 - Plugin discovery in src/tools/"]
  tool_cats["Tools Service: Tool categories - Python 3.11 - Extend BaseToolCategory ABC"]

  nextjs -->|"npm workspace dependency"| opal

  user_api -->|"calls"| user_ctrl
  user_ctrl -->|"calls"| user_logic
  user_logic -->|"calls"| user_repo

  agent_api -->|"calls"| agent_ctrl
  agent_ctrl -->|"calls"| agent_logic
  agent_logic -->|"calls"| agent_repo
```

## Authorization Model

User-service owns runtime authorization. Services and the web app check named
permissions, and user-service resolves the caller's effective permission set
from local RBAC data.

- Users can hold multiple composite roles through `user_roles`.
- `users.role` is a derived primary-role mirror for legacy readers and
  Keycloak realm-role sync.
- Composite roles aggregate direct permissions and feature bundles stored in
  `role_ids`.
- The `system-admin` wildcard role resolves to `["*"]`.
- `users.is_superuser` is not part of authorization.

## Python service layered architecture

```mermaid
flowchart LR
  Route["API layer - Thin HTTP handlers"]
  Controller["Controller layer - Orchestration / error mapping"]
  Service["Service layer - Business logic"]
  Repository["Repository layer - Data access / async SQLAlchemy"]
  Config["Core layer - pydantic-settings"]
  Exceptions["Core layer - NotFoundError, ConflictError"]
  Security["Core layer - JWT / auth utilities"]

  Route --> Controller
  Controller --> Service
  Service --> Repository
  Service -.-> Exceptions
  Controller -.-> Exceptions
  Config -.-> Service
  Config -.-> Repository
```

**Layer rules:**
- Routes parse HTTP params, call controller, return response. No business logic.
- Controllers orchestrate services, translate domain errors to HTTP statuses.
- Services are pure domain logic. Raise domain exceptions from `core/exceptions.py`.
- Repositories wrap SQLAlchemy async sessions. Each entity has its own repo.
- Config loaded via `pydantic-settings` `BaseSettings` with `@lru_cache`.
- Services/controllers: `_instance` module var + `get_*()` singleton pattern.

## Development lifecycle

```mermaid
flowchart LR
  Start([Start])
  Understand["Load skill + read AGENTS.md"]
  Code["Follow layered architecture"]
  Test["make test / npm test"]
  Lint["make lint"]
  Typecheck["make typecheck / npm run types:check"]
  Validate["make validate"]
  QualityGate["make quality-staged"]
  Push["make quality-push"]
  Done([Done])

  Start --> Understand
  Understand --> Code
  Code --> Test
  Test --> Lint
  Lint --> Typecheck
  Typecheck --> Validate
  Validate --> QualityGate
  QualityGate --> Push
  Push --> Done
```

## Infrastructure & startup

```mermaid
flowchart LR
  env_init["1. Env setup: make env-init"]
  env_check["1. Env setup: make env-check"]
  dc_services["2. Infrastructure: docker compose up"]
  PG["Postgres"]
  Neo4j["Neo4j"]
  Milvus["Milvus"]
  Airbyte["Airbyte"]
  KC["Keycloak"]
  dc_dev["3. App services: docker compose up"]
  User["User Service"]
  Agent["Agent Service"]
  RAG["RAG Service"]
  Tools["Tools Service"]
  Kong["Kong Gateway"]

  env_init --> env_check
  env_check --> dc_services

  dc_services --> PG
  dc_services --> Neo4j
  dc_services --> Milvus
  dc_services --> Airbyte
  dc_services --> KC

  dc_services --> dc_dev

  Kong --> User
  Kong --> Agent
  Kong --> RAG
  Kong --> Tools

  User --> PG
  Agent --> PG
  RAG --> PG
   RAG --> Neo4j
   RAG --> Milvus

## Agent service composition

Agents in the agent-service are composed from explicit components (brain,
perceptrons, tool gateway, graph schema, runtime policies) through the
`agent_composition` package — `AgentFactory` → `AgentComposer` → `ComposedAgent`
— rather than monolithic agent modules. Built-in agents are recipes; LangGraph
Studio graphs are exposed from `src/agents/studio_graphs.py`. See
[docs/agent-composition.md](agent-composition.md) for the full runtime
reference and the list of legacy modules removed in ASC-7.

```
