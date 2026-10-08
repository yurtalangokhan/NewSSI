"""code_tools must confine every path argument to the workspace, and must
not expose a localhost port scanner. Spec TS-2, TS-4."""

from pathlib import Path

import pytest

from src.tools import code_tools


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
    monkeypatch.setattr(code_tools, "workspace_root", lambda: tmp_path)
    recorder = _Recorder()
    code_tools.CodeTools().register_tools(recorder)
    return recorder.tools


def _assert_escape_rejected(result: str) -> None:
    assert "workspace" in result.lower()


def test_check_port_tool_is_no_longer_registered(tools):
    assert "check_port" not in tools


@pytest.mark.asyncio
async def test_run_python_file_rejects_outside_path(tools):
    _assert_escape_rejected(await tools["run_python_file"]("/app/server.py"))


@pytest.mark.asyncio
async def test_run_python_file_rejects_traversal(tools):
    _assert_escape_rejected(await tools["run_python_file"]("../../etc/passwd"))


@pytest.mark.asyncio
async def test_run_pytest_rejects_outside_path(tools):
    _assert_escape_rejected(await tools["run_pytest"]("/etc"))


@pytest.mark.asyncio
async def test_run_npm_command_rejects_outside_dir(tools):
    _assert_escape_rejected(await tools["run_npm_command"]("/etc", "install"))


def test_validate_json_file_rejects_outside_path(tools):
    _assert_escape_rejected(tools["validate_json_file"]("/etc/passwd"))


@pytest.mark.asyncio
async def test_run_linter_rejects_outside_path(tools):
    _assert_escape_rejected(await tools["run_linter"]("/etc/passwd"))


def test_start_dev_server_rejects_outside_path(tools):
    _assert_escape_rejected(tools["start_dev_server"]("/etc"))


@pytest.mark.asyncio
async def test_run_python_file_works_inside_workspace(tools, tmp_path):
    script = tmp_path / "hello.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    out = await tools["run_python_file"]("hello.py")
    assert "hi" in out


@pytest.mark.asyncio
async def test_run_python_executes_with_cwd_inside_workspace(tools, tmp_path):
    # run_python's temp file and working directory must land under the
    # (possibly per-tenant) workspace root, not the process's default temp
    # directory, so a workspace boundary also covers files the code itself
    # creates via relative paths.
    out = await tools["run_python"]("import os; print(os.getcwd())")
    assert str(tmp_path.resolve()) in out
