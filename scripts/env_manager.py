#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class EnvVarSpec:
    name: str
    description: str
    default: str = ""
    required: bool = True
    allow_empty: bool = False


@dataclass(frozen=True)
class EnvFileSpec:
    path: Path
    title: str
    variables: tuple[EnvVarSpec, ...]


@dataclass(frozen=True)
class EnvCheckResult:
    spec: EnvFileSpec
    missing: tuple[str, ...]
    empty: tuple[str, ...]
    extra: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.empty and not self.extra


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def check_env_file(spec: EnvFileSpec) -> EnvCheckResult:
    actual = parse_env_file(spec.path)
    expected = {item.name: item for item in spec.variables}
    missing = tuple(item.name for item in spec.variables if item.required and item.name not in actual)
    empty = tuple(
        item.name
        for item in spec.variables
        if item.required
        and not item.allow_empty
        and item.name in actual
        and actual[item.name] == ""
    )
    extra = tuple(sorted(key for key in actual if key not in expected))
    return EnvCheckResult(spec=spec, missing=missing, empty=empty, extra=extra)


def init_env_file(spec: EnvFileSpec) -> None:
    existing = parse_env_file(spec.path)
    spec.path.parent.mkdir(parents=True, exist_ok=True)
    content = spec.path.read_text(encoding="utf-8") if spec.path.exists() else ""
    if content and not content.endswith("\n"):
        content += "\n"

    additions: list[str] = []
    for item in spec.variables:
        if item.name in existing:
            continue
        additions.append(f"# {item.description}")
        additions.append(f"{item.name}={item.default}")

    if additions:
        if content and not content.endswith("\n\n"):
            content += "\n"
        content += "\n".join(additions) + "\n"
        spec.path.write_text(content, encoding="utf-8")
    elif not spec.path.exists():
        spec.path.write_text("", encoding="utf-8")


def var(
    name: str,
    description: str,
    default: str = "",
    *,
    required: bool = True,
    allow_empty: bool = False,
) -> EnvVarSpec:
    return EnvVarSpec(
        name=name,
        description=description,
        default=default,
        required=required,
        allow_empty=allow_empty,
    )


