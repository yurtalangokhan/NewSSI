"""Regression guard for spec TS-1/TS-4: shell=True must never reappear
anywhere in the tools-service source tree.

docker_tools.py and service_tools.py (removed, spec TS-4) and the
original execute_shell (removed, spec TS-1) were the last users."""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def test_no_shell_true_anywhere_in_tools_service_source():
    offenders = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.keyword) or node.arg != "shell":
                continue
            if isinstance(node.value, ast.Constant) and node.value.value is True:
                offenders.append(str(path.relative_to(SRC_ROOT)))
    assert offenders == [], f"shell=True found in: {offenders}"
