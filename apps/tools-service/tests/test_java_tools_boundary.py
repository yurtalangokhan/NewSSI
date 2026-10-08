"""java_tools must confine every path argument to the workspace. Spec TS-2."""

from pathlib import Path

import pytest

from src.tools import java_tools


class _Recorder:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.fixture
def tools(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(java_tools, "workspace_root", lambda: tmp_path)
    recorder = _Recorder()
    java_tools.JavaTools().register_tools(recorder)
    return recorder.tools


def _assert_escape_rejected(result: str) -> None:
    assert "workspace" in result.lower()


def test_run_jar_rejects_outside_path(tools):
    _assert_escape_rejected(tools["run_jar"]("/etc/passwd"))


def test_run_jar_rejects_traversal(tools):
    _assert_escape_rejected(tools["run_jar"]("../../etc/shadow"))


def test_compile_java_file_rejects_outside_path(tools):
    _assert_escape_rejected(tools["compile_java_file"]("/etc/passwd"))


def test_compile_java_file_rejects_outside_output_dir(tools, tmp_path):
    src = tmp_path / "Main.java"
    src.write_text("public class Main {}", encoding="utf-8")
    _assert_escape_rejected(tools["compile_java_file"]("Main.java", output_dir="/etc"))


def test_validate_java_file_rejects_outside_path(tools):
    _assert_escape_rejected(tools["validate_java_file"]("/etc/passwd"))


def test_inspect_jar_rejects_outside_path(tools):
    _assert_escape_rejected(tools["inspect_jar"]("/etc/passwd"))


def test_run_jar_reports_not_found_inside_workspace(tools):
    out = tools["run_jar"]("missing.jar")
    assert "workspace" not in out.lower()
