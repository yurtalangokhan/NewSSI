import json
import re
from pathlib import Path

import pytest
from fastmcp import FastMCP
from localization import init_localization
from localization.core import set_locale

from src.core.registry import ToolRegistry
from src.tools.calculator_tools import CalculatorTools

SERVICE_ROOT = Path(__file__).resolve().parents[1]
LOCALES = ("en", "tr")
_CATEGORY_TAG = re.compile(r"\[category:([^\]]+)\]")


@pytest.fixture(autouse=True)
def setup_i18n():
    locales_dir = SERVICE_ROOT / "locales"
    init_localization(locales_dir)


def _load_locale(locale_name: str) -> dict:
    path = SERVICE_ROOT / "locales" / f"{locale_name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _discovered_registry(mcp_name: str) -> tuple[FastMCP, ToolRegistry]:
    mcp = FastMCP(mcp_name)
    registry = ToolRegistry(mcp)
    registry.discover_plugins(str(SERVICE_ROOT / "src" / "tools"))
    return mcp, registry


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


@pytest.mark.parametrize("locale_name", LOCALES)
def test_every_registered_category_has_a_translated_label_and_description(locale_name: str):
    """Every category must have a ``categories.<name>`` entry in every locale.

    The lookup key is the category's ``name`` property, not whatever key the
    category class passes to ``t()`` itself — so a category can look translated
    in its own class and still fall back to its raw snake_case name in the UI.
    """
    _mcp, registry = _discovered_registry(f"coverage-categories-{locale_name}")
    catalog = _load_locale(locale_name).get("categories", {})

    missing = sorted(
        category["name"]
        for category in registry.list_categories()
        if not catalog.get(category["name"], {}).get("label")
        or not catalog.get(category["name"], {}).get("description")
    )

    assert missing == [], f"{locale_name}.json has no categories.<name> entry for: {missing}"


@pytest.mark.parametrize("locale_name", LOCALES)
@pytest.mark.asyncio
async def test_every_registered_tool_has_a_translated_name_and_description(locale_name: str):
    """Every tool must have a ``tools.<category>.<tool>`` entry in every locale.

    Without one the registry falls back to title-casing the snake_case tool id,
    which renders as English in every locale (e.g. "Connector List Resources").
    """
    mcp, _registry = _discovered_registry(f"coverage-tools-{locale_name}")
    catalog = _load_locale(locale_name).get("tools", {})

    missing = []
    for tool in await mcp.list_tools():
        match = _CATEGORY_TAG.search(tool.description or "")
        assert match is not None, f"Tool '{tool.name}' is registered without a category tag"
        entry = catalog.get(match.group(1), {}).get(tool.name, {})
        if not entry.get("name") or not entry.get("description"):
            missing.append(f"{match.group(1)}.{tool.name}")

    assert sorted(missing) == [], (
        f"{locale_name}.json has no tools.<category>.<tool> entry for: {sorted(missing)}"
    )
