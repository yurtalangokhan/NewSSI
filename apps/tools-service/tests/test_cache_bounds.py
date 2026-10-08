"""No process-local cache may grow without a bound.

Spec 5/T6: `_PERMISSION_CACHE` was a plain dict that grew one entry per
subject ever authorized, for the lifetime of the process.
"""

from cachetools import LRUCache, TTLCache


def test_permission_cache_is_bounded():
    from src.core import authorization

    assert isinstance(authorization._PERMISSION_CACHE, (TTLCache, LRUCache))
    assert authorization._PERMISSION_CACHE.maxsize < float("inf")
