"""No process-local cache may grow without a bound.

Spec 5/T6: `AuthorizationClient._permission_cache` and
`_USER_BY_KEYCLOAK_ID_CACHE` were plain dicts that grew for the lifetime of
the process, one entry per user/permission ever seen. A third such cache,
`_VECTOR_STORE_CACHE` in `agents/tools.py`, no longer exists — the Milvus
vector store it cached moved to rag-service along with the rest of the
direct Milvus access (see `client.rag_client`).
"""

from cachetools import LRUCache, TTLCache


def test_authorization_client_permission_cache_is_bounded():
    from integrations.authorization_client import AuthorizationClient

    client = AuthorizationClient()
    assert isinstance(client._permission_cache, (TTLCache, LRUCache))
    assert client._permission_cache.maxsize < float("inf")


def test_user_by_keycloak_id_cache_is_bounded():
    from integrations import user_service_client as UserServiceClient

    assert isinstance(UserServiceClient._USER_BY_KEYCLOAK_ID_CACHE, (TTLCache, LRUCache))
    assert UserServiceClient._USER_BY_KEYCLOAK_ID_CACHE.maxsize < float("inf")


def test_ttl_cache_evicts_expired_entries():
    import time

    cache = TTLCache(maxsize=10, ttl=0.1)
    cache["k"] = "v"
    time.sleep(0.2)
    assert "k" not in cache


def test_lru_cache_evicts_oldest_entry_once_full():
    cache = LRUCache(maxsize=2)
    cache["a"] = 1
    cache["b"] = 2
    cache["c"] = 3
    assert "a" not in cache
    assert set(cache) == {"b", "c"}
