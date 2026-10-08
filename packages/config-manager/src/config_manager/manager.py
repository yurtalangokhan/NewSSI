#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import secrets
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock

from dotenv import dotenv_values, load_dotenv

ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "configs").is_dir()),
    Path(__file__).resolve().parents[1],
)
_loaded_paths: set[Path] = set()
_load_lock = Lock()


def load_environment() -> None:
    """Load configs/.env once, preserving process values and purged secrets."""
    explicit = os.environ.get("AGENTICAI_ENV_FILE")
    path = (Path(explicit).expanduser() if explicit else ROOT / "configs/.env").resolve()
    with _load_lock:
        if path in _loaded_paths:
            return
        if explicit and not path.is_file():
            raise FileNotFoundError(f"Central environment file does not exist: {path}")
        if path.is_file():
            load_dotenv(path, override=False, interpolate=False)
        _loaded_paths.add(path)


#: The sole file managed by the CLI and shared runtime loader.
ENV_FILES = ("configs/.env",)

#: Known-weak or placeholder values that must never be accepted as a real
#: configured value, even if a user (or an older generated .env, or a
#: manually-copied example) has already set one of these literally. This is
#: a value-content check on top of check_env_file's existing presence/
#: emptiness checks, which is why it is defined right next to them.
#: Keycloak bootstrap credentials (admin123, Test123!, Admin123!, ...) are
#: deliberately not listed here: Keycloak hardening is out of scope for this
#: pass, and flagging them would just add noise to `check` for a class of
#: default this tool isn't fixing.
FORBIDDEN_VALUES = frozenset(
    {
        "minioadmin",
        "neo4j123",
        "postgres123",
        "dev-internal-service-token-change-me",
        "change-me-in-production-use-at-least-32-chars",
        "your-super-secret-and-long-postgres-password",
        "changeme",
        "password",
    }
)


@dataclass(frozen=True)
class EnvVarSpec:
    name: str
    description: str
    default: str = ""
    required: bool = True
    allow_empty: bool = False
    #: How to produce a value when none is configured: "token" for a
    #: URL-safe random string, "fernet" for a Fernet key. Credentials use
    #: this instead of a literal default so nothing weak ships as a
    #: fallback -- see shared_secret() and generate_value().
    generate: str | None = None
    #: True for a public identifier (a username, not a credential) that
    #: happens to share text with an entry in FORBIDDEN_VALUES -- e.g.
    #: MINIO_ROOT_USER is conventionally "minioadmin", which is only a
    #: problem when it is also the *password*. Excludes this var from the
    #: forbidden-value check without weakening it for actual secrets.
    not_secret: bool = False


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
    forbidden: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing and not self.empty and not self.extra and not self.forbidden


def parse_env_file(path: Path) -> dict[str, str]:
    return {
        key: value
        for key, value in dotenv_values(path, interpolate=False).items()
        if value is not None
    }


def check_env_file(spec: EnvFileSpec) -> EnvCheckResult:
    actual = parse_env_file(spec.path)
    expected = {item.name: item for item in spec.variables}
    missing = tuple(
        item.name for item in spec.variables if item.required and item.name not in actual
    )
    empty = tuple(
        item.name
        for item in spec.variables
        if item.required
        and not item.allow_empty
        and item.name in actual
        and actual[item.name] == ""
    )
    extra = tuple(sorted(key for key in actual if key not in expected))
    # A known-weak or placeholder value is rejected even if it is present
    # and non-empty: "present" is not the same as "safe to run with."
    forbidden = tuple(
        sorted(
            key
            for key, value in actual.items()
            if key in expected and not expected[key].not_secret and value in FORBIDDEN_VALUES
        )
    )
    return EnvCheckResult(spec=spec, missing=missing, empty=empty, extra=extra, forbidden=forbidden)


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
        value = item.default or generate_value(item.generate)
        additions.append(f"# {item.description}")
        additions.append(f"{item.name}={value}")

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
    generate: str | None = None,
    not_secret: bool = False,
) -> EnvVarSpec:
    return EnvVarSpec(
        name=name,
        description=description,
        default=default,
        required=required,
        allow_empty=allow_empty,
        generate=generate,
        not_secret=not_secret,
    )


def generate_token(length: int = 32) -> str:
    """A URL-safe random secret, suitable for tokens and passwords."""
    return secrets.token_urlsafe(length)


def generate_fernet_key() -> str:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        # cryptography is a transitive dependency of every service that
        # needs a real Fernet key; if it is not importable here, fall back
        # to a random urlsafe value of the right shape rather than failing
        # env-init outright. It will not decrypt anything encrypted with a
        # properly-generated key, but it is not a known-weak literal either.
        return generate_token(32)
    return Fernet.generate_key().decode("ascii")


def generate_value(kind: str | None) -> str:
    """Produce a value for a spec's ``generate`` kind, or empty when unset."""
    if kind == "fernet":
        return generate_fernet_key()
    if kind == "token":
        return generate_token()
    return ""


_shared_secret_cache: dict[str, str] = {}


def shared_secret(name: str, kind: str = "token") -> str:
    """Resolve a credential from the process, central file, or a generated value."""
    if name in _shared_secret_cache:
        return _shared_secret_cache[name]

    value = os.environ.get(name, "")
    if not value:
        for candidate in ENV_FILES:
            existing = parse_env_file(ROOT / candidate).get(name, "")
            if existing and existing not in FORBIDDEN_VALUES:
                value = existing
                break
    if not value:
        value = generate_value(kind)

    _shared_secret_cache[name] = value
    return value


