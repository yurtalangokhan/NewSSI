"""Gateway configuration preserves secrets as data and rejects missing settings."""

import importlib.util
from pathlib import Path

import pytest


def renderer():
    path = Path(__file__).resolve().parents[1] / "render_gateway_config.py"
    spec = importlib.util.spec_from_file_location("render_gateway_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def settings():
    return {
        "KEYCLOAK_ISSUER_URL": "https://identity.example/realms/platform",
        "KEYCLOAK_BASE_URL": "https://identity.internal",
        "KEYCLOAK_REALM": "platform",
        "KEYCLOAK_CLIENT_ID": "web",
        "KEYCLOAK_CLIENT_SECRET": "quote'\nsecret: true",
        "GATEWAY_KEYCLOAK_CLIENT_ID": "gateway-client",
        "GATEWAY_KEYCLOAK_CLIENT_SECRET": "gateway-secret",
        "INTERNAL_SERVICE_TOKEN": "internal-secret",
        "GATEWAY_ALLOWED_REDIRECT_URIS": '["https://app.example/auth/oidc/callback"]',
        "REDIS_HOST": "redis.internal",
        "REDIS_PORT": "6379",
        **{
            f"{service}_SERVICE_UPSTREAM_ADDR": f"{service.lower()}.internal:8080"
            for service in ("USER", "AGENT", "RAG", "TOOLS")
        },
    }


def test_secrets_and_arrays_are_rendered_as_data():
    result = renderer().render(
        {
            "nodes": {"__USER_SERVICE_UPSTREAM_ADDR__": 1},
            "secret": "__KEYCLOAK_CLIENT_SECRET__",
            "redirects": "__GATEWAY_ALLOWED_REDIRECT_URIS__",
            "secure": "__GATEWAY_COOKIE_SECURE__",
        },
        settings(),
    )
    assert result == {
        "nodes": {"user.internal:8080": 1},
        "secret": "quote'\nsecret: true",
        "redirects": ["https://app.example/auth/oidc/callback"],
        "secure": True,
    }


def test_missing_auth_secret_fails_without_disclosing_values():
    env = settings()
    del env["GATEWAY_KEYCLOAK_CLIENT_SECRET"]
    with pytest.raises(ValueError, match="GATEWAY_KEYCLOAK_CLIENT_SECRET") as failure:
        renderer().render({}, env)
    assert "internal-secret" not in str(failure.value)


def test_missing_gateway_client_id_fails_instead_of_using_an_implementation_name():
    env = settings()
    del env["GATEWAY_KEYCLOAK_CLIENT_ID"]
    with pytest.raises(ValueError, match="GATEWAY_KEYCLOAK_CLIENT_ID"):
        renderer().render({}, env)


def test_wildcard_redirect_is_rejected():
    env = settings()
    env["GATEWAY_ALLOWED_REDIRECT_URIS"] = '["https://app.example/*"]'
    with pytest.raises(ValueError, match="redirect"):
        renderer().render({}, env)


def test_issuer_trailing_slash_is_normalized():
    env = settings()
    env["KEYCLOAK_ISSUER_URL"] += "/"
    result = renderer().render({"issuer": "__KEYCLOAK_ISSUER_URL__"}, env)
    assert result["issuer"] == "https://identity.example/realms/platform"


def test_an_upstream_address_must_be_a_bare_host_and_port():
    env = settings()
    env["RAG_SERVICE_UPSTREAM_ADDR"] = "http://rag.internal:8080/"
    with pytest.raises(ValueError, match="RAG_SERVICE_UPSTREAM_ADDR"):
        renderer().render({}, env)


@pytest.mark.parametrize(
    ("external_settings", "expected_alias"),
    [
        ({"EXTERNAL_KEYCLOAK": "true", "EXTERNAL_KEYCLOAK_ALIAS": "corporate"}, "corporate"),
        ({"EXTERNAL_KEYCLOAK": "true"}, "external-keycloak"),
        ({"EXTERNAL_KEYCLOAK": "false", "EXTERNAL_KEYCLOAK_ALIAS": "corporate"}, ""),
        ({}, ""),
        (
            {
                "EXTERNAL_KEYCLOAK": "true",
                "EXTERNAL_KEYCLOAK_ALIAS": "corporate",
                "GATEWAY_EXTERNAL_IDP_ALIAS": "gateway-override",
            },
            "gateway-override",
        ),
    ],
)
def test_external_login_inherits_enabled_provider_unless_gateway_overrides(
    external_settings, expected_alias
):
    result = renderer().render(
        {"external_idp_alias": "__GATEWAY_EXTERNAL_IDP_ALIAS__"},
        {**settings(), "GATEWAY_EXTERNAL_IDP_ALIAS": "", **external_settings},
    )
    assert result["external_idp_alias"] == expected_alias
