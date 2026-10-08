"""The manifest modules must import cleanly whichever of them a process loads first.

``agents.graphs.middleware`` sits on the path ``service.* -> agents.graphs`` while the
manifest reaches back into ``service.*`` through the document tool plumbing. In a test
session other modules are already loaded, which hides an import cycle; a fresh
interpreter per entry point does not.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.mark.parametrize(
    "module",
    [
        "agents.tooling.attachment_manifest",
        "agents.graphs.middleware",
        "agents.graphs",
        "agents.tooling.document_tools",
        "agents.implementations.chatbot",
        "agents.implementations.configurable_mcp_agent",
        "agents.graphs.strategies.react",
        "service.orchestration",
    ],
)
def test_the_module_imports_first_in_a_fresh_process(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-W", "ignore", "-c", f"import {module}"],
        cwd=SRC,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr[-800:]
