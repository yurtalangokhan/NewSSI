"""The dead `verify_internal_service_token` dependency stays gone.

It duplicated the constant-time compare that `require_auth_or_internal_service_token`
already performs, had no caller anywhere in `src` or in the test suite, and
was never covered by a test itself -- a second, untested code path for the
same security check. This pins its removal so it does not creep back.
"""

from __future__ import annotations


def test_the_dead_verify_internal_service_token_dependency_is_gone():
    from src.api import dependencies

    assert not hasattr(dependencies, "verify_internal_service_token")
