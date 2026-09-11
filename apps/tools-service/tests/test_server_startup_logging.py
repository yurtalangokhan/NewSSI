from __future__ import annotations

import os

os.environ.setdefault("MCP_HOST", "127.0.0.1")
os.environ.setdefault("MCP_PORT", "9000")
os.environ.setdefault("USER_SERVICE_URL", "http://user-service")
os.environ.setdefault("POSTGRES_HOST", "postgres")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "tools")
os.environ.setdefault("POSTGRES_PASSWORD", "secret")
os.environ.setdefault("POSTGRES_DB", "tools")


def test_log_startup_banner_uses_structured_logger() -> None:
    from server import log_startup_banner

    records: list[tuple[str, dict]] = []

    class FakeLogger:
        def info(self, message: str, **kwargs) -> None:
            records.append((message, kwargs))

    log_startup_banner(host="127.0.0.1", port=9000, logger=FakeLogger())

    assert records == [
        (
            "Starting FastMCP Server.",
            {
                "extra": {
                    "event": "startup.server.starting",
                    "dependency": None,
                    "operation": "serve_http",
                    "status": "starting",
                    "host": "127.0.0.1",
                    "port": 9000,
                    "mcp_endpoint": "http://127.0.0.1:9000/mcp",
                }
            },
        )
    ]
