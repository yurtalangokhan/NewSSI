"""Spec: a failure inside the default-admin bootstrap step must be reported
as what it actually is, not blanket-labelled a Keycloak outage.

`_ensure_default_admin`'s body mixes real Keycloak Admin API calls with local
repository calls (`role_repo.get_default_admin_role`, `user_repo.*`,
`settings_repo.ensure_defaults`) that do their own Postgres I/O. Before this,
the lifespan's `except Exception` around the whole call logged every failure
-- Keycloak unreachable, a validation `ValueError`, a local
`IntegrityError`/foreign-key violation, anything -- as "keycloak is
unavailable during default admin bootstrap", and recorded the "keycloak"
dependency as degraded regardless of which one actually failed. A real
Postgres foreign-key violation on `user_settings` was diagnosed as a Keycloak
outage this way, sending the investigation in the wrong direction entirely
before the actual `sqlalchemy.exc.IntegrityError` was found by bypassing the
handler and calling the function directly.

Only a genuine Keycloak HTTP failure (`httpx.HTTPError` and its subclasses --
`HTTPStatusError`, `ConnectError`, `TimeoutException`, ...) gets the
"keycloak is unavailable" framing. Everything else is reported as a
default-admin-bootstrap failure naming the real exception, and does not mark
the (uninvolved) "keycloak" dependency as degraded.
"""

import httpx
import pytest

from src.main import _admin_bootstrap_degraded_dependency


def test_a_keycloak_http_error_keeps_the_keycloak_unavailable_framing() -> None:
    exc = httpx.ConnectError("Connection refused")

    outcome = _admin_bootstrap_degraded_dependency(exc)

    assert outcome.dependency == "keycloak"
    assert "keycloak is unavailable" in outcome.message.lower()


def test_a_keycloak_http_status_error_keeps_the_keycloak_unavailable_framing() -> None:
    request = httpx.Request(
        "POST", "http://keycloak.example/realms/master/protocol/openid-connect/token"
    )
    response = httpx.Response(401, request=request)
    exc = httpx.HTTPStatusError("401 Unauthorized", request=request, response=response)

    outcome = _admin_bootstrap_degraded_dependency(exc)

    assert outcome.dependency == "keycloak"


def test_a_local_database_error_is_not_blamed_on_keycloak() -> None:
    # The exact failure this replaces: a Postgres FK violation on
    # user_settings, nothing to do with Keycloak reachability.
    exc = ValueError(
        'insert or update on table "user_settings" violates foreign key '
        'constraint "user_settings_user_id_fkey"'
    )

    outcome = _admin_bootstrap_degraded_dependency(exc)

    assert outcome.dependency != "keycloak"
    assert "keycloak" not in outcome.message.lower()


def test_a_local_error_names_the_real_exception_type_and_message() -> None:
    exc = ValueError("No default admin role exists in the permission catalog")

    outcome = _admin_bootstrap_degraded_dependency(exc)

    assert "ValueError" in outcome.message
    assert "No default admin role exists in the permission catalog" in outcome.message


def test_a_local_error_uses_a_distinct_dependency_name_from_keycloak() -> None:
    # A health/readiness check keyed on dependency name must not report
    # "keycloak degraded" for a failure Keycloak had no part in.
    exc = RuntimeError("boom")

    outcome = _admin_bootstrap_degraded_dependency(exc)

    assert outcome.dependency == "default_admin_bootstrap"


@pytest.mark.asyncio
async def test_a_local_repository_failure_from_the_real_bootstrap_function_is_not_blamed_on_keycloak() -> (
    None
):
    """End-to-end through `_ensure_default_admin`'s actual exception surface,
    not just the classifier in isolation -- a local repository error (the
    role catalog lookup, standing in for the real `user_settings` FK
    violation this replaces) must classify the same way a raw exception does.
    """
    from src.main import _ensure_default_admin

    class _ExplodingRoleRepo:
        async def get_default_admin_role(self):
            raise RuntimeError("permission denied for schema public")

    settings = type(
        "S",
        (),
        {
            "KEYCLOAK_ADMIN_EMAIL": "admin@example.com",
            "KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL": None,
            "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD": "secret",
        },
    )()
    keycloak = type("K", (), {"is_enabled": staticmethod(lambda: True)})()

    try:
        await _ensure_default_admin(
            settings=settings,
            keycloak=keycloak,
            role_repo=_ExplodingRoleRepo(),
            user_repo=None,
            settings_repo=None,
        )
        pytest.fail("expected the exploding role repo to raise")
    except RuntimeError as exc:
        outcome = _admin_bootstrap_degraded_dependency(exc)
        assert outcome.dependency == "default_admin_bootstrap"
