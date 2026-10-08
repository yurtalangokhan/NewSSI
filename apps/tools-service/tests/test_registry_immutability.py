"""list_tools must not mutate the registered Tool objects. Spec TS-10.

The i18n wrapper previously rewrote .name/.description in place on the
Tool objects FastMCP hands back from list_tools(); those objects are the
exact ones stored in FastMCP's own LocalProvider (list_tools returns live
references, not copies -- see FastMCP's LocalProvider._list_tools), shared
across every request. Two concurrent requests in different locales could
then interleave on the same object and see each other's text.

A same-locale, sequential call to list_tools() does not by itself expose
the mutation: the wrapper re-derives name/description from the tool's own
_original_name/_original_doc attributes (untouched by the mutation) on
every call, so calling it twice in a row "self-heals". The structural
regression test below checks the property that actually matters -- that
list_tools() never hands back the exact object stored internally -- since
that is what makes concurrent, different-locale requests safe regardless
of scheduling.
"""

from pathlib import Path

import pytest
from fastmcp import FastMCP
from localization.core import set_locale

from src.core.registry import ToolRegistry

TOOLS_DIR = str(Path(__file__).resolve().parents[1] / "src" / "tools")


def _registry() -> ToolRegistry:
    mcp = FastMCP("test-immutability-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)
    return registry


def _stored_tools(registry: ToolRegistry) -> dict[str, object]:
    """The exact objects FastMCP's LocalProvider holds internally, keyed by
    the tool's own .name (the provider's own dict key is an internal
    "tool:<name>@<version>" string this test should not depend on)."""
    (local_provider,) = registry.mcp.providers
    return {
        component.name: component
        for component in local_provider._components.values()
        if hasattr(component, "name")
    }


@pytest.mark.asyncio
async def test_list_tools_never_returns_the_internally_stored_object():
    registry = _registry()
    stored = _stored_tools(registry)

    returned = await registry.mcp.list_tools()

    for tool in returned:
        original_name = getattr(tool, "_original_name", tool.name)
        assert tool is not stored[original_name]


@pytest.mark.asyncio
async def test_list_tools_does_not_mutate_registered_objects():
    registry = _registry()
    original = await registry.mcp.list_tools()
    snapshot = {tool.name: tool.description for tool in original}

    await registry.mcp.list_tools()
    await registry.mcp.list_tools()

    again = await registry.mcp.list_tools()
    assert {tool.name: tool.description for tool in again} == snapshot


@pytest.mark.asyncio
async def test_two_locales_do_not_bleed_into_each_other():
    """The locale is a ContextVar (localization.core.set_locale), not the LANG
    environment variable -- see localization's core.py. A test that monkeypatches
    LANG would silently exercise nothing and pass for the wrong reason."""
    registry = _registry()

    try:
        set_locale("tr")
        tr = {t.name: t.description for t in await registry.mcp.list_tools()}
        set_locale("en")
        en = {t.name: t.description for t in await registry.mcp.list_tools()}
        set_locale("tr")
        tr_again = {t.name: t.description for t in await registry.mcp.list_tools()}
    finally:
        set_locale("en")

    assert tr == tr_again
    assert tr != en
