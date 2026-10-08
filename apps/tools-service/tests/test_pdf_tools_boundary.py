"""pdf_tools must confine every path to the workspace, must not block the
event loop with PyMuPDF calls, and must not leak a file descriptor when an
error occurs mid-document. Spec TS-2, TS-11.

pdf_tools returns a JSON envelope ({"success": ..., ...}) rather than the
bare-string contract file_tools/code_tools/java_tools use, so a workspace
escape is reported through self.error_response with the same
workspace.path_escape_error key those modules share, not through
guard_workspace_escape (which returns a bare string and would break this
module's envelope).
"""

import asyncio
import json
from pathlib import Path

import pytest

from src.tools import pdf_tools


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
    monkeypatch.setattr(pdf_tools, "workspace_root", lambda: tmp_path)
    recorder = _Recorder()
    pdf_tools.PDFTools().register_tools(recorder)
    return recorder.tools


def _minimal_pdf_bytes() -> bytes:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


async def _assert_escape_rejected(coro) -> None:
    result = json.loads(await coro)
    assert result["success"] is False
    assert "workspace" in result["error"].lower()


@pytest.mark.asyncio
async def test_read_pdf_rejects_outside_path(tools):
    await _assert_escape_rejected(tools["read_pdf"]("/etc/shadow"))


@pytest.mark.asyncio
async def test_read_pdf_rejects_traversal(tools):
    await _assert_escape_rejected(tools["read_pdf"]("../../etc/shadow"))


@pytest.mark.asyncio
async def test_read_pdf_page_rejects_outside_path(tools):
    await _assert_escape_rejected(tools["read_pdf_page"]("/etc/shadow", 1))


@pytest.mark.asyncio
async def test_get_pdf_info_rejects_outside_path(tools):
    await _assert_escape_rejected(tools["get_pdf_info"]("/etc/shadow"))


@pytest.mark.asyncio
async def test_search_pdf_rejects_outside_path(tools):
    await _assert_escape_rejected(tools["search_pdf"]("/etc/shadow", "x"))


@pytest.mark.asyncio
async def test_extract_pdf_tables_rejects_outside_path(tools):
    await _assert_escape_rejected(tools["extract_pdf_tables"]("/etc/shadow"))


@pytest.mark.asyncio
async def test_read_pdf_works_inside_workspace(tools, tmp_path):
    (tmp_path / "doc.pdf").write_bytes(_minimal_pdf_bytes())
    result = json.loads(await tools["read_pdf"]("doc.pdf"))
    assert result["success"] is True
    assert result["total_pages"] == 1


@pytest.mark.asyncio
async def test_read_pdf_rejects_file_over_size_limit(tools, tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_tools, "MAX_PDF_BYTES", 10)
    (tmp_path / "big.pdf").write_bytes(_minimal_pdf_bytes())
    result = json.loads(await tools["read_pdf"]("big.pdf"))
    assert result["success"] is False
    assert "large" in result["error"].lower() or "limit" in result["error"].lower()


@pytest.mark.asyncio
async def test_read_pdf_does_not_block_the_event_loop(tools, tmp_path):
    """The blocking PyMuPDF call must run off the event loop (to_thread),
    or a concurrently-scheduled coroutine would be starved for its
    duration."""
    (tmp_path / "doc.pdf").write_bytes(_minimal_pdf_bytes())

    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0.005)
            ticks += 1

    ticker_task = asyncio.create_task(ticker())
    await tools["read_pdf"]("doc.pdf")
    await ticker_task
    assert ticks == 20


def test_fitz_document_is_used_as_a_context_manager():
    """Regression guard: a bare doc.close() statement (outside a
    finally/with block) leaks the file descriptor if an exception is
    raised between fitz.open() and the close() call. The module docstring
    mentions "doc.close()" in prose describing the fix, which is fine --
    this checks for it as an executable statement, not as a substring."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(pdf_tools))
    bare_close_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "close"
    ]
    assert bare_close_calls == []
    assert "with fitz.open(" in inspect.getsource(pdf_tools)
