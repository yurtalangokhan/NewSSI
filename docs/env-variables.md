# Environment Variables

## Infrastructure (`configs/.env`)

| Variable                | Description                                                      | Default                        |
| ----------------------- | ---------------------------------------------------------------- | ------------------------------ |
| `POSTGRES_DB`           | Main PostgreSQL database name                                    | `agenticai`                    |
| `POSTGRES_USER`         | PostgreSQL user                                                  | `postgres`                     |
| `POSTGRES_PASSWORD`     | PostgreSQL password                                              | —                              |
| `POSTGRES_HOST`         | PostgreSQL hostname                                              | `postgres`                     |
| `POSTGRES_PORT`         | PostgreSQL port                                                  | `5432`                         |
| `KEYCLOAK_DB`           | Keycloak PostgreSQL database                                     | `keycloak`                     |
| `KEYCLOAK_USER`         | Keycloak admin username                                          | `admin`                        |
| `KEYCLOAK_PASSWORD`     | Keycloak admin password                                          | —                              |
| `KEYCLOAK_HOST`         | Keycloak hostname                                                | `keycloak`                     |
| `KEYCLOAK_PORT`         | Keycloak port                                                    | `8080`                         |
| `KEYCLOAK_EXTERNAL_URL` | External URL for Keycloak                                        | `http://localhost:8080`        |
| `KEYCLOAK_INTERNAL_URL` | Internal URL for Keycloak                                        | `http://keycloak:8080`         |
| `MILVUS_HOST`           | Milvus (vector DB) hostname                                      | `milvus-standalone`            |
| `MILVUS_PORT`           | Milvus port                                                      | `19530`                        |
| `MINIO_ROOT_USER`       | MinIO admin username                                             | `minio`                        |
| `MINIO_ROOT_PASSWORD`   | MinIO admin password                                             | —                              |
| `MINIO_HOST`            | MinIO hostname                                                   | `minio`                        |
| `MINIO_PORT`            | MinIO API port                                                   | `9000`                         |
| `MINIO_CONSOLE_PORT`    | MinIO console port                                               | `9001`                         |
| `NEO4J_USER`            | Neo4j username                                                   | `neo4j`                        |
| `NEO4J_PASSWORD`        | Neo4j password                                                   | —                              |
| `NEO4J_HOST`            | Neo4j hostname                                                   | `neo4j`                        |
| `NEO4J_PORT`            | Neo4j Bolt port                                                  | `7687`                         |
| `AIRBYTE_DB`            | Airbyte PostgreSQL database                                      | `airbyte`                      |
| `AIRBYTE_USER`          | Airbyte DB user                                                  | `airbyte`                      |
| `AIRBYTE_PASSWORD`      | Airbyte DB password                                              | —                              |
| `KONG_DATABASE`         | Kong DB name                                                     | `kong`                         |
| `KONG_PASSWORD`         | Kong admin password                                              | —                              |
| `OLLAMA_IMAGE_TAG`      | Ollama Docker image tag                                          | `latest`                       |
| `OLLAMA_PORT`           | Host port mapped to built-in Ollama                              | `11434`                        |
| `OLLAMA_PRELOAD_MODELS` | Space-separated models pulled by `scripts/pull_ollama_models.sh` | `llama3.1:8b nomic-embed-text` |

---

## Kong (`configs/kong/kong.env`)

| Variable           | Description              | Default    |
| ------------------ | ------------------------ | ---------- |
| `KONG_DATABASE`    | Kong database name       | `kong`     |
| `KONG_PG_HOST`     | Kong PostgreSQL host     | `postgres` |
| `KONG_PG_USER`     | Kong PostgreSQL user     | `postgres` |
| `KONG_PG_PASSWORD` | Kong PostgreSQL password | —          |
| `KONG_PG_DATABASE` | Override env var         | `kong`     |

---

## User Service (`apps/user-service/.env`)

| Variable                      | Description                             | Default                                                       |
| ----------------------------- | --------------------------------------- | ------------------------------------------------------------- |
| `DATABASE_URL`                | PostgreSQL async connection string      | `postgresql+asyncpg://postgres:pass@localhost:5432/agenticai` |
| `SECRET_KEY`                  | JWT signing key (256-bit hex, 64 chars) | —                                                             |
| `ALGORITHM`                   | JWT signing algorithm                   | `HS256`                                                       |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token expiry                        | `30`                                                          |
| `KEYCLOAK_SERVER_URL`         | Keycloak base URL                       | `http://localhost:8080`                                       |
| `KEYCLOAK_REALM`              | Keycloak realm name                     | `agenticai`                                                   |
| `KEYCLOAK_CLIENT_ID`          | Keycloak client ID                      | `user-service`                                                |
| `KEYCLOAK_CLIENT_SECRET`      | Keycloak client secret                  | —                                                             |
| `DAG_AUTH_ENABLED`            | Enable DAG auth broker                  | `false`                                                       |
| `DAG_AUTH_JWT_SECRET`         | Secret for DAG-signed tokens            | —                                                             |
| `EXTERNAL_AUTH_BROKER_URL`    | External auth broker URL                | —                                                             |
| `EXTERNAL_AUTH_BROKER_TOKEN`  | External auth broker API token          | —                                                             |
| `INTERNAL_SERVICE_TOKEN`      | Secret for service-to-service auth      | —                                                             |
| `LOG_LEVEL`                   | Python logging level                    | `INFO`                                                        |
| `SERVICE_NAME`                | Service identifier                      | `user-service`                                                |
| `CORS_ORIGINS`                | Allowed CORS origins                    | `*`                                                           |
| `HOST`                        | Server bind address                     | `0.0.0.0`                                                     |
| `PORT`                        | Server port                             | `8090`                                                        |

