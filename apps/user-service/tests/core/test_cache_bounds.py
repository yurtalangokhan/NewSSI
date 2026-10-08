"""No process-local cache may grow without a bound.

Spec 5/T6: the admin-token and client-UUID caches were single-slot (so
looking up one Keycloak client silently evicted a different one's still
valid cached value), and `PermissionResolverService._cache` was a plain
dict that grew one entry per user ever permission-checked.
"""

from cachetools import LRUCache, TTLCache


def test_admin_token_cache_is_bounded_and_keyed():
    from src.service.keycloak_service import KeycloakService

    assert isinstance(KeycloakService._admin_token_cache, (TTLCache, LRUCache))
    assert KeycloakService._admin_token_cache.maxsize < float("inf")


def test_client_uuid_cache_is_bounded_and_keyed():
    from src.service.keycloak_service import KeycloakService

    assert isinstance(KeycloakService._client_uuid_cache, (TTLCache, LRUCache))
    assert KeycloakService._client_uuid_cache.maxsize < float("inf")


def test_permission_resolver_cache_is_bounded():
    from src.service.permission_resolver_service import PermissionResolverService

    service = PermissionResolverService()
    assert isinstance(service._cache, (TTLCache, LRUCache))
    assert service._cache.maxsize < float("inf")
