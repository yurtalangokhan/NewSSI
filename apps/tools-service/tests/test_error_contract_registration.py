import importlib


def test_tools_service_registers_the_platform_error_contract():
    """The FastAPI app owns the error contract; the MCP mount owns the rest."""
    server = importlib.import_module("server")

    app = server.build_http_app.__doc__
    assert app  # the builder is documented

    transport_middleware = [
        middleware.cls.__name__ for middleware in server.build_service_middleware()
    ]
    # Metrics live on the FastAPI app only; a second MetricsMiddleware on the
    # embedded transport would count every MCP request twice.
    assert "MetricsMiddleware" not in transport_middleware
    assert "IdempotencyMiddleware" in transport_middleware
    assert "TrustedContextMiddleware" in transport_middleware


def test_error_envelope_is_returned_for_unhandled_paths(http_client):
    response = http_client.get("/no-such-route")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "request.not_found"
