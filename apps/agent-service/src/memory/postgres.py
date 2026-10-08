from contextlib import asynccontextmanager

from core.observability.logger import get_logger

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:
    AsyncPostgresSaver = None

try:
    from langgraph.store.postgres import AsyncPostgresStore
except ImportError:
    AsyncPostgresStore = None

from config_manager import env
from psycopg import errors as pg_errors
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr

logger = get_logger(__name__)

# Shared connection pool singleton to avoid socket churn and ensure central pool management
_shared_pool: AsyncConnectionPool | None = None


def validate_postgres_config() -> None:
    """
    Validate that all required PostgreSQL configuration is present.
    Raises ValueError if any required configuration is missing.
    """
    required_vars = [
        "POSTGRES_AGENT_SERVICE_USER",
        "POSTGRES_AGENT_SERVICE_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_AGENT_SERVICE_DB",
    ]

    missing = [var for var in required_vars if not getattr(env, var, None)]
    if missing:
        raise ValueError(
            f"Missing required PostgreSQL configuration: {', '.join(missing)}. "
            "These environment variables must be set to use PostgreSQL persistence."
        )

    if env.POSTGRES_MIN_CONNECTIONS_PER_POOL > env.POSTGRES_MAX_CONNECTIONS_PER_POOL:
        raise ValueError(
            f"POSTGRES_MIN_CONNECTIONS_PER_POOL ({env.POSTGRES_MIN_CONNECTIONS_PER_POOL}) "
            f"must be less than or equal to POSTGRES_MAX_CONNECTIONS_PER_POOL ({env.POSTGRES_MAX_CONNECTIONS_PER_POOL})"
        )


def get_postgres_conninfo() -> str:
    """Build canonical PostgreSQL conninfo using psycopg make_conninfo."""
    validate_postgres_config()
    raw_pw = env.POSTGRES_AGENT_SERVICE_PASSWORD
    password = raw_pw.get_secret_value() if isinstance(raw_pw, SecretStr) else (raw_pw or "")

    return make_conninfo(
        user=env.POSTGRES_AGENT_SERVICE_USER,
        password=password,
        host=env.POSTGRES_HOST,
        port=env.POSTGRES_PORT,
        dbname=env.POSTGRES_AGENT_SERVICE_DB,
    )


def get_postgres_connection_string() -> str:
    """Backward-compatible alias returning secure conninfo."""
    return get_postgres_conninfo()


async def get_or_create_shared_pool() -> AsyncConnectionPool:
    """Get or lazily initialize the shared connection pool.

    Shared by both the checkpointer and the store -- a single pool, so its
    application_name must not claim to belong to just one of them. (A
    former `application_suffix` parameter baked in whichever caller
    happened to create the pool first, mislabeling every connection used
    by the other caller in pg_stat_activity.)
    """
    global _shared_pool
    if _shared_pool is None or _shared_pool.closed:
        validate_postgres_config()
        conninfo = get_postgres_conninfo()

        _shared_pool = AsyncConnectionPool(
            conninfo,
            min_size=env.POSTGRES_MIN_CONNECTIONS_PER_POOL,
            max_size=env.POSTGRES_MAX_CONNECTIONS_PER_POOL,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
                "application_name": env.POSTGRES_APPLICATION_NAME,
            },
            check=AsyncConnectionPool.check_connection,
            timeout=env.POSTGRES_POOL_TIMEOUT_SECONDS,
            reconnect_timeout=env.POSTGRES_POOL_RECONNECT_TIMEOUT_SECONDS,
            open=False,
        )
        await _shared_pool.open()
    return _shared_pool


async def close_shared_pool() -> None:
    """Close the shared pool at shutdown.

    Every other startup resource (Redis, the SQLAlchemy engine, background
    workers) is explicitly closed in app.py's lifespan shutdown; this pool
    previously was not, relying on the process exiting to release its
    connections instead of a graceful close.
    """
    global _shared_pool
    if _shared_pool is not None and not _shared_pool.closed:
        await _shared_pool.close()
    _shared_pool = None


@asynccontextmanager
async def get_postgres_saver():
    """Initialize and yield a PostgreSQL saver instance using the managed connection pool."""
    pool = await get_or_create_shared_pool()

    # `pickle_fallback` lets the checkpointer persist values the default
    # msgpack path rejects — notably `pandas.DataFrame`, which `Operations`
    # (table ops), `SplitText` and `TypeConverter` (Table) put in `scratch`.
    # Without it those nodes 500 the run with "Type is not msgpack
    # serializable: DataFrame" (B5). The checkpointer only ever
    # (de)serialises our own flow state from our own database, so the
    # pickle escape hatch is not an untrusted-input surface.
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    checkpointer = AsyncPostgresSaver(pool, serde=JsonPlusSerializer(pickle_fallback=True))
    try:
        await checkpointer.setup()
    except pg_errors.DuplicateColumn as exc:
        # Some legacy DBs have partially-applied checkpoint migrations.
        # Continue startup when the schema is already effectively present.
        logger.warning("Ignoring duplicate-column during checkpointer setup: %s", exc)
    yield checkpointer


@asynccontextmanager
async def get_postgres_store():
    """Get a PostgreSQL store instance using the managed connection pool."""
    pool = await get_or_create_shared_pool()
    store = AsyncPostgresStore(pool)
    try:
        await store.setup()
    except pg_errors.DuplicateColumn as exc:
        # Same legacy-DB tolerance as get_postgres_saver's .setup() -- a
        # partially-applied migration shouldn't block startup when the
        # schema is already effectively present.
        logger.warning("Ignoring duplicate-column during store setup: %s", exc)
    yield store