def _build_sections() -> dict[str, EnvFileSpec]:
    # No real host ships as a default: DEPLOY_HOST lets an operator point
    # generated env files at a specific host when services do not all run
    # on the same machine; every other deployment gets localhost.
    common_host = os.environ.get("DEPLOY_HOST", "localhost")
    local_postgres_host = "localhost"
    # Credentials more than one env file has to agree on. Resolved once
    # per run so every file receives the same value; see shared_secret().
    internal_token = shared_secret("INTERNAL_SERVICE_TOKEN")
    authentication_secret = shared_secret("AUTHENTICATION_SECRET")
    postgres_password = shared_secret("POSTGRES_PASSWORD")
    neo4j_password = shared_secret("NEO4J_PASSWORD")
    keycloak_admin_password = shared_secret("KEYCLOAK_ADMIN_PASSWORD")
    # MinIO's root user IS its S3-compatible access key (and the root
    # password IS the secret key): app services authenticate to MinIO with
    # the same pair Milvus/MinIO itself is configured with, so both names
    # must resolve to the same generated value, not be generated twice.
    minio_root_user = "minioadmin"  # an identifier, not a secret
    minio_secret = shared_secret("MINIO_ROOT_PASSWORD")
    redis_password = shared_secret("REDIS_PASSWORD")
    grafana_admin_password = shared_secret("GRAFANA_ADMIN_PASSWORD")
    keycloak_base = f"http://{common_host}:8085"
    keycloak_issuer = f"{keycloak_base}/realms/agenticai-v1"

    specs = {
        "configs": EnvFileSpec(
            path=ROOT / "configs/.env",
            title="Infrastructure and APISIX",
            variables=(
                var("POSTGRES_HOST", "Postgres host address for local app services.", common_host),
                var("POSTGRES_PORT", "Host port mapped to infrastructure Postgres.", "8124"),
                # Published infrastructure ports bind to the loopback interface; a
                # shared server that developers reach remotely widens the services it
                # means to (0.0.0.0 or its interface address).
                var(
                    "POSTGRES_BIND_ADDR",
                    "Postgres bind address for the published port.",
                    "127.0.0.1",
                ),
                var("POSTGRES_USER", "Infrastructure Postgres superuser.", "postgres"),
                var("POSTGRES_PASSWORD", "Infrastructure Postgres password.", postgres_password),
                var("OLLAMA_IMAGE_TAG", "Ollama Docker image tag.", "latest"),
                var("OLLAMA_PORT", "Host port mapped to built-in Ollama.", "11434"),
                var("OLLAMA_BIND_ADDR", "Ollama bind address for the published port.", "127.0.0.1"),
                var(
                    "OLLAMA_PRELOAD_MODELS",
                    "Space-separated Ollama models pulled by scripts/pull_ollama_models.sh.",
                    "llama3.1:8b nomic-embed-text",
                ),
                var("LOG_LEVEL", "Shared log level for services.", "INFO"),
                var("LOG_FORMAT", "Shared log format for services (text or JSON).", "JSON"),
                var(
                    "LOG_OUTPUT",
                    "Log destination: console, file, syslog, or elasticsearch.",
                    "console",
                ),
                var(
                    "LOG_INCLUDE_SOURCE",
                    "Whether log records carry module, function, and line.",
                    "true",
                ),
                var(
                    "LOG_QUIET_LOGGERS",
                    "Extra loggers pinned to WARNING, comma-separated.",
                    "",
                    allow_empty=True,
                ),
                var(
                    "LOG_SYSLOG_ADDRESS",
                    "Syslog host:port for the syslog destination.",
                    "localhost:514",
                ),
                var(
                    "LOG_SYSLOG_FACILITY",
                    "Syslog facility for the syslog destination.",
                    "user",
                ),
                var(
                    "LOG_ELASTICSEARCH_INDEX",
                    "Fixed Elasticsearch log index; empty means one index per service.",
                    "",
                    allow_empty=True,
                ),
                var(
                    "LOG_EXTERNAL_URL",
                    "Log platform ingest URL for the elasticsearch destination.",
                    "",
                    allow_empty=True,
                ),
                var(
                    "LOG_EXTERNAL_BEARER_TOKEN",
                    "Bearer credential for the log platform.",
                    "",
                    allow_empty=True,
                ),
                var(
                    "LOG_EXTERNAL_BATCH_SIZE",
                    "Records delivered per log platform call.",
                    "100",
                ),
                var(
                    "LOG_EXTERNAL_FLUSH_INTERVAL",
                    "Seconds a partial log batch waits before delivery.",
                    "5.0",
                ),
                var(
                    "LOG_EXTERNAL_MAX_QUEUE",
                    "Records held before the oldest log record is dropped.",
                    "1000",
                ),
                var(
                    "LOG_EXTERNAL_MAX_RETRIES",
                    "Delivery attempts per log batch before it is counted as lost.",
                    "3",
                ),
                var(
                    "LOG_EXTERNAL_RETRY_BACKOFF",
                    "Seconds before the first log delivery retry; doubles per attempt.",
                    "0.5",
                ),
                var(
                    "LOG_EXTERNAL_SHUTDOWN_TIMEOUT",
                    "Seconds the process waits for a final log flush.",
                    "10.0",
                ),
                var(
                    "OTEL_ENABLED",
                    "Whether services produce OpenTelemetry traces and OTLP metrics.",
                    "false",
                ),
                var(
                    "OTEL_EXPORTER_OTLP_ENDPOINT",
                    "OTLP/http endpoint of the telemetry collector.",
                    "http://otel-collector:4318",
                ),
                var(
                    "OTEL_EXPORTER_OTLP_HEADERS",
                    "Collector credentials as Key=Value pairs, comma-separated.",
                    "",
                    allow_empty=True,
                ),
                var(
                    "OTEL_TRACES_SAMPLE_RATIO",
                    "Fraction of requests traced, 0.0 to 1.0.",
                    "1.0",
                ),
                var(
                    "OTEL_METRICS_ENABLED",
                    "Whether OTLP metrics are exported alongside traces.",
                    "false",
                ),
                var(
                    "OTEL_METRICS_EXPORT_INTERVAL",
                    "Milliseconds between OTLP metric exports.",
                    "60000",
                ),
                var("ELASTIC_VERSION", "Elasticsearch and Kibana image tag.", "8.15.2"),
                var("ELASTICSEARCH_PORT", "Host port mapped to Elasticsearch.", "9200"),
                var("ES_JAVA_OPTS", "Elasticsearch JVM heap settings.", "-Xms512m -Xmx512m"),
                var("KIBANA_PORT", "Host port mapped to Kibana.", "5601"),
                var("PROMETHEUS_VERSION", "Prometheus image tag.", "v2.54.1"),
                var("PROMETHEUS_PORT", "Host port mapped to Prometheus.", "9090"),
                var("GRAFANA_VERSION", "Grafana image tag.", "11.1.0"),
                var("GRAFANA_PORT", "Host port mapped to Grafana.", "3001"),
                var(
                    "GRAFANA_ADMIN_USER",
                    "Grafana admin username for the development stack.",
                    "admin",
                ),
                var(
                    "GRAFANA_ADMIN_PASSWORD",
                    "Grafana admin password for the development stack.",
                    grafana_admin_password,
                ),
                var(
                    "LOG_RETENTION_DAYS",
                    "Days Elasticsearch keeps logs and traces before deleting them.",
                    "30",
                ),
                var("NEO4J_URI", "Neo4j Bolt URI for app services.", f"bolt://{common_host}:8697"),
                var("NEO4J_BIND_ADDR", "Neo4j bind address for the published ports.", "127.0.0.1"),
                var("NEO4J_USERNAME", "Neo4j username.", "neo4j"),
                var("NEO4J_PASSWORD", "Neo4j password.", neo4j_password),
                var("NEO4J_PLUGINS", "Neo4j plugin list.", '["apoc"]'),
                var("NEO4J_HEAP_INITIAL_SIZE", "Neo4j initial heap size.", "512m"),
                var("NEO4J_HEAP_MAX_SIZE", "Neo4j max heap size.", "1g"),
                var("NEO4J_PAGECACHE_SIZE", "Neo4j page cache size.", "512m"),
                var("NEO4J_PROCEDURES_UNRESTRICTED", "Neo4j unrestricted procedures.", "apoc.*"),
                var("NEO4J_PROCEDURES_ALLOWLIST", "Neo4j allowed procedures.", "apoc.*"),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai-v1"),
                var(
                    "KEYCLOAK_ISSUER_URL",
                    "Keycloak issuer URL used by APISIX JWT validation.",
                    keycloak_issuer,
                ),
                var(
                    "KEYCLOAK_CLIENT_ID",
                    "Frontend Keycloak client id bootstrapped by infra.",
                    "web-client",
                ),
                var(
                    "KEYCLOAK_CLIENT_SECRET",
                    "Frontend Keycloak client secret; empty means public client.",
                    "",
                    required=False,
                    allow_empty=True,
                ),
                var(
                    "KEYCLOAK_REDIRECT_URI",
                    "Primary frontend OIDC callback URI.",
                    "http://localhost:3000/auth/oidc/callback",
                ),
                var(
                    "KEYCLOAK_REDIRECT_URIS",
                    "Allowed frontend OIDC callback URIs.",
                    "http://localhost:3000/auth/oidc/callback,http://localhost:3000/*",
                ),
                var(
                    "KEYCLOAK_POST_LOGOUT_REDIRECT_URIS", "Allowed post logout redirect URIs.", "+"
                ),
                var("KEYCLOAK_DB_VENDOR", "Keycloak database vendor.", "postgres"),
                var("KEYCLOAK_DB_HOST", "Keycloak database host inside Docker.", "postgres"),
                var("KEYCLOAK_DB_NAME", "Keycloak database name.", "keycloak"),
                var("KEYCLOAK_ADMIN", "Keycloak bootstrap admin user.", "admin"),
                var(
                    "KEYCLOAK_ADMIN_PASSWORD",
                    "Keycloak bootstrap admin password.",
                    shared_secret("KEYCLOAK_ADMIN_PASSWORD"),
                ),
                var("KEYCLOAK_HEALTH_ENABLED", "Enable Keycloak health endpoints.", "true"),
                var(
                    "KEYCLOAK_HOSTNAME_STRICT",
                    "Disable strict hostname checks in development.",
                    "false",
                ),
                var("KEYCLOAK_WEB_ORIGIN", "Primary frontend web origin.", "http://localhost:3000"),
                var(
                    "KEYCLOAK_WEB_ORIGINS", "Allowed frontend web origins.", "http://localhost:3000"
                ),
                var("KEYCLOAK_TEST_USER", "Bootstrap test username.", "test-user"),
                var("KEYCLOAK_TEST_EMAIL", "Bootstrap test user email.", "test-user@example.com"),
                var(
                    "KEYCLOAK_TEST_PASSWORD",
                    "Bootstrap test user password.",
                    shared_secret("KEYCLOAK_TEST_PASSWORD"),
                ),
                var("KEYCLOAK_DEFAULT_ADMIN_USER", "Bootstrap app admin username.", "admin"),
                var(
                    "KEYCLOAK_DEFAULT_ADMIN_EMAIL",
                    "Bootstrap app admin email.",
                    "admin@example.com",
                ),
                var(
                    "KEYCLOAK_DEFAULT_ADMIN_PASSWORD",
                    "Bootstrap app admin password.",
                    shared_secret("KEYCLOAK_DEFAULT_ADMIN_PASSWORD"),
                ),
                var(
                    "KEYCLOAK_DEFAULT_ADMIN_FIRST_NAME", "Bootstrap app admin first name.", "Admin"
                ),
                var("KEYCLOAK_DEFAULT_ADMIN_LAST_NAME", "Bootstrap app admin last name.", "User"),
                var(
                    "KEYCLOAK_DEFAULT_ADMIN_REALM_ROLE", "Bootstrap app admin realm role.", "admin"
                ),
                var(
                    "KEYCLOAK_PUBLIC_HOSTNAME",
                    "Public hostname advertised by Keycloak.",
                    common_host,
                ),
                var("KEYCLOAK_PUBLIC_PORT", "Public port advertised by Keycloak.", "8085"),
                var(
                    "KEYCLOAK_BIND_ADDR",
                    "Keycloak bind address for the published port; browsers of remote "
                    "developers need it widened or a proxy in front.",
                    "127.0.0.1",
                ),
                var("APP_IMAGE_TAG", "Built application container image tag.", "latest"),
                var("REDIS_HOST_CONTAINER", "Redis host reached by the APISIX container.", "redis"),
                var("APISIX_IMAGE_TAG", "APISIX container image version.", "3.18.0-debian"),
                var("APISIX_HTTP_PORT", "APISIX public HTTP port.", "8000"),
                var("GATEWAY_KEYCLOAK_CLIENT_ID", "Gateway Keycloak client.", "gateway-client"),
                var(
                    "GATEWAY_KEYCLOAK_CLIENT_SECRET",
                    "Gateway Keycloak client secret.",
                    generate="token",
                ),
                var("USER_SERVICE_UPSTREAM_ADDR", "APISIX user-service upstream host:port.", "host.docker.internal:8090"),
                var("AGENT_SERVICE_UPSTREAM_ADDR", "APISIX agent-service upstream host:port.", "host.docker.internal:8123"),
                var("RAG_SERVICE_UPSTREAM_ADDR", "APISIX RAG upstream host:port.", "host.docker.internal:8083"),
                var("TOOLS_SERVICE_UPSTREAM_ADDR", "APISIX tools upstream host:port.", "host.docker.internal:8003"),
                var(
                    "VECTOR_DB_PROVIDER", "Vector database provider used by app services.", "milvus"
                ),
                var("MILVUS_HOST", "Milvus host address for app services.", common_host),
                var("MILVUS_PORT", "Milvus host port.", "9765"),
                var(
                    "MILVUS_USER",
                    "Milvus username; empty when auth is disabled.",
                    "",
                    allow_empty=True,
                ),
                var(
                    "MILVUS_PASSWORD",
                    "Milvus password; empty when auth is disabled.",
                    "",
                    allow_empty=True,
                ),
                var("MILVUS_BIND_ADDR", "Milvus bind address for published ports.", "127.0.0.1"),
                var("MINIO_BIND_ADDR", "MinIO bind address for the published ports.", "127.0.0.1"),
                var("MILVUS_ETCD_ENDPOINTS", "Milvus etcd endpoints.", "etcd:2379"),
                var("MILVUS_MINIO_ADDRESS", "Milvus MinIO address.", "minio:9000"),
                var("MILVUS_ETCD_AUTO_COMPACTION_MODE", "Milvus etcd compaction mode.", "revision"),
                var(
                    "MILVUS_ETCD_AUTO_COMPACTION_RETENTION",
                    "Milvus etcd compaction retention.",
                    "1000",
                ),
                var("MILVUS_ETCD_QUOTA_BACKEND_BYTES", "Milvus etcd quota bytes.", "4294967296"),
                var("MILVUS_ETCD_SNAPSHOT_COUNT", "Milvus etcd snapshot count.", "50000"),
                var(
                    "MINIO_ROOT_USER",
                    "MinIO root username for Milvus object storage.",
                    minio_root_user,
                    not_secret=True,
                ),
                var(
                    "MINIO_ROOT_PASSWORD",
                    "MinIO root password for Milvus object storage.",
                    minio_secret,
                ),
                var("REDIS_HOST", "Redis host for idempotency middleware.", common_host),
                var(
                    "REDIS_CONTAINER_HOST",
                    "Redis host as reached from inside Docker containers (the compose "
                    "service name); REDIS_HOST is the host-side address.",
                    "redis",
                ),
                var("REDIS_PORT", "Redis port for idempotency middleware.", "6379"),
                var("REDIS_BIND_ADDR", "Redis bind address for the published port.", "127.0.0.1"),
                var("REDIS_DB", "Redis database index for idempotency middleware.", "0"),
                var("REDIS_PASSWORD", "Redis password for idempotency middleware.", redis_password),
            ),
        ),
        "web": EnvFileSpec(
            path=ROOT / "configs/.env",
            title="Web app",
            variables=(
                var(
                    "AGENT_SERVICE_URL",
                    "Agent-service API gateway URL, used by every web route that "
                    "calls agent-service.",
                    "http://localhost:8000/agent-service",
                ),
                var(
                    "USER_SERVICE_URL",
                    "User-service API gateway URL.",
                    "http://localhost:8000/user-service",
                ),
                var(
                    "RAG_SERVICE_URL",
                    "RAG-service API gateway URL for web runtime.",
                    "http://localhost:8000/rag-service",
                ),
                var(
                    "MCP_INTERNAL_URL",
                    "MCP gateway URL used by the dev MCP proxy.",
                    "http://localhost:8000/internal/tools-service/mcp",
                ),
                var(
                    "TOOLS_SERVICE_URL",
                    "MCP server URL used by web MCP server metadata.",
                    "http://localhost:8000/tools-service/mcp",
                ),
                var("AUTH_TYPE", "Web authentication mode.", "oidc"),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai-v1"),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL.", keycloak_issuer),
                var("KEYCLOAK_CLIENT_ID", "Frontend Keycloak client id.", "web-client"),
                var("WEB_DOMAIN", "Public web origin.", "http://localhost:3000"),
                var(
                    "OVERRIDE_API_PRODUCTION",
                    "Opt in to the generic /api/* proxy outside development. "
                    "Off by default: a generated .env carried to a production "
                    "build would otherwise open it with nothing else changed.",
                    "false",
                ),
                var(
                    "VALID_API_KEYS",
                    "Development API keys for fallback auth.",
                    shared_secret("VALID_API_KEYS"),
                ),
                var("NEXT_PUBLIC_CLOUD_ENABLED", "Disable cloud-only frontend behavior.", "false"),
                var(
                    "NEXT_PUBLIC_ENABLE_PAID_EE_FEATURES",
                    "Disable paid enterprise frontend behavior.",
                    "false",
                ),
                var("NEXT_PUBLIC_TEST_ENV", "Mark frontend test environment.", "false"),
                var("ATLAS_VERSION", "Web build version stamp.", "dev"),
                var("NEXT_PUBLIC_APP_NAME", "Product name shown in the UI.", "TURKSAT ATLAS"),
                var("NEXT_PUBLIC_APP_URL", "Product URL used in the footer link.", "/"),
                var(
                    "NEXT_PUBLIC_SUPPORT_EMAIL",
                    "Support address shown to users.",
                    "support@example.com",
                ),
                var("NEXT_PUBLIC_APP_DOMAIN", "Tenant sign-up domain suffix.", "atlas.app"),
                var(
                    "NEXT_PUBLIC_POSTHOG_HOST",
                    "PostHog ingestion host.",
                    "https://us.posthog.com",
                ),
                var(
                    "NEXT_PUBLIC_RECAPTCHA_SITE_KEY",
                    "reCAPTCHA site key; empty disables the captcha.",
                    "",
                    allow_empty=True,
                ),
                var("NEXT_PUBLIC_GTM_ENABLED", "Enable Google Tag Manager.", "false"),
                var("NEXT_PUBLIC_ENABLE_STATS", "Enable frontend web-vitals stats.", "false"),
                var("NEXT_PUBLIC_DISABLE_LOGOUT", "Hide the logout action.", "false"),
                var(
                    "NEXT_PUBLIC_FORGOT_PASSWORD_ENABLED",
                    "Offer the forgot-password flow.",
                    "false",
                    # Matches the credential heuristic by spelling only: this is a
                    # feature flag, and every NEXT_PUBLIC_ value ships to the browser.
                    not_secret=True,
                ),
                var(
                    "NEXT_PUBLIC_INCLUDE_ERROR_POPUP_SUPPORT_LINK",
                    "Show a support link in error popups.",
                    "false",
                ),
                var(
                    "NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED",
                    "Hide the powered-by attribution.",
                    "false",
                ),
                var(
                    "ENABLE_PAID_ENTERPRISE_EDITION_FEATURES",
                    "Enable paid enterprise server behavior.",
                    "false",
                ),
            ),
        ),
        "agent-service": EnvFileSpec(
            path=ROOT / "configs/.env",
            title="Agent service",
            variables=(
                var("MODE", "Runtime mode.", "dev"),
                var("PORT", "Agent-service bind port.", "8123"),
                var("POSTGRES_HOST", "Postgres host.", local_postgres_host),
                var("POSTGRES_PORT", "Postgres host port.", "8124"),
                var("POSTGRES_USER", "Postgres user.", "postgres"),
                var("POSTGRES_PASSWORD", "Postgres password.", postgres_password),
                var("POSTGRES_DB", "Agent-service database name.", "agent_service"),
                var("OLLAMA_BASE_URL", "Ollama base URL.", f"http://{common_host}:11434"),
                var("OLLAMA_MODEL", "Default Ollama chat model.", "llama3.1:8b"),
                var("OLLAMA_EMBED_MODEL", "Default Ollama embedding model.", "nomic-embed-text"),
                var("DEFAULT_MODEL", "Default model provider/name.", "llama3.1:8b"),
                var("EMBEDDING_PROVIDER", "Embedding provider.", "ollama"),
                var(
                    "MEMORY_EXTRACTION_MODEL",
                    "Model long-term-memory fact extraction runs on. "
                    "Empty extracts with the conversation's own model.",
                    "",
                    required=False,
                    allow_empty=True,
                ),
                # Prefixed to KEYCLOAK_AGENT_SERVICE_AUDIENCE by build_specs.
                var("KEYCLOAK_AUDIENCE", "Expected Keycloak audience.", "agent-service-client"),
                var(
                    "CONNECTOR_MAX_CONCURRENT_SYNCS",
                    "Connector syncs agent-service runs at the same time.",
                    "1",
                    required=False,
                ),
                var(
                    "CONNECTOR_SYNC_BATCH_SIZE",
                    "Records per batch sent to rag-service during a sync.",
                    "200",
                    required=False,
                ),
                var(
                    "CONNECTOR_SYNC_TIMEOUT_SECONDS",
                    "Fail a connector sync that runs longer than this many seconds; 0 disables.",
                    "86400",
                    required=False,
                ),
                var(
                    "CONNECTOR_SCHEDULER_POLL_SECONDS",
                    "How often the sync scheduler looks for due schedules.",
                    "30",
                    required=False,
                ),
                var(
                    "CONNECTORS_ENABLED",
                    "Comma-separated connector names enabled although hidden by default "
                    "(the ones that read the service's own filesystem).",
                    "",
                    required=False,
                    allow_empty=True,
                ),
                var(
                    "CONNECTORS_DISABLED",
                    "Comma-separated connector names hidden from the catalog.",
                    "",
                    required=False,
                    allow_empty=True,
                ),
                var("NEO4J_URI", "Neo4j Bolt URI.", f"bolt://{common_host}:8697"),
                var("NEO4J_USERNAME", "Neo4j username.", "neo4j"),
                var("NEO4J_PASSWORD", "Neo4j password.", neo4j_password),
                var("VECTOR_DB_PROVIDER", "Vector database provider.", "milvus"),
                var("MILVUS_HOST", "Milvus host.", common_host),
                var("MILVUS_PORT", "Milvus host port.", "9765"),
                var("MILVUS_USER", "Milvus username.", "", allow_empty=True),
                var("MILVUS_PASSWORD", "Milvus password.", "", allow_empty=True),
                var(
                    "INTERNAL_TOOLS_SERVICE_URL",
                    "Tools-service MCP URL through APISIX.",
                    "http://localhost:8000/internal/tools-service/mcp",
                ),
                var(
                    "INTERNAL_RAG_SERVICE_API_URL",
                    "RAG-service internal URL through APISIX.",
                    "http://localhost:8000/internal/rag-service",
                ),
                var(
                    "INTERNAL_USER_SERVICE_URL",
                    "User-service internal URL through APISIX.",
                    "http://localhost:8000/internal/user-service",
                ),
                var("INTERNAL_SERVICE_TOKEN", "Shared service-to-service token.", internal_token),
                var(
                    "AUTHENTICATION_SECRET", "Fallback auth signing secret.", authentication_secret
                ),
                var(
                    "LLM_PROVIDER_API_ENCRYPTION_KEY",
                    "Fernet key for stored LLM provider API keys.",
                    generate="fernet",
                ),
                var(
                    "MCP_CREDENTIAL_ENCRYPTION_KEY",
                    "Fernet key for stored MCP credentials and OAuth tokens.",
                    generate="fernet",
                ),
                var(
                    "MCP_OAUTH_ENCRYPTION_KEY",
                    "Fernet key for stored MCP OAuth client secrets.",
                    generate="fernet",
                ),
                var(
                    "MAIL_CONFIG_ENCRYPTION_KEY",
                    "Fernet key for stored SMTP passwords.",
                    generate="fernet",
                ),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL.", keycloak_issuer),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai-v1"),
                var("CORS_ALLOWED_ORIGINS", "Allowed CORS origins.", "http://localhost:3000"),
                var("REDIS_HOST", "Redis host for idempotency middleware.", common_host),
                var("REDIS_PORT", "Redis port for idempotency middleware.", "6379"),
                var("REDIS_DB", "Redis database index for idempotency middleware.", "0"),
                var("REDIS_PASSWORD", "Redis password for idempotency middleware.", redis_password),
                var("IDEMPOTENCY_TTL", "Idempotency key retention in seconds.", "86400"),
                var("IDEMPOTENCY_ENABLED", "Enable idempotency middleware.", "true"),
                var("IDEMPOTENCY_LOCK_TTL", "Redis lock TTL for in-flight requests.", "10"),
                var("IDEMPOTENCY_WAIT_TIMEOUT", "Wait time for an in-flight replay.", "10.0"),
                var("MINIO_HOST", "MinIO host.", "localhost"),
                var("MINIO_PORT", "MinIO host port.", "10000"),
                var("MINIO_ACCESS_KEY", "MinIO access key.", minio_root_user, not_secret=True),
                var("MINIO_SECRET_KEY", "MinIO secret key.", minio_secret),
                var("MINIO_BUCKET", "Agent document bucket.", "agent-service-documents"),
                var("MINIO_SECURE", "Use HTTPS for MinIO.", "false"),
            ),
        ),
        "rag-service": EnvFileSpec(
            path=ROOT / "configs/.env",
            title="RAG service",
            variables=(
                var("POSTGRES_HOST", "Postgres host.", local_postgres_host),
                var("POSTGRES_PORT", "Postgres host port.", "8124"),
                var("POSTGRES_USER", "Postgres user.", "postgres"),
                var("POSTGRES_PASSWORD", "Postgres password.", postgres_password),
                var("POSTGRES_DB", "RAG-service database name.", "rag_service"),
                var("EMBEDDING_PROVIDER", "Embedding provider.", "ollama"),
                var("OLLAMA_BASE_URL", "Ollama base URL.", f"http://{common_host}:11434"),
                var("OLLAMA_EMBED_MODEL", "Ollama embedding model.", "nomic-embed-text"),
                var("NEO4J_URI", "Neo4j Bolt URI.", f"bolt://{common_host}:8697"),
                var("NEO4J_USERNAME", "Neo4j username.", "neo4j"),
                var("NEO4J_PASSWORD", "Neo4j password.", neo4j_password),
                var("VECTOR_DB_PROVIDER", "Vector database provider.", "milvus"),
                var("MILVUS_HOST", "Milvus host.", common_host),
                var("MILVUS_PORT", "Milvus host port.", "9765"),
                var("MILVUS_USER", "Milvus username.", "", allow_empty=True),
                var("MILVUS_PASSWORD", "Milvus password.", "", allow_empty=True),
                var(
                    "INTERNAL_USER_SERVICE_URL",
                    "User-service internal URL through APISIX.",
                    "http://localhost:8000/internal/user-service",
                ),
                var("INTERNAL_SERVICE_TOKEN", "Shared service-to-service token.", internal_token),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL.", keycloak_issuer),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai-v1"),
                var("REDIS_HOST", "Redis host for idempotency middleware.", common_host),
                var("REDIS_PORT", "Redis port for idempotency middleware.", "6379"),
                var("REDIS_DB", "Redis database index for idempotency middleware.", "0"),
                var("REDIS_PASSWORD", "Redis password for idempotency middleware.", redis_password),
                var("IDEMPOTENCY_TTL", "Idempotency key retention in seconds.", "86400"),
                var("IDEMPOTENCY_ENABLED", "Enable idempotency middleware.", "true"),
                var("IDEMPOTENCY_LOCK_TTL", "Redis lock TTL for in-flight requests.", "10"),
                var("IDEMPOTENCY_WAIT_TIMEOUT", "Wait time for an in-flight replay.", "10.0"),
            ),
        ),
        "user-service": EnvFileSpec(
            path=ROOT / "configs/.env",
            title="User service",
            variables=(
                var("SERVICE_PORT", "Service bind port.", "8090"),
                var("POSTGRES_HOST", "Postgres host.", local_postgres_host),
                var("POSTGRES_PORT", "Postgres host port.", "8124"),
                var("POSTGRES_USER", "Postgres user.", "postgres"),
                var("POSTGRES_PASSWORD", "Postgres password.", postgres_password),
                var("POSTGRES_DB", "User-service database name.", "user_service"),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL.", keycloak_issuer),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai-v1"),
                var("KEYCLOAK_ADMIN", "Keycloak admin username.", "admin"),
                var("KEYCLOAK_ADMIN_PASSWORD", "Keycloak admin password.", keycloak_admin_password),
                var("KEYCLOAK_ADMIN_EMAIL", "Keycloak app admin email.", "admin@agenticai.local"),
                var(
                    "KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL",
                    "Initial user-service admin email.",
                    "admin@agenticai.local",
                ),
                var(
                    "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD",
                    "Initial user-service admin password.",
                    keycloak_admin_password,
                ),
                var(
                    "KEYCLOAK_LOGIN_CLIENT_ID", "Public frontend login client id.", "web-client"
                ),
                var(
                    "KEYCLOAK_CLIENT_ID",
                    "User-service Keycloak client id.",
                    "user-service-client",
                ),
                var(
                    "KEYCLOAK_CLIENT_SECRET",
                    "User-service Keycloak client secret.",
                    allow_empty=True,
                ),
                var("KEYCLOAK_AUDIENCE", "Expected Keycloak audience.", "user-service-client"),
                var(
                    "KEYCLOAK_REDIRECT_URI",
                    "Primary frontend OIDC callback URI.",
                    "http://localhost:3000/auth/oidc/callback",
                ),
                var(
                    "KEYCLOAK_REDIRECT_URIS",
                    "Allowed frontend OIDC callback URIs.",
                    "http://localhost:3000/auth/oidc/callback,http://localhost:3000/*",
                ),
                var(
                    "KEYCLOAK_POST_LOGOUT_REDIRECT_URIS", "Allowed post logout redirect URIs.", "+"
                ),
                var(
                    "KEYCLOAK_WEB_ORIGINS", "Allowed frontend web origins.", "http://localhost:3000"
                ),
                var(
                    "EXTERNAL_KEYCLOAK", "Enable external Keycloak broker.", "false", required=False
                ),
                var(
                    "EXTERNAL_KEYCLOAK_BASE_URL",
                    "External Keycloak base URL.",
                    "",
                    required=False,
                    allow_empty=True,
                ),
                var(
                    "EXTERNAL_KEYCLOAK_ISSUER_URL",
                    "External Keycloak issuer URL.",
                    "",
                    required=False,
                    allow_empty=True,
                ),
                var(
                    "EXTERNAL_KEYCLOAK_REALM",
                    "External Keycloak realm.",
                    "",
                    required=False,
                    allow_empty=True,
                ),
                var(
                    "EXTERNAL_KEYCLOAK_CLIENT_ID",
                    "External Keycloak client id.",
                    "",
                    required=False,
                    allow_empty=True,
                ),
                var(
                    "EXTERNAL_KEYCLOAK_CLIENT_SECRET",
                    "External Keycloak client secret.",
                    "",
                    required=False,
                    allow_empty=True,
                ),
                var(
                    "AUTHENTICATION_SECRET", "Fallback auth signing secret.", authentication_secret
                ),
                var(
                    "USER_API_KEY_ENCRYPTION_KEY",
                    "Fernet key for stored user API key hashes.",
                    generate="fernet",
                ),
                var(
                    "SYSTEM_SETTINGS_ENCRYPTION_KEY",
                    "Fernet key for secrets inside persisted system settings.",
                    generate="fernet",
                ),
                var(
                    "CONNECTOR_CONFIG_ENCRYPTION_KEY",
                    "Fernet key for stored per-user connector configurations.",
                    generate="fernet",
                ),
                var("INTERNAL_SERVICE_TOKEN", "Shared service-to-service token.", internal_token),
                var("CORS_ALLOWED_ORIGINS", "Allowed CORS origins.", "http://localhost:3000"),
                var("REDIS_HOST", "Redis host for idempotency middleware.", common_host),
                var("REDIS_PORT", "Redis port for idempotency middleware.", "6379"),
                var("REDIS_DB", "Redis database index for idempotency middleware.", "0"),
                var("REDIS_PASSWORD", "Redis password for idempotency middleware.", redis_password),
                var("IDEMPOTENCY_TTL", "Idempotency key retention in seconds.", "86400"),
                var("IDEMPOTENCY_ENABLED", "Enable idempotency middleware.", "true"),
                var("IDEMPOTENCY_LOCK_TTL", "Redis lock TTL for in-flight requests.", "10"),
                var("IDEMPOTENCY_WAIT_TIMEOUT", "Wait time for an in-flight replay.", "10.0"),
                var("LOG_LEVEL", "User-service log level.", "INFO"),
                var(
                    "PERMISSION_MANIFEST_ROOT",
                    "Root path for permission manifests.",
                    "/app",
                    required=False,
                    allow_empty=True,
                ),
            ),
        ),
        "tools-service": EnvFileSpec(
            path=ROOT / "configs/.env",
            title="Tools service",
            variables=(
                var("MCP_HOST", "MCP service bind host.", "0.0.0.0"),
                var("MCP_PORT", "MCP service bind port.", "8003"),
                var(
                    "INTERNAL_AGENT_SERVICE_URL",
                    "Agent-service internal connector resolution base URL.",
                    "http://localhost:8000/internal/agent-service/api/v1",
                ),
                # Kept deliberately. tools-service has no database of its own
                # yet, but the connection settings are held ready for planned
                # use, and its REQUIRED_ENV_NAMES still lists them -- a
                # generated .env without these produces a service that cannot
                # boot on its own configuration.
                var("POSTGRES_HOST", "Postgres host.", local_postgres_host),
                var("POSTGRES_PORT", "Postgres host port.", "8124"),
                var("POSTGRES_USER", "Postgres user.", "postgres"),
                var("POSTGRES_PASSWORD", "Postgres password.", postgres_password),
                var("POSTGRES_DB", "Tools-service database name.", "tools_service"),
                var("KEYCLOAK_BASE_URL", "Keycloak public base URL.", keycloak_base),
                var("KEYCLOAK_ISSUER_URL", "Keycloak issuer URL.", keycloak_issuer),
                var("KEYCLOAK_REALM", "Keycloak realm.", "agenticai-v1"),
                var(
                    "INTERNAL_USER_SERVICE_URL",
                    "User-service internal URL through APISIX.",
                    "http://localhost:8000/internal/user-service",
                ),
                var(
                    "INTERNAL_RAG_SERVICE_API_URL",
                    "RAG-service internal URL through APISIX.",
                    "http://localhost:8000/internal/rag-service",
                ),
                var("INTERNAL_SERVICE_TOKEN", "Shared service-to-service token.", internal_token),
            ),
        ),
    }
    return specs


