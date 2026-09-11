from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)

from service.message_conversion import (
    extract_reasoning_from_metadata,
    langchain_to_chat_message,
    split_message_content_reasoning,
)


def test_messages_from_langchain() -> None:
    lc_human_message = HumanMessage(content="Hello, world!")
    human_message = langchain_to_chat_message(lc_human_message)
    assert human_message.type == "human"
    assert human_message.content == "Hello, world!"

    lc_ai_message = AIMessage(content="Hello, world!")
    ai_message = langchain_to_chat_message(lc_ai_message)
    assert ai_message.type == "ai"
    assert ai_message.content == "Hello, world!"

    lc_tool_message = ToolMessage(content="Hello, world!", tool_call_id="123")
    tool_message = langchain_to_chat_message(lc_tool_message)
    assert tool_message.type == "tool"
    assert tool_message.content == "Hello, world!"
    assert tool_message.tool_call_id == "123"

    lc_system_message = SystemMessage(content="Hello, world!")
    try:
        _ = langchain_to_chat_message(lc_system_message)
    except ValueError as e:
        assert str(e) == "Unsupported message type: SystemMessage"


def test_message_run_id_usage() -> None:
    run_id = "847c6285-8fc9-4560-a83f-4e6285809254"
    lc_message = AIMessage(content="Hello, world!")
    ai_message = langchain_to_chat_message(lc_message)
    ai_message.run_id = run_id
    assert ai_message.run_id == run_id


def test_messages_tool_calls() -> None:
    tool_call = ToolCall(name="test_tool", args={"x": 1, "y": 2}, id="call_Jja7")
    lc_ai_message = AIMessage(content="", tool_calls=[tool_call])
    ai_message = langchain_to_chat_message(lc_ai_message)
    assert ai_message.tool_calls[0]["id"] == "call_Jja7"
    assert ai_message.tool_calls[0]["name"] == "test_tool"
    assert ai_message.tool_calls[0]["args"] == {"x": 1, "y": 2}


def test_extract_reasoning_from_metadata_reads_reasoning_content_key() -> None:
    chunk = AIMessageChunk(content="", additional_kwargs={"reasoning_content": "Let me think..."})
    assert extract_reasoning_from_metadata(chunk) == "Let me think..."


def test_extract_reasoning_from_metadata_prefers_reasoning_delta_key() -> None:
    chunk = AIMessageChunk(
        content="",
        additional_kwargs={"reasoning_delta": "delta piece", "reasoning_content": "full so far"},
    )
    assert extract_reasoning_from_metadata(chunk) == "delta piece"


def test_extract_reasoning_from_metadata_falls_back_to_response_metadata() -> None:
    chunk = AIMessageChunk(content="", response_metadata={"thinking": "pondering"})
    assert extract_reasoning_from_metadata(chunk) == "pondering"


def test_extract_reasoning_from_metadata_returns_empty_string_when_absent() -> None:
    chunk = AIMessageChunk(content="hello")
    assert extract_reasoning_from_metadata(chunk) == ""


def test_extract_reasoning_from_metadata_handles_dict_messages() -> None:
    msg = {"additional_kwargs": {"reasoning": "dict-based reasoning"}}
    assert extract_reasoning_from_metadata(msg) == "dict-based reasoning"


def test_extract_reasoning_from_metadata_preserves_whitespace_when_strip_is_false() -> None:
    """Incremental streaming chunks need exact whitespace preserved — a
    leading/trailing space trimmed off one delta glues two words together
    once concatenated with its neighbors."""
    chunk = AIMessageChunk(content="", additional_kwargs={"reasoning_content": " me think..."})
    assert extract_reasoning_from_metadata(chunk, strip=False) == " me think..."
    # Default behavior (whole-message extraction) is unchanged.
    assert extract_reasoning_from_metadata(chunk) == "me think..."


def test_split_message_content_reasoning_plain_string_is_visible() -> None:
    assert split_message_content_reasoning("hello world") == ("", "hello world")


def test_split_message_content_reasoning_non_list_non_string_is_empty() -> None:
    assert split_message_content_reasoning(None) == ("", "")


def test_split_message_content_reasoning_gemini_thinking_block() -> None:
    content = [{"type": "thinking", "thinking": "let me work through 12*12"}]
    assert split_message_content_reasoning(content) == ("let me work through 12*12", "")


def test_split_message_content_reasoning_gemini_thought_flagged_text_block() -> None:
    content = [{"type": "text", "text": "internal notes", "thought": True}]
    assert split_message_content_reasoning(content) == ("internal notes", "")


def test_split_message_content_reasoning_separates_reasoning_from_visible() -> None:
    content = [
        {"type": "thinking", "thinking": "reason A"},
        {"type": "text", "text": "the answer is 144"},
    ]
    assert split_message_content_reasoning(content) == ("reason A", "the answer is 144")


def test_split_message_content_reasoning_joins_visible_string_items() -> None:
    assert split_message_content_reasoning(["foo", "bar"]) == ("", "foobar")


def test_reasoning_extraction_covers_every_provider_shape() -> None:
    """The two extractors together must surface 'thinking' for each provider's
    real output shape, keep the visible answer intact, and never leak encrypted
    (redacted) reasoning."""
    from langchain_core.messages import AIMessage, AIMessageChunk

    def pull(msg):
        meta = extract_reasoning_from_metadata(msg, strip=False)
        block_reasoning, visible = split_message_content_reasoning(msg.content)
        return (meta or block_reasoning), visible

    # Anthropic extended thinking (content blocks, carries a signature)
    r, v = pull(
        AIMessage(
            content=[
                {"type": "thinking", "thinking": "weigh it", "signature": "s"},
                {"type": "text", "text": "42"},
            ]
        )
    )
    assert r == "weigh it" and v == "42"

    # Anthropic redacted thinking must not surface as text
    r, v = pull(
        AIMessage(
            content=[{"type": "redacted_thinking", "data": "ENC"}, {"type": "text", "text": "ok"}]
        )
    )
    assert r == "" and v == "ok"

    # Gemini thought summary + legacy thought=true flag
    r, _ = pull(
        AIMessage(content=[{"type": "thinking", "thinking": "plan"}, {"type": "text", "text": "x"}])
    )
    assert r == "plan"
    r, v = pull(
        AIMessage(
            content=[
                {"type": "text", "text": "inner", "thought": True},
                {"type": "text", "text": "out"},
            ]
        )
    )
    assert r == "inner" and v == "out"

    # Ollama / DeepSeek reasoning_content in additional_kwargs
    r, _ = pull(AIMessage(content="ans", additional_kwargs={"reasoning_content": "cot"}))
    assert r == "cot"

    # Groq reasoning_format="parsed"
    r, _ = pull(AIMessage(content="ans", additional_kwargs={"reasoning": "grq"}))
    assert r == "grq"

    # vLLM streaming reasoning_delta
    r, _ = pull(AIMessageChunk(content="", additional_kwargs={"reasoning_delta": " s "}))
    assert r == " s "

    # OpenAI chat-completions reasoning models expose no reasoning text
    r, v = pull(AIMessage(content="answer", additional_kwargs={}))
    assert r == "" and v == "answer"
