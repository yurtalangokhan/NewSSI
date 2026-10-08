"""resolve_in_workspace is the single boundary every filesystem-touching
tool must route through. See spec TS-2."""

from pathlib import Path

import pytest

from src.core.workspace import WorkspaceEscapeError, resolve_in_workspace


def test_relative_path_resolves_inside_root(tmp_path: Path):
    resolved = resolve_in_workspace("project/main.py", root=tmp_path)
    assert resolved == (tmp_path / "project" / "main.py")


def test_absolute_path_is_rejected(tmp_path: Path):
    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace("/etc/passwd", root=tmp_path)


def test_proc_environ_is_rejected(tmp_path: Path):
    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace("/proc/self/environ", root=tmp_path)


def test_parent_traversal_is_rejected(tmp_path: Path):
    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace("../../etc/passwd", root=tmp_path)


def test_embedded_traversal_is_rejected(tmp_path: Path):
    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace("project/../../etc/passwd", root=tmp_path)


def test_symlink_escape_is_rejected(tmp_path: Path):
    outside = tmp_path.parent / "outside_target_for_workspace_test"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("leak", encoding="utf-8")
    root = tmp_path / "ws"
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)

    try:
        with pytest.raises(WorkspaceEscapeError):
            resolve_in_workspace("link/secret.txt", root=root)
    finally:
        import shutil

        shutil.rmtree(outside, ignore_errors=True)


def test_root_itself_is_allowed(tmp_path: Path):
    assert resolve_in_workspace(".", root=tmp_path) == tmp_path


def test_null_byte_is_rejected(tmp_path: Path):
    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace("a\x00b", root=tmp_path)


def test_sibling_directory_with_shared_prefix_is_rejected(tmp_path: Path):
    """A naive str.startswith(root) check would let 'tmp_path_evil' pass
    for a root of 'tmp_path'; is_relative_to() does not have this bug."""
    root = tmp_path / "ws"
    root.mkdir()
    sibling = tmp_path / "ws_evil"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("leak", encoding="utf-8")

    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace("../ws_evil/secret.txt", root=root)


def test_workspace_path_pattern_compiles_under_pydantic_core():
    """pydantic-core compiles Field(pattern=...) with Rust's `regex` crate,
    which rejects look-around at schema-build time — not at call time. A
    look-around pattern here would only fail once a tool using WorkspacePath
    is actually registered with a real MCP server, which is a much later
    and much less obvious point of failure than a schema-construction test."""
    from pydantic import TypeAdapter

    from src.core.workspace import WorkspacePath

    adapter = TypeAdapter(WorkspacePath)
    assert adapter.validate_python("project/main.py") == "project/main.py"

    from pydantic import ValidationError

    for bad in ("/etc/passwd", "a\x00b"):
        try:
            adapter.validate_python(bad)
        except ValidationError:
            continue
        raise AssertionError(f"{bad!r} should have been rejected by the schema")


def test_guard_workspace_escape_converts_exception_to_string():
    from src.core.workspace import WorkspaceEscapeError, guard_workspace_escape

    @guard_workspace_escape
    def tool(path: str) -> str:
        raise WorkspaceEscapeError(f"nope: {path}")

    result = tool("/etc/passwd")
    assert isinstance(result, str)
    assert "workspace" in result.lower()


def test_guard_workspace_escape_passes_through_normal_results():
    from src.core.workspace import guard_workspace_escape

    @guard_workspace_escape
    def tool(x: int) -> int:
        return x * 2

    assert tool(21) == 42


def test_workspace_escape_error_is_not_an_os_error():
    """Every tool module wraps its filesystem calls in a broad
    `except OSError`, sometimes around a second resolve_in_workspace() call
    nested inside that block (e.g. an output_dir argument). If this type
    were an OSError/PermissionError subclass, such a block would silently
    swallow the escape as a generic I/O error instead of letting
    guard_workspace_escape report it distinctly."""
    from src.core.workspace import WorkspaceEscapeError

    assert not issubclass(WorkspaceEscapeError, OSError)


@pytest.mark.asyncio
async def test_guard_workspace_escape_wraps_async_tools_too():
    """Regression test: calling an async def only builds its coroutine, it
    does not run the body. A guard that runs a plain try/except around the
    call (instead of around an await) would let a WorkspaceEscapeError
    raised inside the coroutine escape uncaught -- the exception is not
    raised until the coroutine is awaited."""
    from src.core.workspace import WorkspaceEscapeError, guard_workspace_escape

    @guard_workspace_escape
    async def tool(path: str) -> str:
        raise WorkspaceEscapeError(f"nope: {path}")

    result = await tool("/etc/passwd")
    assert isinstance(result, str)
    assert "workspace" in result.lower()


@pytest.mark.asyncio
async def test_guard_workspace_escape_passes_through_async_results():
    from src.core.workspace import guard_workspace_escape

    @guard_workspace_escape
    async def tool(x: int) -> int:
        return x * 2

    assert await tool(21) == 42


def test_escape_raised_inside_an_except_oserror_block_is_still_caught(tmp_path):
    """Regression test for the exact bug this class hierarchy prevents:
    a tool function that resolves a second path argument inside its own
    try/except OSError block must still have the escape reach
    guard_workspace_escape, not the tool's own generic error handler."""
    from src.core.workspace import guard_workspace_escape, resolve_in_workspace

    @guard_workspace_escape
    def tool_with_nested_resolve(second_path: str) -> str:
        try:
            resolve_in_workspace(second_path, root=tmp_path)
            return "should not get here"
        except OSError as e:
            return f"generic error handler caught: {e}"

    result = tool_with_nested_resolve("/etc/passwd")
    assert "generic error handler" not in result
    assert "workspace" in result.lower()
