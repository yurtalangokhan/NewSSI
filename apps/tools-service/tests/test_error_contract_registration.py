import importlib


def test_tools_service_registers_standard_error_middleware(monkeypatch):
    required_env = {
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": "8001",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",
        "POSTGRES_DB": "tools",
        "USER_SERVICE_URL": "http://localhost:8090",
    }
    for name, value in required_env.items():
        monkeypatch.setenv(name, value)

    server = importlib.import_module("server")

    middleware_names = [
        middleware.cls.__name__ for middleware in server.build_idempotency_middleware()
    ]

    assert middleware_names[0] == "ErrorContractMiddleware"
