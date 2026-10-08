"""Unit tests for web search providers service."""

from __future__ import annotations

from service.web_search.providers import (
    list_content_providers,
    list_search_providers,
)


def test_list_search_providers():
    providers = list_search_providers()
    assert isinstance(providers, list)


def test_list_content_providers():
    providers = list_content_providers()
    assert len(providers) >= 1
    assert providers[0]["provider_type"] == "atlas_web_crawler"
    assert providers[0]["name"] == "ATLAS Web Crawler"
