"""starlette is a mandatory dependency (pyproject.toml), not an optional
extra, so LocalizationMiddleware must always be the real class -- never a silent
None from a swallowed ImportError masking an actual bug in middleware.py.
"""

from localization import LocalizationMiddleware
from localization.middleware import LocalizationMiddleware as MiddlewareClass


def test_localization_middleware_is_exported_as_the_real_class():
    assert LocalizationMiddleware is MiddlewareClass
