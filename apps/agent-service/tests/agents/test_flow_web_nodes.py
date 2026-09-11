"""Tests for web execution node handlers in flow_builder (P8 Task 46).

Spec: .tmp/flow-canvas-design.md section 7.6.
Brief: .tmp/flow-canvas-task-46-brief.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.graphs.flow_builder import FlowNode, ResolvedResources, make_node


@pytest.mark.asyncio
async def test_web_search_node_calls_the_mcp_tool_not_a_local_scraper():
    """46.6 — Web Search node calls the web_search tool from mcp_tools_map."""
    mock_tool = AsyncMock()
    mock_tool.ainvoke.return_value = [{"title": "Doc 1", "content": "Search result content"}]

    node = FlowNode(
        id="ws_1",
        type="WebSearch",
        values={"query": "python async", "max_results": 3},
    )
    resources = ResolvedResources()
    runnable = await make_node(node, resources, mcp_tools_map={"web_search": mock_tool})

    state = {"scratch": {}}
    res = await runnable(state, {})

    mock_tool.ainvoke.assert_awaited_once_with({"query": "python async", "max_results": 3})
    assert res["scratch"]["ws_1"] == [{"title": "Doc 1", "content": "Search result content"}]


@pytest.mark.asyncio
async def test_web_search_degrades_to_empty_results_on_tools_service_outage():
    """46.7 — Web Search returns empty list on MCP tool error instead of raising."""
    mock_tool = AsyncMock()
    mock_tool.ainvoke.side_effect = RuntimeError("Tools service 503")

    node = FlowNode(
        id="ws_1",
        type="WebSearch",
        values={"query": "python async"},
    )
    resources = ResolvedResources()
    runnable = await make_node(node, resources, mcp_tools_map={"web_search": mock_tool})

    state = {"scratch": {}}
    res = await runnable(state, {})

    assert res["scratch"]["ws_1"] == []


@pytest.mark.asyncio
async def test_fetch_webpage_node_calls_onyx_crawler_in_process():
    """46.8 — Fetch Webpage node calls WebSearchController in-process."""
    node = FlowNode(
        id="fw_1",
        type="FetchWebpage",
        values={"url": "https://example.com/article"},
    )
    resources = ResolvedResources()
    runnable = await make_node(node, resources)

    mock_ctrl = MagicMock()
    mock_ctrl.crawl_url.return_value = {
        "title": "Example Article",
        "content": "Article body text",
        "scrape_successful": True,
        "failure_reason": None,
    }

    with patch(
        "controller.web_search_controller.get_web_search_controller", return_value=mock_ctrl
    ):
        state = {"scratch": {}}
        res = await runnable(state, {})

    mock_ctrl.crawl_url.assert_called_once_with("https://example.com/article")
    assert res["scratch"]["fw_1"] == "Article body text"


@pytest.mark.asyncio
async def test_fetch_webpage_surfaces_failure_reason_without_raising():
    """46.9 — Bad URL fails the node's output gracefully without raising exception."""
    node = FlowNode(
        id="fw_1",
        type="FetchWebpage",
        values={"url": "https://invalid-host-404.com"},
    )
    resources = ResolvedResources()
    runnable = await make_node(node, resources)

    mock_ctrl = MagicMock()
    mock_ctrl.crawl_url.side_effect = RuntimeError("DNS lookup failed")

    with patch(
        "controller.web_search_controller.get_web_search_controller", return_value=mock_ctrl
    ):
        state = {"scratch": {}}
        res = await runnable(state, {})

    assert "Error: DNS lookup failed" in res["scratch"]["fw_1"]


@pytest.mark.asyncio
async def test_content_crawl_fetches_multiple_urls_in_one_call():
    """46.10 — Content Crawl fetches multiple URLs in a single batch crawl_urls call."""
    node = FlowNode(
        id="cc_1",
        type="ContentCrawl",
        values={"urls": "https://a.com\nhttps://b.com", "provider": "atlas_web_crawler"},
    )
    resources = ResolvedResources()
    runnable = await make_node(node, resources)

    mock_ctrl = MagicMock()
    mock_ctrl.crawl_urls.return_value = [
        {
            "url": "https://a.com",
            "title": "A",
            "content": "Content A",
            "scrape_successful": True,
            "failure_reason": None,
        },
        {
            "url": "https://b.com",
            "title": "B",
            "content": "Content B",
            "scrape_successful": True,
            "failure_reason": None,
        },
    ]

    with patch(
        "controller.web_search_controller.get_web_search_controller", return_value=mock_ctrl
    ):
        state = {"scratch": {}}
        res = await runnable(state, {})

    mock_ctrl.crawl_urls.assert_called_once_with(["https://a.com", "https://b.com"])
    assert len(res["scratch"]["cc_1"]) == 2
    assert res["scratch"]["cc_1"][0]["content"] == "Content A"


@pytest.mark.asyncio
async def test_wired_text_input_overrides_the_static_field():
    """46.11 — An incoming scratch text string overrides static query/url value."""
    mock_tool = AsyncMock()
    mock_tool.ainvoke.return_value = [{"title": "Doc", "content": "Dynamic"}]

    node = FlowNode(
        id="ws_1",
        type="WebSearch",
        values={"query": "static query"},
    )
    resources = ResolvedResources()
    runnable = await make_node(node, resources, mcp_tools_map={"web_search": mock_tool})

    state = {"scratch": {"prompt_1": "dynamic query from upstream"}}
    res = await runnable(state, {})

    mock_tool.ainvoke.assert_awaited_once_with(
        {"query": "dynamic query from upstream", "max_results": 5}
    )
    assert res["scratch"]["ws_1"] == [{"title": "Doc", "content": "Dynamic"}]