---

## Agent Service (`apps/agent-service/.env`)

| Variable                 | Description                                                                              | Default                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `DATABASE_URL`           | PostgreSQL async connection string                                                       | `postgresql+asyncpg://postgres:pass@localhost:5432/agenticai` |
| `SECRET_KEY`             | JWT verification key                                                                     | —                                                             |
| `ALGORITHM`              | JWT algorithm                                                                            | `HS256`                                                       |
| `INTERNAL_SERVICE_TOKEN` | Service-to-service auth token                                                            | —                                                             |
| `ENCRYPTION_KEY`         | Fernet key for encrypted secret storage, including SMTP passwords and per-agent API keys | —                                                             |
| `USER_SERVICE_URL`       | User service base URL                                                                    | `http://localhost:8090`                                       |
| `RAG_SERVICE_URL`        | RAG service base URL                                                                     | `http://localhost:8083`                                       |
| `KEYCLOAK_SERVER_URL`    | Keycloak base URL                                                                        | `http://localhost:8080`                                       |
| `KEYCLOAK_REALM`         | Keycloak realm                                                                           | `agenticai`                                                   |
| `KEYCLOAK_CLIENT_ID`     | Keycloak client ID for agent-service                                                     | —                                                             |
| `OPENAI_API_KEY`         | OpenAI API key (models: `gpt-4o`, `gpt-4o-mini`)                                         | —                                                             |
| `ANTHROPIC_API_KEY`      | Anthropic API key (models: `claude-sonnet-4`, `claude-haiku-3`)                          | —                                                             |
| `OLLAMA_BASE_URL`        | Ollama server URL                                                                        | `http://localhost:11434`                                      |
| `OLLAMA_DEFAULT_MODEL`   | Default Ollama model                                                                     | `llama3`                                                      |
| `FAKE_MODEL`             | Use mock LLM (no API key needed)                                                         | `false`                                                       |
| `PROXY_SERVICE_API_KEY`  | Proxy API key                                                                            | —                                                             |
| `SERVICE_NAME`           | Service identifier                                                                       | `agent-service`                                               |
| `LOG_LEVEL`              | Logging level                                                                            | `INFO`                                                        |
| `HOST`                   | Server bind address                                                                      | `0.0.0.0`                                                     |
| `PORT`                   | Server port                                                                              | `8080`                                                        |
| `MCP_PORT`               | MCP proxy port                                                                           | `8001`                                                        |
| `AIRBYTE_ENABLED`        | Enable Airbyte datasource sync                                                           | `true`                                                        |
| `AIRBYTE_API_URL`        | Airbyte API base URL                                                                     | `http://localhost:8006`                                       |
| `AIRBYTE_API_USERNAME`   | Airbyte API username                                                                     | `airbyte`                                                     |
| `AIRBYTE_API_PASSWORD`   | Airbyte API password                                                                     | —                                                             |

---

## RAG Service (`apps/rag-service/.env`)

| Variable                 | Description                               | Default                                                       |
| ------------------------ | ----------------------------------------- | ------------------------------------------------------------- |
| `DATABASE_URL`           | PostgreSQL async connection string        | `postgresql+asyncpg://postgres:pass@localhost:5432/agenticai` |
| `MILVUS_HOST`            | Milvus hostname                           | `localhost`                                                   |
| `MILVUS_PORT`            | Milvus port                               | `19530`                                                       |
| `MILVUS_ALIAS`           | Milvus connection alias                   | `default`                                                     |
| `NEO4J_URI`              | Neo4j connection URI                      | `bolt://localhost:7687`                                       |
| `NEO4J_USER`             | Neo4j username                            | `neo4j`                                                       |
| `NEO4J_PASSWORD`         | Neo4j password                            | —                                                             |
| `OLLAMA_BASE_URL`        | Ollama server URL                         | `http://localhost:11434`                                      |
| `EMBEDDING_PROVIDER`     | Embedding provider (`ollama` or `openai`) | `ollama`                                                      |
| `EMBEDDING_MODEL`        | Embedding model name                      | `nomic-embed-text`                                            |
| `OPENAI_API_KEY`         | OpenAI API key for embeddings             | —                                                             |
| `LLM_PROVIDER`           | LLM provider for graph extraction         | `ollama`                                                      |
| `LLM_MODEL`              | LLM model for graph extraction            | `llama3`                                                      |
| `SECRET_KEY`             | JWT verification key                      | —                                                             |
| `INTERNAL_SERVICE_TOKEN` | Service-to-service auth token             | —                                                             |
| `SERVICE_NAME`           | Service identifier                        | `rag-service`                                                 |
| `LOG_LEVEL`              | Logging level                             | `INFO`                                                        |
| `HOST`                   | Server bind address                       | `0.0.0.0`                                                     |
| `PORT`                   | Server port                               | `8083`                                                        |

