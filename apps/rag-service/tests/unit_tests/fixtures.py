from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from langconnect import config
from langconnect.server import APP


def reset_db() -> None:
    """Reset the test vector store between test runs."""
    if config.VECTOR_DB_PROVIDER.lower() == "pgvector":
        # Legacy PGVector path: drop + recreate tables
        if config.POSTGRES_DB != "langchain_test":
            raise AssertionError(
                "Attempting to run unit tests with a non-test database. "
                "Please set the database to 'test' before running tests."
            )
        if config.POSTGRES_HOST != "localhost":
            raise AssertionError(
                "Attempting to run unit tests with a non-localhost database. "
                "Please set the host to 'localhost' before running tests."
            )
        from langconnect.database.connection import get_vectorstore
        vectorstore = get_vectorstore()
        vectorstore.drop_tables()
        vectorstore.__post_init__()
    else:
        # Milvus: nothing to reset globally — individual test collections are
        # ephemeral; each test creates/drops its own Milvus collection via the
        # standard collection CRUD APIs.
        pass


@asynccontextmanager
async def get_async_test_client() -> AsyncGenerator[AsyncClient, None]:
    """Get an async client."""
    url = "http://localhost:9999"
    transport = ASGITransport(
        app=APP,
        raise_app_exceptions=True,
    )
    reset_db()
    async_client = AsyncClient(base_url=url, transport=transport)
    try:
        yield async_client
    finally:
        await async_client.aclose()
