import json

from i18n.core import set_locale

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


async def test_read_pdf_missing_file_returns_translated_error():
    tools = _register()
    result = json.loads(await tools["read_pdf"]("/does/not/exist.pdf"))
    assert result == {"success": False, "error": "File not found: /does/not/exist.pdf"}


async def test_read_pdf_missing_file_error_is_translated_for_turkish_locale():
    tools = _register()
    set_locale("tr")
    try:
        result = json.loads(await tools["read_pdf"]("/does/not/exist.pdf"))
    finally:
        set_locale("en")
    assert result == {"success": False, "error": "Dosya bulunamadı: /does/not/exist.pdf"}


async def test_search_pdf_empty_search_text_returns_translated_error():
    tools = _register()
    result = json.loads(await tools["search_pdf"](__file__, ""))
    assert result == {"success": False, "error": "Search text cannot be empty"}
