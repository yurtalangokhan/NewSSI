"""WebSearchProgressTracker turns web_search/fetch_webpage tool activity
into the same search_tool_*/open_url_* packets the internal-search and
fetch-tool frontend renderers already consume, instead of the generic
custom_tool_* packets every other tool falls through to."""

from service.WebSearchProgressTracker import WebSearchProgressTracker, is_web_search_tool


def _types(packets) -> list[str]:
    return [p["type"] for p in packets]


def test_is_web_search_tool_only_matches_the_two_tools():
    assert is_web_search_tool("web_search")
    assert is_web_search_tool("fetch_webpage")
    assert not is_web_search_tool("Calculator")
    assert not is_web_search_tool(None)


def test_on_tool_call_returns_none_for_other_tools():
    tracker = WebSearchProgressTracker()

    assert tracker.on_tool_call("Calculator", {"expression": "2+2"}, "call-1") is None


def test_web_search_tool_call_emits_start_and_queries():
    tracker = WebSearchProgressTracker()

    packets = tracker.on_tool_call("web_search", {"query": "Onyx"}, "call-1")

    assert _types(packets) == ["search_tool_start", "search_tool_queries_delta"]
    assert packets[0]["is_internet_search"] is True
    assert packets[1]["queries"] == ["Onyx"]


def test_web_search_tool_call_handles_json_string_args():
    tracker = WebSearchProgressTracker()

    packets = tracker.on_tool_call("web_search", '{"query": "Onyx"}', "call-1")

    assert packets[1]["queries"] == ["Onyx"]


def test_fetch_webpage_tool_call_emits_start_and_url():
    tracker = WebSearchProgressTracker()

    packets = tracker.on_tool_call("fetch_webpage", {"url": "https://onyx.app"}, "call-1")

    assert _types(packets) == ["open_url_start", "open_url_urls"]
    assert packets[1]["urls"] == ["https://onyx.app"]


def test_web_search_result_is_parsed_into_documents():
    tracker = WebSearchProgressTracker()
    tracker.on_tool_call("web_search", {"query": "Onyx"}, "call-1")

    content = (
        "TITLE: Onyx: Open Source AI Platform\n"
        "URL: https://onyx.app\n"
        "SNIPPET: Onyx is the open source generative AI platform.\n"
        "---\n"
        "TITLE: Onyx Docs\n"
        "URL: https://docs.onyx.app\n"
        "SNIPPET: Documentation for Onyx."
    )

    packets = tracker.on_tool_result("web_search", content, "call-1")

    assert _types(packets) == ["search_tool_documents_delta"]
    docs = packets[0]["documents"]
    assert len(docs) == 2
    assert docs[0] == {
        "document_id": "https://onyx.app",
        "semantic_identifier": "Onyx: Open Source AI Platform",
        "link": "https://onyx.app",
        "source_type": "web",
        "blurb": "Onyx is the open source generative AI platform.",
        "boost": 0,
        "hidden": False,
        "score": 1.0,
        "chunk_ind": 0,
        "match_highlights": [],
        "metadata": {},
        "updated_at": None,
        "is_internet": True,
    }
    assert docs[1]["document_id"] == "https://docs.onyx.app"


def test_web_search_result_that_is_an_error_string_emits_empty_documents():
    tracker = WebSearchProgressTracker()
    tracker.on_tool_call("web_search", {"query": "Onyx"}, "call-1")

    packets = tracker.on_tool_result("web_search", "Web search error: timeout", "call-1")

    assert _types(packets) == ["search_tool_documents_delta"]
    assert packets[0]["documents"] == []


def test_fetch_webpage_result_reuses_the_url_from_its_own_tool_call():
    tracker = WebSearchProgressTracker()
    tracker.on_tool_call("fetch_webpage", {"url": "https://onyx.app"}, "call-1")

    content = "TITLE: Onyx\nDESCRIPTION: Open source AI platform.\n---\nFull page body text here."

    packets = tracker.on_tool_result("fetch_webpage", content, "call-1")

    assert _types(packets) == ["open_url_documents"]
    doc = packets[0]["documents"][0]
    assert doc["document_id"] == "https://onyx.app"
    assert doc["link"] == "https://onyx.app"
    assert doc["semantic_identifier"] == "Onyx"
    assert doc["blurb"] == "Open source AI platform."
    assert doc["source_type"] == "web"
    assert doc["is_internet"] is True


def test_fetch_webpage_result_falls_back_to_body_snippet_when_no_description():
    tracker = WebSearchProgressTracker()
    tracker.on_tool_call("fetch_webpage", {"url": "https://onyx.app"}, "call-1")

    content = "TITLE: Onyx\n---\n" + ("body text " * 50)

    packets = tracker.on_tool_result("fetch_webpage", content, "call-1")

    doc = packets[0]["documents"][0]
    assert doc["blurb"] == ("body text " * 50).strip()[:300]


def test_fetch_webpage_result_with_error_or_no_title_gracefully_emits_url_document():
    tracker = WebSearchProgressTracker()
    tracker.on_tool_call("fetch_webpage", {"url": "https://onyx.app/404"}, "call-1")

    packets = tracker.on_tool_result(
        "fetch_webpage", "Error fetching webpage: Client error 404 Not Found", "call-1"
    )

    assert _types(packets) == ["open_url_documents"]
    assert len(packets[0]["documents"]) == 1
    doc = packets[0]["documents"][0]
    assert doc["document_id"] == "https://onyx.app/404"
    assert doc["semantic_identifier"] == "https://onyx.app/404"
    assert "404 Not Found" in doc["blurb"]


def test_fetch_webpage_result_with_unknown_call_id_emits_empty_documents():
    tracker = WebSearchProgressTracker()
    packets = tracker.on_tool_result("fetch_webpage", "Error: failed", "call-unknown")

    assert _types(packets) == ["open_url_documents"]
    assert packets[0]["documents"] == []


def test_on_tool_result_returns_none_for_other_tools():
    tracker = WebSearchProgressTracker()

    assert tracker.on_tool_result("Calculator", "4", "call-1") is None


def test_clone_is_independent_of_the_original():
    tracker = WebSearchProgressTracker()
    tracker.on_tool_call("fetch_webpage", {"url": "https://onyx.app"}, "call-1")

    cloned = tracker.clone()
    cloned.on_tool_call("fetch_webpage", {"url": "https://docs.onyx.app"}, "call-2")

    # The clone learned about call-2; the original must not have.
    assert (
        tracker.on_tool_result("fetch_webpage", "TITLE: Docs\n---\nbody", "call-2")[0]["documents"][
            0
        ]["document_id"]
        == "Docs"
    )
    assert (
        cloned.on_tool_result("fetch_webpage", "TITLE: Docs\n---\nbody", "call-2")[0]["documents"][
            0
        ]["document_id"]
        == "https://docs.onyx.app"
    )
