from __future__ import annotations

from src.tools.web_tools import (
    extract_title_and_description,
    format_web_search_results,
    web_search_results,
)


def test_format_web_search_results_joins_blocks_with_separator():
    formatted = format_web_search_results(
        [
            {
                "title": "Onyx: Open Source AI Platform",
                "url": "https://onyx.app",
                "snippet": "Onyx is the open source generative AI platform.",
            },
            {
                "title": "Onyx Docs",
                "url": "https://docs.onyx.app",
                "snippet": "Documentation for Onyx.",
            },
        ]
    )

    assert formatted == (
        "TITLE: Onyx: Open Source AI Platform\n"
        "URL: https://onyx.app\n"
        "SNIPPET: Onyx is the open source generative AI platform.\n"
        "---\n"
        "TITLE: Onyx Docs\n"
        "URL: https://docs.onyx.app\n"
        "SNIPPET: Documentation for Onyx."
    )


def test_format_web_search_results_empty_list_returns_empty_string():
    assert format_web_search_results([]) == ""


class _FakeDDGS:
    def __init__(self, results):
        self._results = results

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def text(self, query, max_results=5):
        return self._results[:max_results]


def test_web_search_results_uses_ddgs_when_available(monkeypatch):
    fake_results = [
        {"title": "Onyx", "body": "Open source AI platform.", "href": "https://onyx.app"},
    ]

    def _fake_ddgs_import():
        return _FakeDDGS(fake_results)

    monkeypatch.setattr(
        "src.tools.web_tools._make_ddgs_client",
        _fake_ddgs_import,
    )

    result = web_search_results("Onyx", max_results=5)

    assert "TITLE: Onyx" in result
    assert "URL: https://onyx.app" in result
    assert "SNIPPET: Open source AI platform." in result


def test_extract_title_and_description_finds_both():
    html = """
    <html><head>
      <title>Onyx: Open Source AI Platform</title>
      <meta name="description" content="Onyx connects your company's docs, apps, and people.">
    </head><body><p>hello</p></body></html>
    """

    title, description = extract_title_and_description(html)

    assert title == "Onyx: Open Source AI Platform"
    assert description == "Onyx connects your company's docs, apps, and people."


def test_extract_title_and_description_missing_description_returns_none():
    html = "<html><head><title>Onyx</title></head><body></body></html>"

    title, description = extract_title_and_description(html)

    assert title == "Onyx"
    assert description is None


def test_extract_title_and_description_no_title_returns_none_none():
    html = "<html><body><p>no head at all</p></body></html>"

    assert extract_title_and_description(html) == (None, None)


def test_extract_title_and_description_decodes_html_entities():
    html = "<html><head><title>Onyx &amp; Friends</title></head></html>"

    title, _ = extract_title_and_description(html)

    assert title == "Onyx & Friends"