def build_specs() -> dict[str, EnvFileSpec]:
    """Combine service catalogs using the keys in the central configuration."""
    sections = _build_sections()
    variables: dict[str, EnvVarSpec] = {}
    for section in (
        "configs",
        "agent-service",
        "rag-service",
        "user-service",
        "tools-service",
        "web",
    ):
        prefix = section.removesuffix("-service").upper().replace("TOOLS", "TOOL")
        for item in sections[section].variables:
            name = item.name
            if section.endswith("-service"):
                if name in {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}:
                    name = name.replace("POSTGRES_", f"POSTGRES_{prefix}_SERVICE_")
                elif name in {"KEYCLOAK_CLIENT_ID", "KEYCLOAK_CLIENT_SECRET", "KEYCLOAK_AUDIENCE"}:
                    name = name.replace("KEYCLOAK_", f"KEYCLOAK_{prefix}_SERVICE_")
            elif section == "configs" and name in {"POSTGRES_USER", "POSTGRES_PASSWORD"}:
                name = name.replace("POSTGRES_", "POSTGRES_ADMIN_")
            if section == "agent-service" and name == "PORT":
                name = "AGENT_SERVICE_PORT"
            if section == "user-service" and name == "SERVICE_PORT":
                name = "USER_SERVICE_PORT"
            default = item.default
            if name.startswith("POSTGRES_") and name.endswith("_PASSWORD"):
                default = shared_secret(name)
            variables.setdefault(name, replace(item, name=name, default=default))
    for item in (
        var(
            "GATEWAY_URL",
            "Gateway base URL for web auth and catalog calls.",
            "http://localhost:8000",
        ),
        var(
            "INFRA_DOCKER_NETWORK",
            "Docker network of the infrastructure stack that application containers join.",
            "agentic-ai-infrastructure_default",
            required=False,
        ),
        var(
            "GATEWAY_ALLOWED_REDIRECT_URIS",
            "Required JSON array of exact browser callback URLs; configure before startup.",
        ),
        var("GATEWAY_COOKIE_SECURE", "Require HTTPS for Gateway cookies.", "true"),
        var(
            "GATEWAY_EXTERNAL_IDP_ALIAS",
            "Optional Keycloak external identity-provider alias.",
            required=False,
            allow_empty=True,
        ),
        var(
            "GATEWAY_BROKER_URL_REWRITES",
            "Optional JSON object mapping broker URLs to reachable URLs.",
            required=False,
            allow_empty=True,
        ),
        var(
            "GATEWAY_REDIS_DB",
            "Redis database for one-time Gateway OIDC state.",
            "0",
            required=False,
        ),
        var("RAG_SERVICE_PORT", "RAG-service bind port.", "8083"),
        var("TOOLS_SERVICE_PORT", "Tools-service bind port.", "8003"),
        var("ALLOW_ORIGINS", "RAG-service CORS origins.", required=False, allow_empty=True),
        var(
            "KEYCLOAK_AGENT_SERVICE_AUDIENCE",
            "Agent-service Keycloak audience.",
            "agent-service-client",
        ),
        var(
            "KEYCLOAK_AGENT_SERVICE_CLIENT_ID",
            "Agent-service Keycloak client ID.",
            "agent-service-client",
        ),
        var(
            "KEYCLOAK_RAG_SERVICE_CLIENT_ID",
            "RAG-service Keycloak client ID.",
            "rag-service-client",
        ),
        var(
            "KEYCLOAK_TOOLS_SERVICE_CLIENT_ID",
            "Tools-service Keycloak client ID.",
            "tools-service-client",
        ),
    ):
        variables[item.name] = item
    return {
        "configs": EnvFileSpec(
            ROOT / "configs/.env", "Shared service configuration", tuple(variables.values())
        )
    }


