from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.core import auth


async def test_keycloak_verifier_disables_iat_verification(monkeypatch) -> None:
    settings = SimpleNamespace(
        keycloak_issuer_url="https://issuer",
        keycloak_audience="tools-service",
        keycloak_client_id="agenticai-web",
        keycloak_token_leeway_seconds=120,
        mcp_public_base_url="http://localhost:9000/mcp",
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    class FakeSigningKey:
        key = "signing-key"

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token: str) -> FakeSigningKey:
            assert token == "sample-token"
            return FakeSigningKey()

    def _decode(
        jwt: str,
        key: str,
        algorithms: list[str],
        audience: list[str] | None,
        issuer: str,
        leeway: int,
        options: dict[str, bool],
    ) -> dict[str, object]:
        assert jwt == "sample-token"
        assert key == "signing-key"
        assert algorithms == ["RS256", "RS384", "RS512"]
        assert audience == ["tools-service", "agenticai-web"]
        assert issuer == "https://issuer"
        assert leeway == 120
        assert options["verify_iat"] is False
        return {"sub": "keycloak-sub", "exp": 2_000_000_000}

    monkeypatch.setattr(auth.jwt, "decode", _decode)
    monkeypatch.setattr(
        auth.KeycloakTokenVerifier,
        "_get_jwks_client",
        lambda self: FakeJwksClient(),
    )
    monkeypatch.setattr(
        auth,
        "get_user_service_permissions",
        AsyncMock(return_value=["tool:execute"]),
    )

    result = await auth.KeycloakTokenVerifier().verify_token("sample-token")

    assert result is not None
