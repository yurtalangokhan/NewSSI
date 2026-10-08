from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from config_manager import env
from httpx import ASGITransport, AsyncClient, Response

from src.server import APP

#: The shared secret Gateway carries in ``x-gateway-token``. The test suite
#: configures the service with this value (see ``conftest.use_test_auth_mode``)
#: and presents it in the headers :func:`gateway_headers` builds.
GATEWAY_SECRET = "test-gateway-secret"


def gateway_headers(user_id: str = "user1", **overrides: str) -> dict[str, str]:
    """The trusted headers Gateway sets for an authenticated user.

    rag-service has no API-key or development authentication path any more: a
    request is authenticated only by the headers Gateway forwards, so a test
    that drives a real route has to present them.
    """
    headers = {
        "x-gateway-token": GATEWAY_SECRET,
        "x-gateway-user-id": user_id,
        "x-gateway-email": f"{user_id}@example.com",
        "x-gateway-username": user_id,
    }
    headers.update(overrides)
    return headers


def reset_db() -> None:
    """Reset the test vector store between test runs."""
    if env.VECTOR_DB_PROVIDER.lower() == "pgvector":
        # Legacy PGVector path: drop + recreate tables
        if env.POSTGRES_RAG_SERVICE_DB != "langchain_test":
            raise AssertionError(
                "Attempting to run unit tests with a non-test database. "
                "Please set the database to 'test' before running tests."
            )
        if env.POSTGRES_HOST != "localhost":
            raise AssertionError(
                "Attempting to run unit tests with a non-localhost database. "
                "Please set the host to 'localhost' before running tests."
            )
        from src.shared.vectorstore import get_vectorstore

        vectorstore = get_vectorstore()
        vectorstore.drop_tables()
        vectorstore.__post_init__()
    else:
        # Milvus: nothing to reset globally — individual test collections are
        # ephemeral; each test creates/drops its own Milvus collection via the
        # standard collection CRUD APIs.
        pass


_ENVELOPE_KEYS = frozenset({"statusCode", "message", "data", "error"})


def _is_success_envelope(body: Any) -> bool:
    return isinstance(body, dict) and set(body) == _ENVELOPE_KEYS and body["error"] is None


class EnvelopeUnwrappingClient(AsyncClient):
    """Test client that hands tests the payload a route produced.

    Every JSON route answers ``{statusCode, message, data, error}``. On a
    success, ``response.json()`` returns ``data`` so tests assert the resource
    itself; ``response.envelope()`` returns the raw envelope for contract
    checks. A failure keeps its envelope in ``json()``, which is the contract
    under test there (``response.json()["error"]``).
    """

    async def request(self, *args: Any, **kwargs: Any) -> Response:
        response = await super().request(*args, **kwargs)
        raw_json = response.json

        def envelope(**json_kwargs: Any) -> Any:
            return raw_json(**json_kwargs)

        def unwrapped(**json_kwargs: Any) -> Any:
            body = raw_json(**json_kwargs)
            return body["data"] if _is_success_envelope(body) else body

        response.envelope = envelope  # type: ignore[attr-defined]
        response.json = unwrapped  # type: ignore[method-assign]
        return response


@asynccontextmanager
async def get_async_test_client() -> AsyncGenerator[AsyncClient, None]:
    """Get an async client."""
    url = "http://localhost:9999"
    transport = ASGITransport(
        app=APP,
        raise_app_exceptions=True,
    )
    reset_db()
    async_client = EnvelopeUnwrappingClient(base_url=url, transport=transport)
    try:
        yield async_client
    finally:
        await async_client.aclose()
