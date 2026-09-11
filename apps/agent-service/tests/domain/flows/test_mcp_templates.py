"""Tests for MCP category templates and per-category tool resolvers.

Spec: .tmp/flow-canvas-design.md sections 4.2, 7.3, R4.
Brief: .tmp/flow-canvas-task-29-brief.md
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.exceptions import UnknownOptionsSourceError
from domain.flows.registry import get_registry
from domain.flows.resolvers import ResolverContext, clear_cache, resolve_options
from domain.flows.sources import KNOWN_OPTIONS_SOURCES
from domain.flows.templates.icons import ICON_ALLOWLIST
from models.flows import ComponentKind, FieldType, PortType

# 14 categories registered in Task 29 (MailTools deferred to Task 30)
MCP_CATEGORY_TYPES = [
    "CalculatorTools",
    "CodeTools",
    "CommandTools",
    "DockerTools",
    "FileTools",
    "GitTools",
    "JavaTools",
    "JsonTools",
    "PdfTools",
    "ServiceTools",
    "TextTools",
    "TimeTools",
    "UtilityTools",
    "WebTools",
]

# Every tools-service module. Not all of them become a generic MCP category
# node on the canvas: "mail" is reached through the send_email node and
# "knowledge" through the RAG/knowledge nodes, so they have no template of
# their own — this list tracks the modules, not the templates.
ALL_TOOL_CATEGORIES = [
    "calculator",
    "code",
    "command",
    "docker",
    "file",
    "git",
    "java",
    "json",
    "knowledge",
    "mail",
    "pdf",
    "service",
    "text",
    "time",
    "utility",
    "web",
]


@pytest.fixture
def registry():
    return get_registry()


@pytest.fixture(autouse=True)
def _clear_resolver_cache():
    clear_cache()
    yield
    clear_cache()


def _get_mcp_templates(registry):
    return [
        t
        for templates in registry.list_grouped(include_deprecated=True).values()
        for t in templates
        if t.category == "tools" and t.type in MCP_CATEGORY_TYPES
    ]


def test_mcp_templates_register_without_error(registry):
    """29.1 — 14 category templates registered."""
    registered = {t.type for t in _get_mcp_templates(registry)}
    for type_name in MCP_CATEGORY_TYPES:
        assert type_name in registered, f"Template '{type_name}' not registered"


def test_every_mcp_template_is_a_resource_kind(registry):
    """29.2 — MCP templates are RESOURCE kind (injected, not execution nodes)."""
    for template in _get_mcp_templates(registry):
        assert template.kind == ComponentKind.RESOURCE, (
            f"{template.type} has kind {template.kind!r}, expected RESOURCE"
        )


def test_every_mcp_template_emits_a_tools_handle(registry):
    """29.3 — Every MCP template emits a single output handle of type TOOLS."""
    for template in _get_mcp_templates(registry):
        assert len(template.handles.outputs) == 1, (
            f"{template.type} should have exactly 1 output handle"
        )
        out_handle = template.handles.outputs[0]
        assert out_handle.name == "tools"
        assert PortType.TOOLS in out_handle.types


def test_every_mcp_template_has_a_multiselect_bound_to_its_own_category(registry):
    """29.4 — Each category template has an enabled tools multiselect field with correct source."""
    for template in _get_mcp_templates(registry):
        assert "tools" in template.inputs, f"{template.type} missing 'tools' input field"
        field = template.inputs["tools"]
        assert field.type == FieldType.MULTISELECT
        assert field.required is True
        cat_name = template.type.replace("Tools", "").lower()
        expected_source = f"mcp.tools.{cat_name}"
        assert field.options_source == expected_source, (
            f"{template.type} options_source is '{field.options_source}', expected '{expected_source}'"
        )


def test_every_declared_options_source_is_in_known_sources(registry):
    """29.5 — Every mcp.tools.{category} key must be in KNOWN_OPTIONS_SOURCES."""
    for template in _get_mcp_templates(registry):
        for name, field in template.inputs.items():
            if field.options_source:
                assert field.options_source in KNOWN_OPTIONS_SOURCES, (
                    f"{template.type}.{name} options_source '{field.options_source}' not in KNOWN_OPTIONS_SOURCES"
                )


@pytest.mark.asyncio
async def test_per_category_resolver_returns_only_that_categorys_tools(monkeypatch):
    """29.6 — Core behaviour: resolver returns only the tools belonging to the specified category."""
    from service.MCPToolService import MCPToolService

    mock_service = AsyncMock()
    mock_service.get_tools_by_category.return_value = [
        {"name": "git_clone", "display_name": "Git Clone", "description": "Clone a repo"},
        {"name": "git_commit", "display_name": "Git Commit", "description": "Commit changes"},
    ]

    monkeypatch.setattr(MCPToolService, "get_instance", lambda: mock_service)

    ctx = ResolverContext(user_id="user-123")
    result = await resolve_options("mcp.tools.git", ctx)

    assert result.available is True
    assert result.source == "mcp.tools.git"
    assert len(result.items) == 2
    assert result.items[0].value == "git_clone"
    assert result.items[0].label == "Git Clone"
    assert result.items[1].value == "git_commit"
    mock_service.get_tools_by_category.assert_awaited_once_with("git")


@pytest.mark.asyncio
async def test_per_category_resolver_is_cached_per_user(monkeypatch):
    """29.7 — Result is cached per (source, user_id)."""
    from service.MCPToolService import MCPToolService

    mock_service = AsyncMock()
    mock_service.get_tools_by_category.return_value = [
        {"name": "calc_add", "display_name": "Add", "description": "Add numbers"},
    ]
    monkeypatch.setattr(MCPToolService, "get_instance", lambda: mock_service)

    ctx = ResolverContext(user_id="user-123")
    r1 = await resolve_options("mcp.tools.calculator", ctx)
    r2 = await resolve_options("mcp.tools.calculator", ctx)

    assert r1.items == r2.items
    assert mock_service.get_tools_by_category.await_count == 1

    # Different user -> fetched again
    ctx2 = ResolverContext(user_id="user-456")
    await resolve_options("mcp.tools.calculator", ctx2)
    assert mock_service.get_tools_by_category.await_count == 2


@pytest.mark.asyncio
async def test_unknown_category_key_raises_unknown_options_source():
    """29.8 — Unknown category key raises UnknownOptionsSourceError."""
    ctx = ResolverContext(user_id="user-123")
    with pytest.raises(UnknownOptionsSourceError):
        await resolve_options("mcp.tools.nonexistent", ctx)


def test_registered_categories_match_tools_service_modules():
    """29.9 — Anti-drift: tools-service tools modules match the expected categories."""
    tools_dir = Path(__file__).resolve().parents[4] / "tools-service" / "src" / "tools"
    if not tools_dir.exists():
        tools_dir = Path("/home/alipekisik/Projects/agenticai/apps/tools-service/src/tools")

    if not tools_dir.exists():
        pytest.skip("apps/tools-service not present on disk (container environment)")

    tool_files = list(tools_dir.glob("*_tools.py"))
    disk_categories = sorted(f.name.replace("_tools.py", "") for f in tool_files)

    assert disk_categories == sorted(ALL_TOOL_CATEGORIES), (
        f"tools-service modules {disk_categories} do not match the expected "
        f"categories {sorted(ALL_TOOL_CATEGORIES)}"
    )


def test_every_mcp_template_icon_is_in_the_allowlist(registry):
    """29.10 — Every MCP template declares an icon present in ICON_ALLOWLIST."""
    for template in _get_mcp_templates(registry):
        assert template.icon in ICON_ALLOWLIST, (
            f"{template.type} icon '{template.icon}' not in ICON_ALLOWLIST"
        )
