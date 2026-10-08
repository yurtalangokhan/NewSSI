"""Spec TS-1: execute_shell is replaced by a server-defined command
registry. The model selects a command_id; it never supplies a command
string."""

from pathlib import Path

import pytest

from src.core.commands import ALLOWED_COMMANDS, UnknownCommandError, build_argv


def test_known_command_builds_argv():
    assert build_argv("python_version", {}) == ["python3", "--version"]


def test_unknown_command_is_rejected():
    with pytest.raises(UnknownCommandError):
        build_argv("rm_rf_slash", {})


def test_free_form_command_string_is_rejected():
    with pytest.raises(UnknownCommandError):
        build_argv("echo x; touch /tmp/pwn", {})


def test_registry_rejects_arguments_for_argument_free_commands():
    with pytest.raises(UnknownCommandError):
        build_argv("python_version", {"extra": "x"})


def test_registry_contains_no_shell_interpreters():
    for argv in ALLOWED_COMMANDS.values():
        assert argv[0] not in {"sh", "bash", "zsh", "dash", "env", "eval"}


class _Recorder:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *a, **k):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def tools(tmp_path: Path, monkeypatch):
    from src.tools import command_tools

    monkeypatch.setattr(command_tools, "workspace_root", lambda: tmp_path)
    recorder = _Recorder()
    command_tools.CommandTools().register_tools(recorder)
    return recorder.tools


def test_execute_shell_tool_no_longer_exists(tools):
    assert "execute_shell" not in tools


@pytest.mark.asyncio
async def test_run_command_tool_rejects_unknown_id(tools):
    out = await tools["run_command"]("definitely_not_a_command")
    assert "not allowed" in out.lower() or "izin" in out.lower()


@pytest.mark.asyncio
async def test_run_command_tool_runs_a_known_command(tools):
    out = await tools["run_command"]("python_version")
    assert "Python" in out


def test_list_commands_lists_registered_ids(tools):
    out = tools["list_commands"]()
    assert "python_version" in out


def test_get_system_info_no_longer_leaks_hostname_or_os_version(tools):
    import json

    info = json.loads(tools["get_system_info"]())
    # hostname and os_version are internal infrastructure details with no
    # legitimate use for a model; only architecture/runtime facts remain.
    assert "hostname" not in info
    assert "os_version" not in info
    assert "python_version" in info
