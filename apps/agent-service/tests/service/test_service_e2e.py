from langchain_core.messages import AIMessage, ToolCall, ToolMessage

from agents.utils import CustomData
from service.utils import langchain_to_chat_message

START_MESSAGE = CustomData(type="start", data={"key1": "value1", "key2": 123})

STATIC_MESSAGES = [
    AIMessage(
        content="",
        tool_calls=[
            ToolCall(
                name="test_tool",
                args={"arg1": "value1"},
                id="test_call_id",
            ),
        ],
    ),
    ToolMessage(content="42", tool_call_id="test_call_id"),
    AIMessage(content="The answer is 42"),
    CustomData(type="end", data={"time": "end"}).to_langchain(),
]


EXPECTED_OUTPUT_MESSAGES = [
    langchain_to_chat_message(m) for m in [START_MESSAGE.to_langchain()] + STATIC_MESSAGES
]


def test_messages_conversion() -> None:
    """Verify that our list of messages is converted to the expected output."""

    messages = EXPECTED_OUTPUT_MESSAGES

    # Verify the sequence of messages
    assert len(messages) == 5

    # First message: Custom data start marker
    assert messages[0].type == "custom"
    assert messages[0].custom_data == {"key1": "value1", "key2": 123}

    # Second message: AI with tool call
    assert messages[1].type == "ai"
    assert len(messages[1].tool_calls) == 1
    assert messages[1].tool_calls[0]["name"] == "test_tool"
    assert messages[1].tool_calls[0]["args"] == {"arg1": "value1"}

    # Third message: Tool response
    assert messages[2].type == "tool"
    assert messages[2].content == "42"
    assert messages[2].tool_call_id == "test_call_id"

    # Fourth message: Final AI response
    assert messages[3].type == "ai"
    assert messages[3].content == "The answer is 42"

    # Fifth message: Custom data end marker
    assert messages[4].type == "custom"
    assert messages[4].custom_data == {"time": "end"}
