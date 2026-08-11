"""Streaming state machine for <think> and tool-call markup.

Models without native tool calling write their tool call into the answer text
as `<tool_call>{...}</tool_call>`. Whatever the provider's parser leaves behind
must never be rendered in the chat — but it is also the only sign that a long
document is being written, so it is reported rather than silently dropped.
"""

from api.routes.AgentsRoute import ThinkingTagProcessor


def _feed_all(processor: ThinkingTagProcessor, chunks: list[str]) -> list[dict]:
    events: list[dict] = []
    for chunk in chunks:
        events.extend(processor.feed(chunk))
    events.extend(processor.flush())
    return events


def _text_of(events: list[dict], event_type: str, key: str) -> str:
    return "".join(e[key] for e in events if e["type"] == event_type)


def test_plain_text_streams_through_untouched():
    events = _feed_all(ThinkingTagProcessor(), ["Merhaba ", "dünya"])

    assert _text_of(events, "token", "content") == "Merhaba dünya"


def test_thinking_block_becomes_reasoning():
    events = _feed_all(
        ThinkingTagProcessor(), ["<think>", "düşünüyorum", "</think>", "cevap"]
    )

    assert _text_of(events, "reasoning_delta", "reasoning") == "düşünüyorum"
    assert _text_of(events, "token", "content") == "cevap"


def test_tool_call_markup_never_reaches_the_answer():
    events = _feed_all(
        ThinkingTagProcessor(),
        ['Hazırlıyorum<tool_call>{"name": "create_document"}</tool_call>: bitti'],
    )

    assert _text_of(events, "token", "content") == "Hazırlıyorum: bitti"
    assert _text_of(events, "tool_call_text", "content") == '{"name": "create_document"}'


def test_mid_word_tool_call_is_rejoined():
    events = _feed_all(
        ThinkingTagProcessor(),
        ['bir DOCX dosyası ol<tool_call>{"name": "create_document"}</tool_call>uşturuyorum.'],
    )

    assert _text_of(events, "token", "content") == "bir DOCX dosyası oluşturuyorum."
    assert _text_of(events, "tool_call_text", "content") == '{"name": "create_document"}'



def test_tool_call_markup_split_across_chunks_is_still_caught():
    events = _feed_all(
        ThinkingTagProcessor(),
        ["Hazır", "lıyorum<tool_", 'call>{"name": ', '"create_document"}</tool_', "call>."],
    )

    assert _text_of(events, "token", "content") == "Hazırlıyorum."
    assert "tool_call" not in _text_of(events, "token", "content")


def test_a_closing_tag_whose_opening_was_eaten_is_dropped():
    """Providers sometimes consume the '<' and leave a bare '/tool_call>'."""
    events = _feed_all(ThinkingTagProcessor(), ["cevap/tool_call>", " devam"])

    assert _text_of(events, "token", "content") == "cevap devam"


def test_tool_call_inside_a_thinking_block_is_kept_out_of_the_reasoning():
    events = _feed_all(
        ThinkingTagProcessor(),
        ["<think>plan<tool_call>", '{"name": "create_document"}', "</tool_call>", "</think>ok"],
    )

    assert _text_of(events, "reasoning_delta", "reasoning") == "plan"
    assert _text_of(events, "tool_call_text", "content") == '{"name": "create_document"}'
    assert _text_of(events, "token", "content") == "ok"


def test_unterminated_tool_call_markup_is_not_flushed_as_answer_text():
    events = _feed_all(ThinkingTagProcessor(), ['<tool_call>{"name": "create_do'])

    assert _text_of(events, "token", "content") == ""
    assert "create_do" in _text_of(events, "tool_call_text", "content")


def test_reasoning_start_is_emitted_once():
    events = _feed_all(
        ThinkingTagProcessor(), ["<think>a</think>b<think>c</think>d"]
    )

    assert [e["type"] for e in events].count("reasoning_start") == 1