---

## Tools Service (`apps/tools-service/.env`)

| Variable                 | Description                        | Default                                                       |
| ------------------------ | ---------------------------------- | ------------------------------------------------------------- |
| `DATABASE_URL`           | PostgreSQL async connection string | `postgresql+asyncpg://postgres:pass@localhost:5432/agenticai` |
| `SECRET_KEY`             | JWT verification key               | —                                                             |
| `ALGORITHM`              | JWT algorithm                      | `HS256`                                                       |
| `INTERNAL_SERVICE_TOKEN` | Service-to-service auth token      | —                                                             |
| `USER_SERVICE_URL`       | User service base URL              | `http://localhost:8090`                                       |
| `SERVICE_NAME`           | Service identifier                 | `tools-service`                                               |
| `LOG_LEVEL`              | Logging level                      | `INFO`                                                        |
| `HOST`                   | Server bind address                | `0.0.0.0`                                                     |
| `MCP_PORT`               | MCP server port                    | `8001`                                                        |
| `PYTHON_CMD`             | Python interpreter path            | `python3`                                                     |
| `WORKING_DIR`            | MCP working directory              | `/tmp/mcp`                                                    |
| `ALLOWED_ORIGINS`        | CORS origins                       | `*`                                                           |

---

## Web Frontend (`apps/web/.env`)

| Variable                         | Description                                              | Default                                            |
| -------------------------------- | -------------------------------------------------------- | -------------------------------------------------- |
| `NEXT_PUBLIC_API_URL`            | Browser-facing Kong base URL for compatibility API calls | `http://localhost:8000/api`                        |
| `INTERNAL_URL`                   | Server-side agent-service gateway base                   | `http://localhost:8000/agent-service`              |
| `AGENT_SERVICE_URL`              | Explicit server-side agent-service gateway base          | `http://localhost:8000/agent-service`              |
| `USER_SERVICE_URL`               | Server-side user-service gateway base                    | `http://localhost:8000/user-service`               |
| `LANGCONNECT_URL`                | Server-side RAG gateway base                             | `http://localhost:8000/rag-service`                |
| `MCP_INTERNAL_URL`               | Server-side internal MCP gateway URL                     | `http://localhost:8000/internal/tools-service/mcp` |
| `MCP_SERVER_URL`                 | Browser-facing MCP gateway URL                           | `http://localhost:8000/tools-service/mcp`          |
| `TOOLS_SERVICE_URL`              | Server-side tools-service MCP gateway URL                | `http://localhost:8000/tools-service/mcp`          |
| `NEXT_PUBLIC_WS_URL`             | WebSocket URL for streaming                              | `ws://localhost:8000`                              |
| `NEXT_PUBLIC_KEYCLOAK_URL`       | Keycloak external URL                                    | `http://localhost:8080`                            |
| `NEXT_PUBLIC_KEYCLOAK_REALM`     | Keycloak realm                                           | `agenticai`                                        |
| `NEXT_PUBLIC_KEYCLOAK_CLIENT_ID` | Keycloak client ID for frontend                          | `web-app`                                          |
| `SENTRY_AUTH_TOKEN`              | Sentry auth token (optional)                             | —                                                  |
| `NEXT_PUBLIC_SENTRY_DSN`         | Sentry DSN (optional)                                    | —                                                  |
| `NEXT_PUBLIC_ANALYTICS_ID`       | Analytics ID (optional)                                  | —                                                  |

Sentry is only enabled when **both** `SENTRY_AUTH_TOKEN` and `NEXT_PUBLIC_SENTRY_DSN` are set. If missing, Sentry is no-op.

---

## Startup helper commands

```sh
# Create missing .env files from defaults
make env-init

# Validate all env files have required keys
make env-check
```

---

## Common variable groups across services

### JWT auth (shared by all services)

| Variable                 | Where set             | Purpose                                       |
| ------------------------ | --------------------- | --------------------------------------------- |
| `SECRET_KEY`             | Each service's `.env` | Must match across services for JWT validation |
| `ALGORITHM`              | Each service's `.env` | Usually `HS256`                               |
| `INTERNAL_SERVICE_TOKEN` | Each service's `.env` | Must match across services for internal calls |

### Database (user-service, agent-service)

Both connect to the same PostgreSQL instance. Each has its own `DATABASE_URL` pointing to the same server (schema separation).

### LLM providers (agent-service, rag-service)

| Variable          | agent-service                   | rag-service                      |
| ----------------- | ------------------------------- | -------------------------------- |
| `OPENAI_API_KEY`  | Chat models (GPT-4o)            | Embeddings (text-embedding-3-\*) |
| `OLLAMA_BASE_URL` | Chat models                     | Embeddings + graph LLM           |
| Custom provider   | Per-agent API key storage in DB | Not supported                    |
