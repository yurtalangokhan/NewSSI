from localization.core import set_locale

from service.proxy.proxy_service import ProxyService


class TestMcpConnectionForwardsLocale:
    def test_includes_current_locale_as_x_language_header(self):
        set_locale("tr")
        try:
            connection = ProxyService()._mcp_connection("http://tools-service:8003/mcp")
        finally:
            set_locale("en")

        assert connection["headers"]["X-Language"] == "tr"

    def test_defaults_to_en_when_locale_not_set(self):
        connection = ProxyService()._mcp_connection("http://tools-service:8003/mcp")

        assert connection["headers"]["X-Language"] == "en"

    def test_still_includes_authorization_header_when_token_configured(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "secret-token")

        connection = ProxyService()._mcp_connection("http://tools-service:8003/mcp")

        assert connection["headers"]["Authorization"] == "Bearer secret-token"
        assert connection["headers"]["X-Language"] == "en"
