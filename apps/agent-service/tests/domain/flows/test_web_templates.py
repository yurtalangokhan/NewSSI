"""Tests for web component templates and options sources (P8 Task 46).

Spec: .tmp/flow-canvas-design.md section 7.6.
Brief: .tmp/flow-canvas-task-46-brief.md
"""

from __future__ import annotations

import pytest

from domain.flows.registry import get_registry
from domain.flows.resolvers import ResolverContext, resolve_options
from domain.flows.sources import KNOWN_OPTIONS_SOURCES
from domain.flows.templates.icons import ICON_ALLOWLIST
from models.flows import ComponentKind


def test_web_templates_register_without_error():
    """46.1 — Registry accepts all 3 web templates."""
    reg = get_registry()
    ws = reg.get("WebSearch")
    fw = reg.get("FetchWebpage")
    cc = reg.get("ContentCrawl")

    assert ws.category == "web"
    assert fw.category == "web"
    assert cc.category == "web"


def test_all_three_are_execution_kind():
    """46.2 — All three templates declare ComponentKind.EXECUTION."""
    reg = get_registry()
    for name in ("WebSearch", "FetchWebpage", "ContentCrawl"):
        template = reg.get(name)
        assert template.kind == ComponentKind.EXECUTION


def test_web_search_provider_field_is_optional():
    """46.3 — Web Search provider field is optional and advanced."""
    reg = get_registry()
    ws = reg.get("WebSearch")
    provider_field = ws.inputs["provider"]
    assert provider_field.required is False
    assert provider_field.advanced is True
    assert provider_field.options_source == "websearch.providers"


def test_content_crawl_declares_content_providers_source():
    """46.4 — Content Crawl declares websearch.content_providers source, registered in KNOWN_OPTIONS_SOURCES."""
    reg = get_registry()
    cc = reg.get("ContentCrawl")
    assert cc.inputs["provider"].options_source == "websearch.content_providers"
    assert "websearch.content_providers" in KNOWN_OPTIONS_SOURCES


@pytest.mark.asyncio
async def test_content_providers_resolver_returns_the_builtin_crawler():
    """46.5 — Resolving websearch.content_providers returns ATLAS Web Crawler."""
    ctx = ResolverContext(user_id="u1")
    res = await resolve_options("websearch.content_providers", ctx)
    assert res.available is True
    assert len(res.items) >= 1
    assert any("ATLAS" in item.label for item in res.items)


def test_new_icons_are_in_the_allowlist():
    """46.12 — Icons declared by web templates exist in ICON_ALLOWLIST."""
    reg = get_registry()
    for name in ("WebSearch", "FetchWebpage", "ContentCrawl"):
        template = reg.get(name)
        assert template.icon in ICON_ALLOWLIST
