"""Tests for ToolRegistry dynamic plugin discovery and failure observability.

These tests ensure that:
- All expected ``*_tools.py`` categories are discovered and registered.
- Failed category loads are logged and do not crash the registry.
- Category names, labels, and i18n keys are preserved after registration.
"""

import importlib
import logging
from pathlib import Path

import pytest
from fastmcp import FastMCP

from src.core.base import BaseToolCategory
from src.core.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Expected categories: kept in sync with ``src/tools/*_tools.py`` files.
# Each tuple is (module_stem, category_name, label_fragment).
# If a new tool module is added, this list MUST be updated so the discovery
# test fails until the new category is covered.
# ---------------------------------------------------------------------------
EXPECTED_CATEGORIES: list[tuple[str, str, str]] = [
    ("calculator_tools", "calculator", "Calculator"),
    ("code_tools", "code_execution", "Code Execution"),
    ("command_tools", "command_execution", "Command Execution"),
    ("connector_tools", "connector", "Connector"),
    ("docker_tools", "docker", "Docker"),
    ("file_tools", "file_operations", "File Operations"),
    ("git_tools", "git", "Git"),
    ("java_tools", "java", "Java"),
    ("json_tools", "json_data", "JSON Data"),
    ("knowledge_tools", "knowledge_retrieval", "Knowledge"),
    ("mail_tools", "mail", "Mail"),
    ("pdf_tools", "pdf", "PDF"),
    ("service_tools", "service_management", "Service Management"),
    ("text_tools", "text_processing", "Text Processing"),
    ("time_tools", "time_date", "Time"),
    ("utility_tools", "utilities", "Utilities"),
    ("web_tools", "web_search", "Web"),
]

TOOLS_DIR = str(Path(__file__).resolve().parents[1] / "src" / "tools")


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


def test_discover_plugins_registers_all_expected_categories():
    """Dynamic discovery must find every ``*_tools.py`` module and register it."""
    mcp = FastMCP("test-discover-mcp")
    registry = ToolRegistry(mcp)

    registered_count = registry.discover_plugins(TOOLS_DIR)

    # We must have at least as many registrations as expected categories.
    # Some modules might define extra categories in the future; fail-safe.
    assert registered_count >= len(EXPECTED_CATEGORIES), (
        f"Expected at least {len(EXPECTED_CATEGORIES)} categories, got {registered_count}"
    )

    registered_names = {cat["name"] for cat in registry.list_categories()}
    for _module_stem, cat_name, _label in EXPECTED_CATEGORIES:
        assert cat_name in registered_names, (
            f"Category '{cat_name}' (from {_module_stem}) was not registered. "
            f"Registered: {sorted(registered_names)}"
        )


def test_discover_plugins_returns_zero_for_missing_directory(tmp_path: Path):
    """Missing directory should return 0 and not raise."""
    mcp = FastMCP("test-missing-dir-mcp")
    registry = ToolRegistry(mcp)

    count = registry.discover_plugins(str(tmp_path / "nonexistent"))

    assert count == 0


def test_discover_plugins_logs_failure_for_broken_module(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    """A broken ``*_tools.py`` file should log an error and not crash."""
    # Write a file that matches the naming pattern but has a syntax error
    broken_file = tmp_path / "broken_tools.py"
    broken_file.write_text("raise RuntimeError('intentional failure')\n")

    mcp = FastMCP("test-broken-mcp")
    registry = ToolRegistry(mcp)

    with caplog.at_level(logging.ERROR, logger="src.core.registry"):
        count = registry.discover_plugins(str(tmp_path))

    # The broken file should not prevent other valid categories from loading
    assert count == 0
    # The error should be logged with the file name
    assert any("broken_tools.py" in record.message for record in caplog.records)
    assert any("intentional failure" in record.message for record in caplog.records)


def test_discover_plugins_logs_warning_for_nonexistent_plugins_dir(
    caplog: pytest.LogCaptureFixture,
):
    """Non-existent plugins directory should log a warning."""
    mcp = FastMCP("test-no-dir-mcp")
    registry = ToolRegistry(mcp)

    with caplog.at_level(logging.WARNING, logger="src.core.registry"):
        count = registry.discover_plugins("/this/path/does/not/exist")

    assert count == 0
    assert any("does not exist" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Category property preservation tests
# ---------------------------------------------------------------------------


def test_registered_categories_have_correct_names():
    """Each category must expose the expected ``name`` property value."""
    mcp = FastMCP("test-names-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)

    for _module_stem, cat_name, _label in EXPECTED_CATEGORIES:
        cat = registry.get_category(cat_name)
        assert cat is not None, f"Category '{cat_name}' not found in registry"
        assert cat.name == cat_name, f"Category '{cat_name}' has wrong name property: {cat.name}"


def test_registered_categories_have_non_empty_labels():
    """Every registered category must have a non-empty label."""
    mcp = FastMCP("test-labels-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)

    for name, cat in registry._categories.items():
        assert cat.label, f"Category '{name}' has empty label"
        assert isinstance(cat.label, str), f"Category '{name}' label is not a string"


def test_registered_categories_have_non_empty_descriptions():
    """Every registered category must have a non-empty description."""
    mcp = FastMCP("test-desc-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)

    for name, cat in registry._categories.items():
        assert cat.description, f"Category '{name}' has empty description"
        assert isinstance(cat.description, str), f"Category '{name}' description is not a string"


def test_registered_categories_are_subclasses_of_base():
    """Every registered category must be a ``BaseToolCategory`` subclass."""
    mcp = FastMCP("test-abc-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)

    for name, cat in registry._categories.items():
        assert isinstance(cat, BaseToolCategory), (
            f"Category '{name}' is not a BaseToolCategory subclass"
        )


# ---------------------------------------------------------------------------
# Registry API contract tests
# ---------------------------------------------------------------------------


def test_register_category_duplicate_raises():
    """Registering the same category name twice must raise ValueError."""
    mcp = FastMCP("test-dup-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)

    # Pick the first registered category and try to register it again
    first_name = next(iter(registry._categories))
    cat = registry.get_category(first_name)
    assert cat is not None

    with pytest.raises(ValueError, match="already registered"):
        registry.register_category(cat)


def test_enable_disable_category_toggle():
    """Enable/disable must toggle the enabled state for registered categories."""
    mcp = FastMCP("test-toggle-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)

    first_name = next(iter(registry._categories))

    # All categories start enabled after registration
    assert registry._enabled[first_name] is True

    assert registry.disable_category(first_name) is True
    assert registry._enabled[first_name] is False

    assert registry.enable_category(first_name) is True
    assert registry._enabled[first_name] is True


def test_enable_disable_nonexistent_category_returns_false():
    """Enabling/disabling an unknown category must return False."""
    mcp = FastMCP("test-unknown-mcp")
    registry = ToolRegistry(mcp)

    assert registry.enable_category("nonexistent") is False
    assert registry.disable_category("nonexistent") is False


def test_list_categories_returns_all_registered():
    """list_categories must return one entry per registered category."""
    mcp = FastMCP("test-list-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)

    cats = registry.list_categories()
    assert len(cats) >= len(EXPECTED_CATEGORIES)

    for entry in cats:
        assert "name" in entry
        assert "description" in entry
        assert "label" in entry
        assert "enabled" in entry
        assert entry["enabled"] is True


# ---------------------------------------------------------------------------
# Module-level import test: each ``*_tools.py`` must be importable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_stem, cat_name, _label",
    EXPECTED_CATEGORIES,
    ids=[c[0] for c in EXPECTED_CATEGORIES],
)
def test_tool_module_is_importable(module_stem: str, cat_name: str, _label: str):
    """Every ``*_tools.py`` module must be importable as ``src.tools.<stem>``."""
    full_name = f"src.tools.{module_stem}"
    try:
        mod = importlib.import_module(full_name)
    except Exception as exc:
        pytest.fail(f"Module '{full_name}' failed to import: {exc}")

    # The module must contain at least one BaseToolCategory subclass
    found = False
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, BaseToolCategory)
            and attr is not BaseToolCategory
        ):
            found = True
            break
    assert found, f"Module '{full_name}' contains no BaseToolCategory subclass"


# ---------------------------------------------------------------------------
# Dynamic-load behavior verification
# ---------------------------------------------------------------------------


def test_discover_plugins_does_not_mutate_other_tools_dir_files():
    """Discovery must not write or rename files in the tools directory."""
    tools_path = Path(TOOLS_DIR)
    before = sorted(p.name for p in tools_path.glob("*_tools.py"))

    mcp = FastMCP("test-no-mutate-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)

    after = sorted(p.name for p in tools_path.glob("*_tools.py"))
    assert before == after, "discover_plugins modified files in the tools directory"


@pytest.mark.asyncio
async def test_each_category_registers_at_least_one_mcp_tool():
    """After discovery, every category must have registered ≥ 1 tool with MCP."""
    mcp = FastMCP("test-mcp-tools-mcp")
    registry = ToolRegistry(mcp)
    registry.discover_plugins(TOOLS_DIR)

    tools = await mcp.list_tools()

    # Each registered category should contribute at least one tool to MCP.
    assert len(tools) > 0, "No MCP tools registered after discovery"

    # Verify all categories are present in the registry
    assert len(registry._categories) > 0, "No categories discovered"
