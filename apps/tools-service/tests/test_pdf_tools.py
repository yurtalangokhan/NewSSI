import json

from localization.core import set_locale

from src.tools import pdf_tools
from src.tools.pdf_tools import PDFTools


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _register() -> dict:
    mcp = _FakeMCP()
    PDFTools().register_tools(mcp)
    return mcp.tools


async def test_read_pdf_missing_file_returns_translated_error(tmp_path, monkeypatch):
    # Amended for spec TS-2 (workspace confinement): this test originally
    # passed an absolute, unconfined path ("/does/not/exist.pdf"). That is
    # exactly the behaviour being fixed -- read_pdf now resolves its
    # argument relative to the workspace, so an absolute path is rejected
    # as a workspace escape before the file-not-found check ever runs. The
    # test now exercises the same "missing file, translated error" intent
    # with a path that is relative to (and therefore confined by) the
    # workspace, which is mocked to tmp_path here as every other tool
    # module's tests already do.
    monkeypatch.setattr(pdf_tools, "workspace_root", lambda: tmp_path)
    tools = _register()
    result = json.loads(await tools["read_pdf"]("does/not/exist.pdf"))
    assert result == {"success": False, "error": "File not found: does/not/exist.pdf"}


async def test_read_pdf_missing_file_error_is_translated_for_turkish_locale(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_tools, "workspace_root", lambda: tmp_path)
    tools = _register()
    set_locale("tr")
    try:
        result = json.loads(await tools["read_pdf"]("does/not/exist.pdf"))
    finally:
        set_locale("en")
    assert result == {"success": False, "error": "Dosya bulunamadı: does/not/exist.pdf"}


async def test_search_pdf_empty_search_text_returns_translated_error(tmp_path, monkeypatch):
    # Amended for the same reason: __file__ is an absolute path outside
    # any workspace. An empty file inside the mocked workspace exercises
    # the same "empty search text" check, which runs before the file's
    # content is ever touched.
    monkeypatch.setattr(pdf_tools, "workspace_root", lambda: tmp_path)
    (tmp_path / "doc.pdf").write_bytes(b"")
    tools = _register()
    result = json.loads(await tools["search_pdf"]("doc.pdf", ""))
    assert result == {"success": False, "error": "Search text cannot be empty"}