def build_specs() -> dict[str, EnvFileSpec]:
    common_host = "10.101.90.13"
    internal_token = "dev-internal-service-token-change-me"
    auth_secret = "change-me-in-production-use-at-least-32-chars"
    postgres_password = "your-super-secret-and-long-postgres-password"
    keycloak_base = f"http://{common_host}:8085"
    keycloak_issuer = f"{keycloak_base}/realms/agenticai"

    specs = {
        "configs": EnvFileSpec(
            path=ROOT / "configs/.env",
            title="Infrastructure and Kong",
            variables=(
                var("POSTGRES_HOST", "Postgres host address for local app services.", common_host),
                var("POSTGRES_PORT", "Host port mapped to infrastructure Postgres.", "8124"),
                var("POSTGRES_USER", "Infrastructure Postgres superuser.", "postgres"),
                var("POSTGRES_PASSWORD", "Infrastructure Postgres password.", postgres_password),
                var("POSTGRES_DB", "Default database created by Postgres.", "postgres"),
                var("POSTGRES_PGDATA", "Postgres data directory inside the container.", "/var/lib/postgresql/data/pgdata"),
                var("OLLAMA_IMAGE_TAG", "Ollama Docker image tag.", "latest"),
                var("OLLAMA_PORT", "Host port mapped to built-in Ollama.", "11434"),
                var(
                    "OLLAMA_PRELOAD_MODELS",
                    "Space-separated Ollama models pulled during infra startup.",
                    "llama3.1:8b nomic-embed-text",
                ),
                var("NEO4J_URI", "Neo4j Bolt URI for app services.", f"bolt://{common_host}:8697"),
                var("NEO4J_USERNAME", "Neo4j username.", "neo4j"),
                var("NEO4J_PASSWORD", "Neo4j password.", "neo4j123"),
                var("NEO4J_PLUGINS", "Neo4j plugin list.", '["apoc"]'),
                var("NEO4J_HEAP_INITIAL_SIZE", "Neo4j initial heap size.", "512m"),
                var("NEO4J_HEAP_MAX_SIZE", "Neo4j max heap size.", "1g"),
                var("NEO4J_PAGECACHE_SIZE", "Neo4j page cache size.", "512m"),
                var("NEO4J_PROCEDURES_UNRESTRICTED", "Neo4j unrestricted procedures.", "apoc.*"),
                var("NEO4J_PROCEDURES_ALLOWLIST", "Neo4j allowed procedures.", "apoc.*"),
                var("AIRBYTE_VERSION", "Airbyte image version.", "0.50.33"),
                var("AIRBYTE_DATABASE_URL", "Airbyte JDBC database URL.", "jdbc:postgresql://postgres:5432/airbyte"),
                var("AIRBYTE_DB_USER", "Airbyte database user.", "postgres"),
                var("AIRBYTE_DB_PASSWORD", "Airbyte database password.", "airbyte_password"),
                var("AIRBYTE_DB_TYPE", "Airbyte database type.", "postgresql"),
                var("AIRBYTE_DB_PORT", "Airbyte database port inside Docker.", "5432"),
                var("AIRBYTE_DB_SEEDS", "Airbyte database seed host.", "postgres"),
                var("AIRBYTE_DYNAMIC_CONFIG_FILE_PATH", "Airbyte dynamic config path.", "config/dynamicconfig/development.yaml"),
                var("AIRBYTE_RUN_DATABASE_MIGRATION_ON_STARTUP", "Run Airbyte migrations at startup.", "true"),
                var("AIRBYTE_LOG_LEVEL", "Airbyte log level.", "INFO"),
                var("AIRBYTE_ROLE", "Airbyte server role.", "dev"),
                var("AIRBYTE_TRACKING_STRATEGY", "Airbyte tracking strategy.", "logging"),
                var("AIRBYTE_TEMPORAL_HOST", "Airbyte Temporal host.", "airbyte-temporal:7233"),
                var("AIRBYTE_INTERNAL_API_HOST", "Airbyte internal API host.", "airbyte-server:8001"),
                var("AIRBYTE_WEBAPP_URL", "Airbyte web app URL.", "http://localhost:8010"),
                var("AIRBYTE_CONNECTOR_BUILDER_API_HOST", "Airbyte connector builder API host.", "airbyte-server:8001"),
                var("AIRBYTE_WORKER_ENVIRONMENT", "Airbyte worker runtime.", "docker"),
                var("AIRBYTE_WORKSPACE_ROOT", "Airbyte workspace root.", "/tmp/workspace"),
                var("AIRBYTE_CONFIG_ROOT", "Airbyte config root.", "/data/config"),
                var("AIRBYTE_LOCAL_ROOT", "Airbyte local root.", "/tmp/airbyte_local"),
                var("AIRBYTE_DEPLOYMENT_MODE", "Airbyte deployment mode.", "OSS"),
                var("AIRBYTE_SECRET_PERSISTENCE", "Airbyte secret persistence mode.", "NONE"),
                var("AIRBYTE_CONFIGS_DATABASE_MINIMUM_FLYWAY_MIGRATION_VERSION", "Airbyte config DB minimum migration version.", "0"),
                var("AIRBYTE_JOBS_DATABASE_MINIMUM_FLYWAY_MIGRATION_VERSION", "Airbyte jobs DB minimum migration version.", "0"),
                var("AIRBYTE_MICRONAUT_ENVIRONMENTS", "Airbyte Micronaut environments.", "control-plane"),
                var("AIRBYTE_DOCKER_NETWORK", "Shared Docker network for infra and apps.", "agentic-ai-infrastructure_default"),
                var("AIRBYTE_MAX_SYNC_WORKERS", "Airbyte max sync workers.", "5"),
                var("AIRBYTE_MAX_CHECK_WORKERS", "Airbyte max check workers.", "5"),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai"),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL used by Kong JWT validation.", keycloak_issuer),
                var("KEYCLOAK_CLIENT_ID", "Frontend Keycloak client id bootstrapped by infra.", "agenticai-web"),
                var("KEYCLOAK_CLIENT_SECRET", "Frontend Keycloak client secret; empty means public client.", "", allow_empty=True),
                var("KEYCLOAK_REDIRECT_URI", "Primary frontend OIDC callback URI.", f"http://{common_host}:3000/auth/oidc/callback"),
                var("KEYCLOAK_REDIRECT_URIS", "Allowed frontend OIDC callback URIs.", f"http://localhost:3000/auth/oidc/callback,http://localhost:3000/*,http://{common_host}:3000/auth/oidc/callback,http://{common_host}:3000/*"),
                var("KEYCLOAK_POST_LOGOUT_REDIRECT_URIS", "Allowed post logout redirect URIs.", "+"),
                var("KEYCLOAK_DB_VENDOR", "Keycloak database vendor.", "postgres"),
                var("KEYCLOAK_DB_HOST", "Keycloak database host inside Docker.", "postgres"),
                var("KEYCLOAK_DB_NAME", "Keycloak database name.", "keycloak"),
                var("KEYCLOAK_ADMIN", "Keycloak bootstrap admin user.", "admin"),
                var("KEYCLOAK_ADMIN_PASSWORD", "Keycloak bootstrap admin password.", "admin123"),
                var("KEYCLOAK_HEALTH_ENABLED", "Enable Keycloak health endpoints.", "true"),
                var("KEYCLOAK_HOSTNAME_STRICT", "Disable strict hostname checks in development.", "false"),
                var("KEYCLOAK_WEB_ORIGIN", "Primary frontend web origin.", f"http://{common_host}:3000"),
                var("KEYCLOAK_WEB_ORIGINS", "Allowed frontend web origins.", f"http://localhost:3000,http://{common_host}:3000"),
                var("KEYCLOAK_TEST_USER", "Bootstrap test username.", "test-user"),
                var("KEYCLOAK_TEST_EMAIL", "Bootstrap test user email.", "test-user@example.com"),
                var("KEYCLOAK_TEST_PASSWORD", "Bootstrap test user password.", "Test123!"),
                var("KEYCLOAK_DEFAULT_ADMIN_USER", "Bootstrap app admin username.", "admin"),
                var("KEYCLOAK_DEFAULT_ADMIN_EMAIL", "Bootstrap app admin email.", "admin@example.com"),
                var("KEYCLOAK_DEFAULT_ADMIN_PASSWORD", "Bootstrap app admin password.", "Admin123!"),
                var("KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME", "Bootstrap app admin first name.", "Admin"),
                var("KEYCLOAK_DEFAULT_ADMIN_LAST_NAME", "Bootstrap app admin last name.", "User"),
                var("KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE", "Bootstrap app admin realm role.", "admin"),
                var("KEYCLOAK_PUBLIC_HOSTNAME", "Public hostname advertised by Keycloak.", common_host),
                var("KEYCLOAK_PUBLIC_PORT", "Public port advertised by Keycloak.", "8085"),
                var("KONG_DATABASE", "Kong database mode.", "off"),
                var("KONG_DECLARATIVE_CONFIG", "Kong rendered declarative config path.", "/tmp/kong.yml"),
                var("KONG_DNS_ORDER", "Kong DNS lookup order.", "LAST,A,CNAME"),
                var("KONG_LOG_LEVEL", "Kong log level.", "notice"),
                var("KONG_ADMIN_LISTEN", "Kong admin listener.", "0.0.0.0:8001"),
                var("KONG_PROXY_LISTEN", "Kong proxy listener.", "0.0.0.0:8000"),
                var("KONG_ADMIN_ACCESS_LOG", "Kong admin access log target.", "/dev/stdout"),
                var("KONG_ADMIN_ERROR_LOG", "Kong admin error log target.", "/dev/stderr"),
                var("KONG_PROXY_ACCESS_LOG", "Kong proxy access log target.", "/dev/stdout"),
                var("KONG_PROXY_ERROR_LOG", "Kong proxy error log target.", "/dev/stderr"),
                var("USER_SERVICE_UPSTREAM_URL", "Kong upstream URL for user-service.", "http://host.docker.internal:8090"),
                var("AGENT_SERVICE_UPSTREAM_URL", "Kong upstream URL for agent-service.", "http://host.docker.internal:8123"),
                var("RAG_SERVICE_UPSTREAM_URL", "Kong upstream URL for rag-service.", "http://host.docker.internal:8083"),
                var("TOOLS_SERVICE_UPSTREAM_URL", "Kong upstream URL for tools-service.", "http://host.docker.internal:8003"),
                var("VECTOR_DB_PROVIDER", "Vector database provider used by app services.", "milvus"),
                var("MILVUS_HOST", "Milvus host address for app services.", common_host),
                var("MILVUS_PORT", "Milvus host port.", "9765"),
                var("MILVUS_USER", "Milvus username; empty when auth is disabled.", "", allow_empty=True),
                var("MILVUS_PASSWORD", "Milvus password; empty when auth is disabled.", "", allow_empty=True),
                var("MILVUS_BIND_ADDR", "Milvus bind address for published ports.", "0.0.0.0"),
                var("MILVUS_ETCD_ENDPOINTS", "Milvus etcd endpoints.", "etcd:2379"),
                var("MILVUS_MINIO_ADDRESS", "Milvus MinIO address.", "minio:9000"),
                var("MILVUS_ETCD_AUTO_COMPACTION_MODE", "Milvus etcd compaction mode.", "revision"),
                var("MILVUS_ETCD_AUTO_COMPACTION_RETENTION", "Milvus etcd compaction retention.", "1000"),
                var("MILVUS_ETCD_QUOTA_BACKEND_BYTES", "Milvus etcd quota bytes.", "4294967296"),
                var("MILVUS_ETCD_SNAPSHOT_COUNT", "Milvus etcd snapshot count.", "50000"),
                var("MINIO_ROOT_USER", "MinIO root username for Milvus object storage.", "minioadmin"),
                var("MINIO_ROOT_PASSWORD", "MinIO root password for Milvus object storage.", "minioadmin"),
                var("REDIS_HOST", "Redis host for idempotency middleware.", common_host),
                var("REDIS_PORT", "Redis port for idempotency middleware.", "6379"),
                var("REDIS_DB", "Redis database index for idempotency middleware.", "0"),
                var("REDIS_PASSWORD", "Redis password for idempotency middleware.", "", allow_empty=True),
            ),
        ),
        "web": EnvFileSpec(
            path=ROOT / "apps/web/.env",
            title="Web app",
            variables=(
                var("INTERNAL_URL", "Agent-service API gateway URL.", "http://localhost:8000"),
                var("AGENT_SERVICE_URL", "Agent-service API gateway URL for agent proxy routes.", "http://localhost:8000"),
                var("USER_SERVICE_URL", "User-service API gateway URL.", "http://localhost:8000"),
                var("LANGCONNECT_URL", "RAG-service API gateway URL.", "http://localhost:8000"),
                var("MCP_INTERNAL_URL", "MCP gateway URL used by the dev MCP proxy.", "http://localhost:8000/internal/mcp"),
                var("MCP_SERVER_URL", "MCP gateway URL shown to backend providers.", "http://localhost:8000/api/mcp"),
                var("TOOLS_SERVICE_URL", "MCP server URL used by web MCP server metadata.", "http://localhost:8000/api/mcp"),
                var("AUTH_TYPE", "Web authentication mode.", "oidc"),
                var("KEYCLOAK_ENABLED", "Enable Keycloak/OIDC in web routes.", "true"),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai"),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL.", keycloak_issuer),
                var("KEYCLOAK_CLIENT_ID", "Frontend Keycloak client id.", "agenticai-web"),
                var("OLLAMA_URL", "Ollama URL for admin helper routes.", f"http://{common_host}:11434"),
                var("WEB_DOMAIN", "Public web origin.", f"http://{common_host}:3000"),
                var("NODE_ENV", "Node runtime environment.", "development"),
                var("OVERRIDE_API_PRODUCTION", "Allow local API proxy in development-style production runs.", "true"),
                var("VALID_API_KEYS", "Development API keys for fallback auth.", "dev-key-123,prod-key-456"),
                var("NEXT_PUBLIC_CLOUD_ENABLED", "Disable cloud-only frontend behavior.", "false"),
                var("NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES", "Disable paid enterprise frontend behavior.", "false"),
                var("NEXT_PUBLIC_TEST_ENV", "Mark frontend test environment.", "false"),
                var("EE_ENABLED", "Disable enterprise-only server behavior.", "false"),
                var("SHOW_EXTRA_CONNECTORS", "Hide extra connector experiments.", "false"),
            ),
        ),
        "agent-service": EnvFileSpec(
            path=ROOT / "apps/agent-service/.env",
            title="Agent service",
            variables=(
                var("DATABASE_TYPE", "Checkpoint/database backend type.", "postgres"),
                var("MODE", "Runtime mode.", "dev"),
                var("PORT", "Agent-service bind port.", "8123"),
                var("POSTGRES_HOST", "Postgres host.", common_host),
                var("POSTGRES_PORT", "Postgres host port.", "8124"),
                var("POSTGRES_USER", "Postgres user.", "postgres"),
                var("POSTGRES_PASSWORD", "Postgres password.", postgres_password),
                var("POSTGRES_DB", "Agent-service database name.", "agent_service"),
                var("OLLAMA_BASE_URL", "Ollama base URL.", f"http://{common_host}:11434"),
                var("OLLAMA_MODEL", "Default Ollama chat model.", "llama3.1:8b"),
                var("OLLAMA_EMBED_MODEL", "Default Ollama embedding model.", "nomic-embed-text"),
                var("DEFAULT_MODEL", "Default model provider/name.", "ollama"),
                var("EMBEDDING_PROVIDER", "Embedding provider.", "ollama"),
                var("AIRBYTE_API_URL", "Airbyte API URL.", f"http://{common_host}:8001/api/v1"),
                var("AIRBYTE_SYNC_POLL_INTERVAL_SECONDS", "Airbyte sync polling interval.", "30"),
                var("AIRBYTE_LOCAL_OUTPUT_PATH", "Airbyte local file output mount.", "/tmp/airbyte_local"),
                var("NEO4J_URI", "Neo4j Bolt URI.", f"bolt://{common_host}:8697"),
                var("NEO4J_USERNAME", "Neo4j username.", "neo4j"),
                var("NEO4J_PASSWORD", "Neo4j password.", "neo4j123"),
                var("VECTOR_DB_PROVIDER", "Vector database provider.", "milvus"),
                var("MILVUS_HOST", "Milvus host.", common_host),
                var("MILVUS_PORT", "Milvus host port.", "9765"),
                var("MILVUS_USER", "Milvus username.", "", allow_empty=True),
                var("MILVUS_PASSWORD", "Milvus password.", "", allow_empty=True),
                var("TOOLS_SERVICE_URL", "Tools-service MCP URL through Kong.", "http://localhost:8000/internal/mcp"),
                var("MCP_SERVER_URL", "Tools-service MCP URL through Kong.", "http://localhost:8000/internal/mcp"),
                var("RAG_SERVICE_API_URL", "RAG-service internal URL through Kong.", "http://localhost:8000/internal/rag-service"),
                var("RAG_API_URL", "RAG-service internal URL through Kong.", "http://localhost:8000/internal/rag-service"),
                var("USER_SERVICE_URL", "User-service internal URL through Kong.", "http://localhost:8000/internal/user-service"),
                var("INTERNAL_SERVICE_TOKEN", "Shared service-to-service token.", internal_token),
                var("AUTH_SECRET", "Fallback auth signing secret.", auth_secret),
                var("KEYCLOAK_ENABLED", "Enable Keycloak auth.", "true"),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL.", keycloak_issuer),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai"),
                var("KEYCLOAK_CLIENT_ID", "Agent-service Keycloak client id.", "agent-service"),
                var("KEYCLOAK_CLIENT_SECRET", "Agent-service Keycloak client secret."),
                var("KEYCLOAK_AUDIENCE", "Expected Keycloak audience.", "agent-service"),
                var("REDIS_HOST", "Redis host for idempotency middleware.", common_host),
                var("REDIS_PORT", "Redis port for idempotency middleware.", "6379"),
                var("REDIS_DB", "Redis database index for idempotency middleware.", "0"),
                var("REDIS_PASSWORD", "Redis password for idempotency middleware.", "", allow_empty=True),
                var("IDEMPOTENCY_TTL", "Idempotency key retention in seconds.", "86400"),
                var("IDEMPOTENCY_ENABLED", "Enable idempotency middleware.", "true"),
                var("MINIO_HOST", "MinIO host.", "localhost"),
                var("MINIO_PORT", "MinIO host port.", "10000"),
                var("MINIO_ACCESS_KEY", "MinIO access key.", "minioadmin"),
                var("MINIO_SECRET_KEY", "MinIO secret key.", "minioadmin"),
                var("MINIO_BUCKET", "Agent document bucket.", "agent-service-documents"),
                var("MINIO_SECURE", "Use HTTPS for MinIO.", "false"),
            ),
        ),
        "rag-service": EnvFileSpec(
            path=ROOT / "apps/rag-service/.env",
            title="RAG service",
            variables=(
                var("POSTGRES_HOST", "Postgres host.", common_host),
                var("POSTGRES_PORT", "Postgres host port.", "8124"),
                var("POSTGRES_USER", "Postgres user.", "postgres"),
                var("POSTGRES_PASSWORD", "Postgres password.", postgres_password),
                var("POSTGRES_DB", "RAG-service database name.", "rag_service"),
                var("ALLOW_ORIGINS", "CORS allowed origins.", '["*"]'),
                var("EMBEDDING_PROVIDER", "Embedding provider.", "ollama"),
                var("OLLAMA_BASE_URL", "Ollama base URL.", f"http://{common_host}:11434"),
                var("OLLAMA_EMBED_MODEL", "Ollama embedding model.", "nomic-embed-text"),
                var("NEO4J_URI", "Neo4j Bolt URI.", f"bolt://{common_host}:8697"),
                var("NEO4J_USERNAME", "Neo4j username.", "neo4j"),
                var("NEO4J_PASSWORD", "Neo4j password.", "neo4j123"),
                var("VECTOR_DB_PROVIDER", "Vector database provider.", "milvus"),
                var("MILVUS_HOST", "Milvus host.", common_host),
                var("MILVUS_PORT", "Milvus host port.", "9765"),
                var("MILVUS_USER", "Milvus username.", "", allow_empty=True),
                var("MILVUS_PASSWORD", "Milvus password.", "", allow_empty=True),
                var("USER_SERVICE_URL", "User-service internal URL through Kong.", "http://localhost:8000/internal/user-service"),
                var("INTERNAL_SERVICE_TOKEN", "Shared service-to-service token.", internal_token),
                var("KEYCLOAK_ENABLED", "Enable Keycloak auth.", "true"),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL.", keycloak_issuer),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai"),
                var("KEYCLOAK_CLIENT_ID", "RAG-service Keycloak client id.", "rag-service"),
                var("KEYCLOAK_CLIENT_SECRET", "RAG-service Keycloak client secret."),
                var("KEYCLOAK_AUDIENCE", "Expected Keycloak audience.", "rag-service"),
                var("REDIS_HOST", "Redis host for idempotency middleware.", common_host),
                var("REDIS_PORT", "Redis port for idempotency middleware.", "6379"),
                var("REDIS_DB", "Redis database index for idempotency middleware.", "0"),
                var("REDIS_PASSWORD", "Redis password for idempotency middleware.", "", allow_empty=True),
                var("IDEMPOTENCY_TTL", "Idempotency key retention in seconds.", "86400"),
                var("IDEMPOTENCY_ENABLED", "Enable idempotency middleware.", "true"),
            ),
        ),
        "user-service": EnvFileSpec(
            path=ROOT / "apps/user-service/.env",
            title="User service",
            variables=(
                var("SERVICE_NAME", "Service name used in JWT audience defaults.", "user-service"),
                var("SERVICE_HOST", "Service bind host.", "0.0.0.0"),
                var("SERVICE_PORT", "Service bind port.", "8090"),
                var("POSTGRES_HOST", "Postgres host.", common_host),
                var("POSTGRES_PORT", "Postgres host port.", "8124"),
                var("POSTGRES_USER", "Postgres user.", "postgres"),
                var("POSTGRES_PASSWORD", "Postgres password.", postgres_password),
                var("POSTGRES_DB", "User-service database name.", "user_service"),
                var("KEYCLOAK_ENABLED", "Enable Keycloak auth.", "true"),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL.", keycloak_issuer),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai"),
                var("KEYCLOAK_ADMIN", "Keycloak admin username.", "admin"),
                var("KEYCLOAK_ADMIN_PASSWORD", "Keycloak admin password.", "admin123"),
                var("KEYCLOAK_ADMIN_EMAIL", "Keycloak app admin email.", "admin@agenticai.local"),
                var("KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL", "Initial user-service admin email.", "admin@agenticai.local"),
                var("KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD", "Initial user-service admin password.", "admin123"),
                var("KEYCLOAK_LOGIN_CLIENT_ID", "Public frontend login client id.", "agenticai-web"),
                var("KEYCLOAK_CLIENT_ID", "User-service Keycloak client id.", "user-service"),
                var("KEYCLOAK_CLIENT_SECRET", "User-service Keycloak client secret."),
                var("KEYCLOAK_AUDIENCE", "Expected Keycloak audience.", "user-service"),
                var("KEYCLOAK_REDIRECT_URI", "Primary frontend OIDC callback URI.", f"http://{common_host}:3000/auth/oidc/callback"),
                var("KEYCLOAK_REDIRECT_URIS", "Allowed frontend OIDC callback URIs.", f"http://localhost:3000/auth/oidc/callback,http://localhost:3000/*,http://{common_host}:3000/auth/oidc/callback,http://{common_host}:3000/*"),
                var("KEYCLOAK_POST_LOGOUT_REDIRECT_URIS", "Allowed post logout redirect URIs.", "+"),
                var("KEYCLOAK_WEB_ORIGINS", "Allowed frontend web origins.", f"http://localhost:3000,http://{common_host}:3000"),
                var("EXTERNAL_KEYCLOAK", "Enable external Keycloak broker.", "false"),
                var("EXTERNAL_KEYCLOAK_BASE_URL", "External Keycloak base URL.", "", required=False, allow_empty=True),
                var("EXTERNAL_KEYCLOAK_ISSUER_URL", "External Keycloak issuer URL.", "", required=False, allow_empty=True),
                var("EXTERNAL_KEYCLOAK_REALM", "External Keycloak realm.", "", required=False, allow_empty=True),
                var("EXTERNAL_KEYCLOAK_CLIENT_ID", "External Keycloak client id.", "", required=False, allow_empty=True),
                var("EXTERNAL_KEYCLOAK_CLIENT_SECRET", "External Keycloak client secret.", "", required=False, allow_empty=True),
                var("AUTH_SECRET", "Fallback auth signing secret.", auth_secret),
                var("ENCRYPTION_KEY", "Fernet key for persisted secrets."),
                var("INTERNAL_SERVICE_TOKEN", "Shared service-to-service token.", internal_token),
                var("CORS_ALLOWED_ORIGINS", "Allowed CORS origins.", f"http://localhost:3000,http://{common_host}:3000"),
                var("REDIS_HOST", "Redis host for idempotency middleware.", common_host),
                var("REDIS_PORT", "Redis port for idempotency middleware.", "6379"),
                var("REDIS_DB", "Redis database index for idempotency middleware.", "0"),
                var("REDIS_PASSWORD", "Redis password for idempotency middleware.", "", allow_empty=True),
                var("IDEMPOTENCY_TTL", "Idempotency key retention in seconds.", "86400"),
                var("IDEMPOTENCY_ENABLED", "Enable idempotency middleware.", "true"),
                var("LOG_LEVEL", "User-service log level.", "INFO"),
                var("LDAP_ENABLED", "Enable LDAP login.", "false"),
                var("LDAP_HOST", "LDAP host.", "localhost", required=False),
                var("LDAP_PORT", "LDAP port.", "389", required=False),
                var("LDAP_USE_TLS", "Use TLS for LDAP.", "false", required=False),
                var("LDAP_BIND_DN", "LDAP bind DN.", "", required=False, allow_empty=True),
                var("LDAP_BIND_PASSWORD", "LDAP bind password.", "", required=False, allow_empty=True),
                var("LDAP_BASE_DN", "LDAP base DN.", "dc=example,dc=com", required=False),
                var("LDAP_USER_SEARCH_FILTER", "LDAP user search filter.", "(&(objectClass=person)(uid={{username}}))", required=False),
                var("LDAP_ATTRIBUTE_MAP", "LDAP user attribute JSON map.", '{"username": "uid", "email": "mail", "first_name": "givenName", "last_name": "sn"}', required=False),
            ),
        ),
        "tools-service": EnvFileSpec(
            path=ROOT / "apps/tools-service/.env",
            title="Tools service",
            variables=(
                var("MCP_HOST", "MCP service bind host.", "0.0.0.0"),
                var("MCP_PORT", "MCP service bind port.", "8003"),
                var("POSTGRES_HOST", "Postgres host.", common_host),
                var("POSTGRES_PORT", "Postgres host port.", "8124"),
                var("POSTGRES_USER", "Postgres user.", "postgres"),
                var("POSTGRES_PASSWORD", "Postgres password.", postgres_password),
                var("POSTGRES_DB", "Tools-service database name.", "tools_service"),
                var("KEYCLOAK_ENABLED", "Enable Keycloak auth.", "true"),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL.", keycloak_issuer),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai"),
                var("KEYCLOAK_CLIENT_ID", "Tools-service Keycloak client id.", "tools-service"),
                var("KEYCLOAK_CLIENT_SECRET", "Tools-service Keycloak client secret."),
                var("KEYCLOAK_AUDIENCE", "Expected Keycloak audience.", "tools-service"),
                var("USER_SERVICE_URL", "User-service internal URL through Kong.", "http://localhost:8000/internal/user-service"),
                var("RAG_SERVICE_API_URL", "RAG-service internal URL through Kong.", "http://localhost:8000/internal/rag-service"),
                var("INTERNAL_SERVICE_TOKEN", "Shared service-to-service token.", internal_token),
            ),
        ),
    }
    return specs