def selected_specs(names: list[str]) -> list[EnvFileSpec]:
    known = {
        "all",
        "configs",
        "agent-service",
        "rag-service",
        "user-service",
        "tools-service",
        "web",
    }
    unknown = [name for name in names if name not in known]
    if unknown:
        raise SystemExit(f"Unknown env spec: {', '.join(unknown)}")
    return list(build_specs().values())


def print_result(result: EnvCheckResult) -> None:
    rel_path = result.spec.path.relative_to(ROOT)
    status = "OK" if result.ok else "FAIL"
    print(f"[{status}] {rel_path} - {result.spec.title}")
    if result.missing:
        print("  Missing:")
        for key in result.missing:
            item = next(item for item in result.spec.variables if item.name == key)
            print(f"    {key}: {item.description}")
    if result.empty:
        print("  Empty but required:")
        for key in result.empty:
            item = next(item for item in result.spec.variables if item.name == key)
            print(f"    {key}: {item.description}")
    if result.extra:
        print("  Extra:")
        for key in result.extra:
            print(f"    {key}")
    if result.forbidden:
        print("  Forbidden (known-weak or placeholder) value:")
        for key in result.forbidden:
            item = next(item for item in result.spec.variables if item.name == key)
            print(f"    {key}: {item.description} -- set a real value")


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
    parser = argparse.ArgumentParser(description="Validate the central environment file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Validate env files.")
    check_parser.add_argument("names", nargs="*", default=["all"], help="Env spec names or all.")

    args = parser.parse_args(argv)
    if args.command == "check":
        return check_command(args.names)
    return 2


if __name__ == "__main__":
    sys.exit(main())
