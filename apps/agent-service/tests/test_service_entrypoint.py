"""The Windows launcher must create a psycopg-compatible event loop."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def test_windows_launcher_uses_selector_and_configured_port(monkeypatch):
    import asyncio
    import sys

    import uvicorn

    source = Path(__file__).resolve().parents[1] / "src/app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    entry = next(node for node in tree.body if isinstance(node, ast.If) and "__name__" in ast.unparse(node.test))
    policy = Mock()
    selector = Mock(return_value="selector-policy")
    run = Mock()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(asyncio, "WindowsSelectorEventLoopPolicy", selector, raising=False)
    monkeypatch.setattr(asyncio, "set_event_loop_policy", policy)
    monkeypatch.setattr(uvicorn, "run", run)
    settings = SimpleNamespace(
        HOST="127.0.0.1",
        AGENT_SERVICE_PORT=12345,
        GRACEFUL_SHUTDOWN_TIMEOUT=30,
        is_dev=lambda: False,
    )
    exec(  # noqa: S102 - execute only the repository's launcher with mocked I/O
        compile(ast.Module(body=entry.body, type_ignores=[]), str(source), "exec"),
        {"env": settings, "sys": sys, "asyncio": asyncio},
    )
    policy.assert_called_once_with("selector-policy")
    assert run.call_args.kwargs["port"] == 12345  # noqa: S101
