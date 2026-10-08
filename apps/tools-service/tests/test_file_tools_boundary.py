"""file_tools must never touch a path outside the workspace. Spec TS-2, TS-11.

Before this fix, file_tools.py never imported WORKSPACE_DIR at all: every
tool used a bare open()/Path() on whatever string the model supplied.

Every tool in this module follows a "never raise, always return a str"
contract, so a workspace escape is reported the same way as any other
failure: as a string mentioning "workspace" (see @_guard_workspace_escape
and the workspace.path_escape_error i18n key), not as a raised exception.
"""

from pathlib import Path

import pytest

from src.tools import file_tools


class _Recorder:
    """Minimal stand-in for the FastMCP server: captures registered tools."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.fixture
def tools(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(file_tools, "workspace_root", lambda: tmp_path)
    recorder = _Recorder()
    file_tools.FileTools().register_tools(recorder)
    return recorder.tools


def _assert_escape_rejected(result: str) -> None:
    assert "workspace" in result.lower()


def test_file_read_rejects_proc_environ(tools):
    _assert_escape_rejected(tools["file_read"]("/proc/self/environ"))


def test_file_read_rejects_traversal(tools):
    _assert_escape_rejected(tools["file_read"]("../../etc/passwd"))


def test_file_write_rejects_absolute_path(tools, tmp_path):
    result = tools["file_write"]("/app/server.py", "pwned")
    _assert_escape_rejected(result)
    assert not (tmp_path.parent / "app" / "server.py").exists()


def test_file_delete_rejects_workspace_root(tools, tmp_path):
    result = tools["file_delete"](".", recursive=True)
    _assert_escape_rejected(result)
    assert tmp_path.exists()


def test_file_read_and_write_roundtrip_inside_workspace(tools, tmp_path):
    tools["file_write"]("notes/hello.txt", "hi")
    assert (tmp_path / "notes" / "hello.txt").read_text(encoding="utf-8") == "hi"
    assert "hi" in tools["file_read"]("notes/hello.txt")


def test_file_read_is_capped_by_bytes(tools, tmp_path):
    (tmp_path / "big.txt").write_text("x" * (file_tools.MAX_READ_BYTES + 5000), encoding="utf-8")
    out = tools["file_read"]("big.txt")
    assert len(out.encode("utf-8")) <= file_tools.MAX_READ_BYTES + 200
    assert "truncated" in out


def test_file_read_does_not_buffer_whole_file_before_truncating(tools, tmp_path):
    """A file far larger than the cap must not be fully materialised in
    memory before the truncation kicks in."""
    huge_line_count = 2_000_000
    path = tmp_path / "huge.txt"
    with open(path, "w", encoding="utf-8") as f:
        for _ in range(huge_line_count):
            f.write("x\n")

    out = tools["file_read"]("huge.txt", max_lines=10)
    assert out.count("x") <= 15
    assert "truncated" in out


def test_file_list_rejects_traversal(tools):
    _assert_escape_rejected(tools["file_list"]("../"))


def test_file_list_uses_islice_and_caps_items(tools, tmp_path):
    for i in range(150):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
    out = tools["file_list"](".")
    assert out.count("FILE") <= file_tools.MAX_LIST_ITEMS
    assert "more items" in out


def test_file_list_skips_symlinks(tools, tmp_path):
    outside = tmp_path.parent / "outside_for_list_test"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("leak", encoding="utf-8")
    try:
        (tmp_path / "link.txt").symlink_to(outside / "secret.txt")
        out = tools["file_list"](".")
        assert "link.txt" not in out
    finally:
        import shutil

        shutil.rmtree(outside, ignore_errors=True)


def test_create_directory_rejects_traversal(tools):
    _assert_escape_rejected(tools["create_directory"]("../evil"))


def test_file_exists_rejects_traversal(tools):
    _assert_escape_rejected(tools["file_exists"]("/etc/passwd"))


def test_file_update_rejects_traversal(tools):
    _assert_escape_rejected(tools["file_update"]("../../etc/passwd", "old", "new"))


def test_file_delete_rejects_absolute_path(tools):
    _assert_escape_rejected(tools["file_delete"]("/etc/passwd"))


def test_file_write_rejects_content_over_byte_limit(tools):
    oversized = "x" * (file_tools.MAX_WRITE_BYTES + 1)
    result = tools["file_write"]("big.txt", oversized)
    assert "limit" in result.lower()


def test_normalize_content_is_unchanged():
    # normalize_content is pure text processing and must keep working
    # exactly as before — this is a regression guard, not a new behaviour.
    assert file_tools.normalize_content("a\\nb") == "a\nb"
