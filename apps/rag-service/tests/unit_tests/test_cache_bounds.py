"""No process-local cache may grow without a bound.

Spec 5/T6: `_permission_cache`, `_upload_progress` and `_build_progress`
were plain dicts that grew for the lifetime of the process, one entry per
user/permission or per collection ever seen.
"""

from cachetools import LRUCache, TTLCache


def test_authorization_client_permission_cache_is_bounded():
    from src.shared.authorization import AuthorizationClient

    client = AuthorizationClient()
    assert isinstance(client._permission_cache, (TTLCache, LRUCache))
    assert client._permission_cache.maxsize < float("inf")


def test_upload_progress_cache_is_bounded():
    from src.documents import upload_service as document_upload_service

    assert isinstance(document_upload_service._upload_progress, (TTLCache, LRUCache))
    assert document_upload_service._upload_progress.maxsize < float("inf")


def test_build_progress_cache_is_bounded():
    from src.graph import service as graph_rag_service

    assert isinstance(graph_rag_service._build_progress, (TTLCache, LRUCache))
    assert graph_rag_service._build_progress.maxsize < float("inf")
