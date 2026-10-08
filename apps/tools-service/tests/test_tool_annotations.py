"""Destructive and read-only tools carry MCP ToolAnnotations hints so a
client can gate or confirm calls without special-casing tool names.
Spec TS-9 step 5."""

from pathlib import Path

from fastmcp import FastMCP

from src.core.registry import (
    DESTRUCTIVE_TOOLS,
    READ_ONLY_TOOLS,
    ToolRegistry,
    tool_annotations_for,
)

TOOLS_DIR = str(Path(__file__).resolve().parents[1] / "src" / "tools")


def _registered_tools() -> dict[str, object]:
    mcp = FastMCP("test-annotations-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)
    (local_provider,) = mcp.providers
    return {c.name: c for c in local_provider._components.values() if hasattr(c, "name")}


def test_tool_annotations_for_covers_every_listed_tool_name():
    for name in DESTRUCTIVE_TOOLS:
        assert tool_annotations_for(name) == {"destructiveHint": True}
    for name in READ_ONLY_TOOLS:
        hint = tool_annotations_for(name)
        assert hint is not None
        assert hint["readOnlyHint"] is True


def test_unlisted_tool_gets_no_hint():
    assert tool_annotations_for("json_format") is None


def test_open_world_read_only_tool_is_flagged():
    assert tool_annotations_for("fetch_webpage") == {
        "readOnlyHint": True,
        "openWorldHint": True,
    }


def test_registered_destructive_tools_carry_destructive_hint():
    tools = _registered_tools()
    for name in DESTRUCTIVE_TOOLS:
        assert name in tools, f"{name} not found among registered tools"
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.destructiveHint is True


def test_registered_read_only_tools_carry_read_only_hint():
    tools = _registered_tools()
    for name in READ_ONLY_TOOLS:
        assert name in tools, f"{name} not found among registered tools"
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.readOnlyHint is True
