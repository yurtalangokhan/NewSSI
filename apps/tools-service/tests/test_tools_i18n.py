from pathlib import Path

import pytest
from fastmcp import FastMCP
from i18n import init_service_i18n
from i18n.core import set_locale

from src.core.registry import ToolRegistry
from src.tools.calculator_tools import CalculatorTools


@pytest.fixture(autouse=True)
def setup_i18n():
    locales_dir = Path(__file__).resolve().parents[1] / "locales"
    init_service_i18n(locales_dir)


@pytest.mark.asyncio
async def test_tools_list_i18n_translation():
    mcp = FastMCP("test-i18n-mcp")
    registry = ToolRegistry(mcp)
    calc_cat = CalculatorTools()
    registry.register_category(calc_cat)

    # 1. Test Turkish translation
    set_locale("tr")
    tr_tools = await mcp.list_tools()
    calc_tool = next(t for t in tr_tools if t.name == "calculate")

    assert "[category:calculator]" in calc_tool.description
    assert "[category_label:Hesap Makinesi]" in calc_tool.description
    assert "[title:Hesapla]" in calc_tool.description
    assert "Bir matematiksel ifadeyi güvenli bir şekilde değerlendirin." in calc_tool.description

    # 2. Test English translation
    set_locale("en")
    en_tools = await mcp.list_tools()
    calc_tool_en = next(t for t in en_tools if t.name == "calculate")

    assert "[category:calculator]" in calc_tool_en.description
    assert "[category_label:Calculator]" in calc_tool_en.description
    assert "[title:Calculate]" in calc_tool_en.description
    assert "Evaluate a mathematical expression safely." in calc_tool_en.description


@pytest.mark.asyncio
async def test_list_categories_i18n():
    mcp = FastMCP("test-categories-mcp")
    registry = ToolRegistry(mcp)
    calc_cat = CalculatorTools()
    registry.register_category(calc_cat)

    set_locale("tr")
    tr_cats = registry.list_categories()
    calc_info_tr = next(c for c in tr_cats if c["name"] == "calculator")
    assert calc_info_tr["label"] == "Hesap Makinesi"
    assert calc_info_tr["description"] == "Güvenli matematiksel ifade değerlendirmesi"

    set_locale("en")
    en_cats = registry.list_categories()
    calc_info_en = next(c for c in en_cats if c["name"] == "calculator")
    assert calc_info_en["label"] == "Calculator"
    assert calc_info_en["description"] == "Safe mathematical expression evaluation"
