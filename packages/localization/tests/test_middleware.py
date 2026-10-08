import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from localization.core import get_locale
from localization.middleware import LocalizationMiddleware


def _build_app() -> Starlette:
    async def echo_locale(request):
        return JSONResponse({"locale": get_locale()})

    app = Starlette(routes=[Route("/whoami", echo_locale)])
    app.add_middleware(LocalizationMiddleware, default_locale="en")
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


class TestLocaleDetectionPrecedence:
    def test_defaults_to_en_with_no_signal(self, client: TestClient):
        resp = client.get("/whoami")
        assert resp.json() == {"locale": "en"}
        assert resp.headers["content-language"] == "en"

    def test_accept_language_header_is_honored(self, client: TestClient):
        resp = client.get("/whoami", headers={"Accept-Language": "tr-TR,tr;q=0.9"})
        assert resp.json() == {"locale": "tr"}

    def test_x_language_header_overrides_accept_language(self, client: TestClient):
        resp = client.get(
            "/whoami",
            headers={"X-Language": "tr", "Accept-Language": "en-US"},
        )
        assert resp.json() == {"locale": "tr"}

    def test_lang_query_param_overrides_headers(self, client: TestClient):
        resp = client.get(
            "/whoami?lang=tr",
            headers={"X-Language": "en", "Accept-Language": "en-US"},
        )
        assert resp.json() == {"locale": "tr"}

    def test_locale_query_param_also_supported(self, client: TestClient):
        resp = client.get("/whoami?locale=tr")
        assert resp.json() == {"locale": "tr"}

    def test_unsupported_language_normalizes_to_en(self, client: TestClient):
        resp = client.get("/whoami?lang=fr")
        assert resp.json() == {"locale": "en"}

    def test_response_carries_content_language_header(self, client: TestClient):
        resp = client.get("/whoami?lang=tr")
        assert resp.headers["content-language"] == "tr"


class TestConcurrentRequestIsolation:
    def test_locale_does_not_leak_between_requests(self, client: TestClient):
        tr_resp = client.get("/whoami?lang=tr")
        en_resp = client.get("/whoami")
        assert tr_resp.json() == {"locale": "tr"}
        assert en_resp.json() == {"locale": "en"}


@pytest.mark.asyncio
async def test_middleware_restores_outer_locale_and_preserves_response_language():
    from localization.core import set_locale

    async def app(scope, receive, send):
        assert get_locale() == "tr"
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-language", b"en")],
            }
        )

    async def receive():
        return {"type": "http.request", "body": b""}

    sent = []

    async def send(message):
        sent.append(message)

    set_locale("en")
    await LocalizationMiddleware(app)(
        {"type": "http", "method": "GET", "path": "/", "query_string": b"lang=tr", "headers": []},
        receive,
        send,
    )
    assert get_locale() == "en"
    assert dict(sent[0]["headers"])[b"content-language"] == b"en"
