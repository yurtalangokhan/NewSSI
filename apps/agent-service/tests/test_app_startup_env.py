"""Regression coverage for URL validation before startup opens connections."""

import pytest


@pytest.mark.asyncio
async def test_lifespan_validates_environment_urls(monkeypatch):
    import app as application

    calls = []

    class ValidationComplete(Exception):
        pass

    def capture_urls(urls, *, required=True):
        calls.append((urls, required))
        if len(calls) == 2:
            raise ValidationComplete

    monkeypatch.setenv("INTERNAL_USER_SERVICE_URL", str("https://gateway.example/users"))
    monkeypatch.setenv("INTERNAL_RAG_SERVICE_API_URL", str("https://gateway.example/rag"))
    monkeypatch.setattr(application, "assert_gateway_routed", capture_urls)

    with pytest.raises(ValidationComplete):
        async with application.lifespan(application.app):
            pytest.fail("Startup must validate URLs before opening connections")

    assert calls == [
        (
            {
                "INTERNAL_USER_SERVICE_URL": "https://gateway.example/users",
                "INTERNAL_TOOLS_SERVICE_URL": application.env.INTERNAL_TOOLS_SERVICE_URL,
            },
            True,
        ),
        (
            {
                "INTERNAL_RAG_SERVICE_API_URL": "https://gateway.example/rag",
            },
            False,
        ),
    ]
