"""Flow web node factories (web search, fetch webpage, content crawl, sync trigger)."""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.graphs.flow.state import FlowState, ResolvedResources
from core.observability.logger import get_logger
from schemas.flows import FlowNode

logger = get_logger(__name__)

WEB_CRAWL_TIMEOUT_SECONDS = 60.0


def _make_web_search_node(
    node: FlowNode,
    _resources: ResolvedResources,
    mcp_tools_map: dict[str, Any] | None = None,
) -> Any:
    static_query = str(node.values.get("query") or "")
    max_results = int(node.values.get("max_results", 5))

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        scratch = state.get("scratch", {})
        query = static_query
        for v in scratch.values():
            if isinstance(v, str) and v.strip():
                query = v

        if not query:
            msgs = state.get("messages") or []
            if msgs:
                last_msg = msgs[-1]
                if hasattr(last_msg, "content"):
                    query = str(last_msg.content)
                elif isinstance(last_msg, dict) and "content" in last_msg:
                    query = str(last_msg["content"])
                elif isinstance(last_msg, str):
                    query = last_msg

        if not query:
            return {"scratch": {node.id: []}}

        tools = mcp_tools_map or {}
        tool = tools.get("web_search") or tools.get("web")
        results: list[dict[str, Any]] = []

        if tool:
            try:
                if hasattr(tool, "ainvoke"):
                    raw = await tool.ainvoke({"query": query, "max_results": max_results})
                elif hasattr(tool, "invoke"):
                    raw = tool.invoke({"query": query, "max_results": max_results})
                elif callable(tool):
                    raw = (
                        await tool(query=query, max_results=max_results)
                        if asyncio.iscoroutinefunction(tool)
                        else tool(query=query, max_results=max_results)
                    )
                else:
                    raw = ""

                if isinstance(raw, list):
                    results = raw
                elif isinstance(raw, str):
                    results = [{"content": raw, "query": query}]
                elif isinstance(raw, dict):
                    results = [raw]
            except Exception as exc:
                logger.warning("WebSearch execution failed for node %s: %s", node.id, exc)
                results = []
        else:
            logger.info("WebSearch: no web_search tool in mcp_tools_map; returning empty results")
            results = []

        return {"scratch": {node.id: results}}

    return _run


def _make_fetch_webpage_node(
    node: FlowNode,
    _resources: ResolvedResources,
) -> Any:
    static_url = str(node.values.get("url") or "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        from service.web_search.web_crawl_service import get_web_crawl_service

        scratch = state.get("scratch", {})
        url = static_url
        for v in scratch.values():
            if isinstance(v, str) and (v.startswith("http://") or v.startswith("https://")):
                url = v

        if not url:
            return {"scratch": {node.id: ""}}

        crawl_service = get_web_crawl_service()
        try:
            # The crawler is synchronous (requests + a thread pool); inline
            # on the loop it stalled every other request, health included.
            res = await asyncio.wait_for(
                asyncio.to_thread(crawl_service.crawl_url, url),
                timeout=WEB_CRAWL_TIMEOUT_SECONDS,
            )
            if not res.get("scrape_successful") and res.get("failure_reason"):
                return {"scratch": {node.id: f"Error: {res['failure_reason']}"}}
            content = res.get("content") or ""
            return {"scratch": {node.id: content}}
        except Exception as exc:
            logger.warning("FetchWebpage execution failed for node %s: %s", node.id, exc)
            return {"scratch": {node.id: f"Error: {exc}"}}

    return _run


def _make_content_crawl_node(
    node: FlowNode,
    _resources: ResolvedResources,
) -> Any:
    static_urls_str = str(node.values.get("urls") or "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        from service.web_search.web_crawl_service import get_web_crawl_service

        scratch = state.get("scratch", {})
        urls_str = static_urls_str
        for v in scratch.values():
            if isinstance(v, str) and ("http://" in v or "https://" in v):
                urls_str = v

        urls = [u.strip() for u in urls_str.splitlines() if u.strip()]
        if not urls:
            return {"scratch": {node.id: []}}

        crawl_service = get_web_crawl_service()
        try:
            crawled = await asyncio.wait_for(
                asyncio.to_thread(crawl_service.crawl_urls, urls),
                timeout=WEB_CRAWL_TIMEOUT_SECONDS,
            )
            docs = [
                {
                    "content": item.get("content", ""),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "scrape_successful": item.get("scrape_successful", True),
                    "failure_reason": item.get("failure_reason"),
                }
                for item in crawled
            ]
            return {"scratch": {node.id: docs}}
        except Exception as exc:
            logger.warning("ContentCrawl execution failed for node %s: %s", node.id, exc)
            return {"scratch": {node.id: []}}

    return _run


def _make_sync_trigger_node(node: FlowNode) -> Any:
    datasource_id = str(node.values.get("datasource_id") or "")

    async def _run(state: FlowState, config: RunnableConfig) -> dict[str, Any]:
        from service.datasources.datasource_service import get_datasource_service

        try:
            res = await get_datasource_service().trigger_sync(datasource_id, triggered_by="flow")
            return {"scratch": {node.id: res}}
        except Exception as exc:
            logger.warning(
                "SyncTrigger execution failed for node %s (datasource %s): %s",
                node.id,
                datasource_id,
                exc,
            )
            return {"scratch": {node.id: {"status": "error", "error": str(exc)}}}

    return _run
