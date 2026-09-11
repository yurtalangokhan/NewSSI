from enum import StrEnum

from pydantic import AliasChoices, AnyHttpUrl, Field, TypeAdapter, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseType(StrEnum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"
    MONGO = "mongo"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def to_logging_level(self) -> int:
        mapping = {
            LogLevel.DEBUG: 10,
            LogLevel.INFO: 20,
            LogLevel.WARNING: 30,
            LogLevel.ERROR: 40,
            LogLevel.CRITICAL: 50,
        }
        return mapping[self]


def check_str_is_http(value: str) -> str:
    """Validate and normalize an HTTP(S) URL string."""
    return str(TypeAdapter(AnyHttpUrl).validate_python(value))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        validate_default=False,
    )

    MODE: str | None = None
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    GRACEFUL_SHUTDOWN_TIMEOUT: int = 30
    # LangGraph's own default (25) counts every model call + tool call as a
    # graph "step" — a deep-research agent doing several rounds of parallel
    # web_search/fetch_webpage calls burns through that in a handful of
    # rounds and gets killed by GraphRecursionError mid-turn.
    AGENT_RECURSION_LIMIT: int = 150
    # How long an SSE stream may stay silent before a keep-alive comment is
    # sent. Must stay well under the read timeout of anything proxying the
    # stream (Kong defaults to 60s), because a model writing a long document
    # emits nothing for minutes on providers that only deliver completed
    # tool calls.
    STREAM_HEARTBEAT_SECONDS: int = 15
    LOG_LEVEL: LogLevel = LogLevel.WARNING
    LOG_FORMAT: str = "text"
    AUTH_SECRET: str | None = None

    # Keycloak / OIDC authentication
    KEYCLOAK_ENABLED: bool = False
    KEYCLOAK_ISSUER_URL: str | None = None
    KEYCLOAK_BASE_URL: str | None = None
    KEYCLOAK_REALM: str = "agenticai"
    KEYCLOAK_CLIENT_ID: str = "agenticai-web"
    KEYCLOAK_CLIENT_SECRET: str | None = None
    KEYCLOAK_AUDIENCE: str | None = None
    KEYCLOAK_TOKEN_LEEWAY_SECONDS: int = 120
    KEYCLOAK_ADMIN_EMAIL: str | None = None

    # Fallback / internal auth
    VALID_API_KEYS: str | None = None
    INTERNAL_SERVICE_TOKEN: str | None = None

    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    DEFAULT_MODEL: str = "llama3.1:8b"
    EMBEDDING_PROVIDER: str = "ollama"

    COMPATIBLE_MODEL: str | None = None
    COMPATIBLE_API_KEY: str | None = None
    COMPATIBLE_BASE_URL: str | None = None

    # Applied to every provider-backed chat model. The library defaults vary
    # wildly (langchain-google-genai retries 6x with 2→64s backoff, the OpenAI
    # client has no read timeout at all), so a stalled upstream can silently
    # hang an SSE turn for minutes — past the proxy read timeout. Override per
    # deployment; set the timeout to 0 to fall back to the library default.
    LLM_MAX_RETRIES: int = 2
    LLM_REQUEST_TIMEOUT: float = 600.0

    # Provider-specific LLM tuning. Extended-thinking token budgets for the
    # providers that take an explicit budget (Anthropic also forces
    # temperature == 1 whenever thinking is on).
    LLM_ANTHROPIC_THINKING_BUDGET_TOKENS: int = 8_000
    LLM_GEMINI_THINKING_BUDGET_TOKENS: int = 8_000
    # reasoning_effort sent to OpenAI/Azure reasoning models when the caller
    # only knows the model is a reasoning model, not how hard it should think.
    LLM_OPENAI_REASONING_EFFORT: str = "medium"
    # TCP connect timeout for the AWS Bedrock client; its read timeout tracks
    # LLM_REQUEST_TIMEOUT.
    LLM_BEDROCK_CONNECT_TIMEOUT_SECONDS: int = 10
    # Default Bedrock read timeout when LLM_REQUEST_TIMEOUT is unset/zero.
    LLM_BEDROCK_READ_TIMEOUT_SECONDS: int = 60
    # Azure OpenAI API version used when a provider config doesn't pin one.
    LLM_AZURE_API_VERSION: str = "2024-10-21"
    # OpenAI-compatible base URL for Mistral (langchain-mistralai isn't a dep).
    LLM_MISTRAL_BASE_URL: str = "https://api.mistral.ai/v1"
    # Comma-separated model-name prefixes to additionally treat as reasoning
    # models, so a new model family can be enabled without a code change.
    LLM_EXTRA_REASONING_MODEL_PREFIXES: str = ""

    MCP_SERVER_URL: str = Field(
        default="http://localhost:8003/mcp",
        validation_alias=AliasChoices("MCP_SERVER_URL", "TOOLS_SERVICE_URL"),
    )
    TOOLS_SERVICE_URL: str = Field(
        default="http://localhost:8003/mcp",
        validation_alias=AliasChoices("TOOLS_SERVICE_URL", "MCP_SERVER_URL"),
    )
    GITHUB_PAT: str | None = None
    MCP_GITHUB_SERVER_URL: str = "https://api.githubcopilot.com/mcp/"

    LANGFUSE_TRACING: bool = False
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None

    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_PROJECT: str = "default"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: str | None = None

    DATABASE_TYPE: DatabaseType = DatabaseType.SQLITE
    SQLITE_DB_PATH: str = "checkpoints.db"

    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None
    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int | None = None
    POSTGRES_DB: str | None = None
    POSTGRES_APPLICATION_NAME: str = "agent-service"
    POSTGRES_MIN_CONNECTIONS_PER_POOL: int = 2
    POSTGRES_MAX_CONNECTIONS_PER_POOL: int = 20

    MONGO_HOST: str | None = None
    MONGO_PORT: int | None = None
    MONGO_DB: str | None = None
    MONGO_USER: str | None = None
    MONGO_PASSWORD: str | None = None
    MONGO_AUTH_SOURCE: str | None = None

    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j123"

    VECTOR_DB_PROVIDER: str = "milvus"
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 9765
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""

    AIRBYTE_API_URL: str | None = None
    AIRBYTE_LOCAL_OUTPUT_PATH: str = "/tmp/airbyte_local"

    MINIO_HOST: str = "localhost"
    MINIO_PORT: int = 10000
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "agent-service-documents"
    MINIO_SECURE: bool = False

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    IDEMPOTENCY_TTL: int = 86_400
    IDEMPOTENCY_ENABLED: bool = True
    IDEMPOTENCY_ENFORCE_REQUIRED_KEYS: bool = True
    IDEMPOTENCY_LOCK_TTL: int = 10
    IDEMPOTENCY_WAIT_TIMEOUT: float = 10.0

    # Document output tools (create_document / create_spreadsheet) — always
    # available to every agent and the default chatbot, not opt-in per agent.
    DOCUMENT_TOOLS_ENABLED: bool = True

    # The full `options` reference (~350 tokens) is appended to the tool
    # description on every request. Disable for token-sensitive or small
    # local-model setups; `options` keeps working, the model just isn't told
    # about it in detail.
    DOCUMENT_TOOLS_RICH_OPTIONS: bool = True

    @computed_field
    @property
    def BASE_URL(self) -> str:
        return f"http://{self.HOST}:{self.PORT}"

    @computed_field
    @property
    def AVAILABLE_MODELS(self) -> set[str]:
        """Configured fallback model names.

        Runtime availability is discovered from connected providers. This value
        only exposes explicit env/default fallbacks for legacy callers.
        """
        models = {
            model
            for model in (
                self.DEFAULT_MODEL,
                self.OLLAMA_MODEL,
                self.COMPATIBLE_MODEL,
            )
            if model
        }
        return models

    def is_dev(self) -> bool:
        return self.MODE == "dev"


settings = Settings()
