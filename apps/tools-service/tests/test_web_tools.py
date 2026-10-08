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
                "title": "Atlas: Open Source AI Platform",
                "url": "https://atlas.app",
                "snippet": "Atlas is the open source generative AI platform.",
            },
            {
                "title": "Atlas Docs",
                "url": "https://docs.atlas.app",
                "snippet": "Documentation for Atlas.",
            },
        ]
    )

    assert formatted == (
        "TITLE: Atlas: Open Source AI Platform\n"
        "URL: https://atlas.app\n"
        "SNIPPET: Atlas is the open source generative AI platform.\n"
        "---\n"
        "TITLE: Atlas Docs\n"
        "URL: https://docs.atlas.app\n"
        "SNIPPET: Documentation for Atlas."
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
        {"title": "Atlas", "body": "Open source AI platform.", "href": "https://atlas.app"},
    ]

    def _fake_ddgs_import():
        return _FakeDDGS(fake_results)

    monkeypatch.setattr(
        "src.tools.web_tools._make_ddgs_client",
        _fake_ddgs_import,
    )

    result = web_search_results("Atlas", max_results=5)

    assert "TITLE: Atlas" in result
    assert "URL: https://atlas.app" in result
    assert "SNIPPET: Open source AI platform." in result


def test_extract_title_and_description_finds_both():
    html = """
    <html><head>
      <title>Atlas: Open Source AI Platform</title>
      <meta name="description" content="Atlas connects your company's docs, apps, and people.">
    </head><body><p>hello</p></body></html>
    """

    title, description = extract_title_and_description(html)

    assert title == "Atlas: Open Source AI Platform"
    assert description == "Atlas connects your company's docs, apps, and people."


def test_extract_title_and_description_missing_description_returns_none():
    html = "<html><head><title>Atlas</title></head><body></body></html>"

    title, description = extract_title_and_description(html)

    assert title == "Atlas"
    assert description is None


def test_extract_title_and_description_no_title_returns_none_none():
    html = "<html><body><p>no head at all</p></body></html>"

    assert extract_title_and_description(html) == (None, None)


def test_extract_title_and_description_decodes_html_entities():
    html = "<html><head><title>Atlas &amp; Friends</title></head></html>"

    title, _ = extract_title_and_description(html)

    assert title == "Atlas & Friends"


def test_extract_title_and_description_finds_meta_regardless_of_attribute_order():
    # A regex requiring name= to appear textually before content= misses this
    # -- a real parser (matching attributes by name, not source position)
    # does not care about attribute order.
    html = (
        "<html><head><title>Atlas</title>"
        '<meta content="Reversed attribute order." name="description"></head></html>'
    )

    _, description = extract_title_and_description(html)

    assert description == "Reversed attribute order."


def test_extract_title_and_description_recovers_a_title_missing_its_close_tag():
    # No literal </title> appears anywhere in this document, so a regex
    # requiring one to match finds nothing at all (title = None). A real
    # parser still recovers a non-empty title from the malformed input
    # (per HTML5, <title> is RCDATA: everything up to </title> or EOF is
    # its text, tags included) instead of silently discarding it.
    html = "<html><head><title>Broken<body><p>Actual page content.</p></body></html>"

    title, _ = extract_title_and_description(html)

    assert title is not None
    assert "Broken" in title