def selected_specs(names: list[str]) -> list[EnvFileSpec]:
    specs = build_specs()
    if not names or names == ["all"]:
        return list(specs.values())
    unknown = [name for name in names if name not in specs]
    if unknown:
        known = ", ".join(sorted(specs))
        raise SystemExit(f"Unknown env spec: {', '.join(unknown)}. Known specs: {known}")
    return [specs[name] for name in names]


def print_result(result: EnvCheckResult) -> None:
    rel_path = result.spec.path.relative_to(ROOT)
    status = "OK" if result.ok else "FAIL"
    print(f"[{status}] {rel_path} - {result.spec.title}")
    if result.missing:
        print("  Missing:")
        for key in result.missing:
            item = next(item for item in result.spec.variables if item.name == key)
            print(f"    {key}: {item.description} Suggested: {item.default!r}")
    if result.empty:
        print("  Empty but required:")
        for key in result.empty:
            item = next(item for item in result.spec.variables if item.name == key)
            print(f"    {key}: {item.description}")
    if result.extra:
        print("  Extra:")
        for key in result.extra:
            print(f"    {key}")


def check_command(names: list[str]) -> int:
    results = [check_env_file(spec) for spec in selected_specs(names)]
    for result in results:
        print_result(result)
    return 0 if all(result.ok for result in results) else 1


def init_command(names: list[str]) -> int:
    for spec in selected_specs(names):
        init_env_file(spec)
    return check_command(names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and initialize project env files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Validate env files.")
    check_parser.add_argument("names", nargs="*", default=["all"], help="Env spec names or all.")

    init_parser = subparsers.add_parser("init", help="Create missing env files and keys.")
    init_parser.add_argument("names", nargs="*", default=["all"], help="Env spec names or all.")

    args = parser.parse_args(argv)
    if args.command == "check":
        return check_command(args.names)
    if args.command == "init":
        return init_command(args.names)
    return 2


if __name__ == "__main__":
    sys.exit(main())
