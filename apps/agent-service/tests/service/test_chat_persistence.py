"""
Test for chat session persistence.

This test verifies that:
1. Messages are stored correctly during streaming
2. Messages can be retrieved from the checkpointer
3. The frontend receives the correct message structure
"""


import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver


# Simple test graph that just echoes the message
def create_test_graph():
    from langgraph.graph import END, MessagesState, StateGraph

    async def echo_node(state: MessagesState) -> MessagesState:
        messages = state["messages"]
        last_message = messages[-1] if messages else None
        if last_message and hasattr(last_message, "content"):
            response = AIMessage(content=f"Echo: {last_message.content}")
        else:
            response = AIMessage(content="Hello!")
        return {"messages": [response]}

    workflow = StateGraph(MessagesState)
    workflow.add_node("echo", echo_node)
    workflow.set_entry_point("echo")
    workflow.add_edge("echo", END)

    return workflow.compile(checkpointer=MemorySaver())


@pytest.mark.asyncio
async def test_checkpointer_stores_and_retrieves_messages():
    """Test that the checkpointer correctly stores and retrieves messages."""
    import uuid

    # Create a test graph with a checkpointer
    graph = create_test_graph()
    thread_id = str(uuid.uuid4())

    # Run the graph with a user message
    config = {"configurable": {"thread_id": thread_id}}

    # First run - send a message
    result1 = await graph.ainvoke({"messages": [HumanMessage(content="Hello, world!")]}, config)

    print(f"First run result messages: {len(result1['messages'])}")
    for i, msg in enumerate(result1["messages"]):
        print(
            f"  Message {i}: type={type(msg).__name__}, content={msg.content[:50] if hasattr(msg, 'content') and msg.content else 'N/A'}"
        )

    # Get state from checkpointer
    state = await graph.aget_state(config)
    print(f"\nCheckpointer state values keys: {list(state.values.keys())}")
    print(f"Checkpointer messages count: {len(state.values.get('messages', []))}")

    checkpoint_messages = state.values.get("messages", [])
    for i, msg in enumerate(checkpoint_messages):
        print(
            f"  Checkpoint Message {i}: type={type(msg).__name__}, content={str(msg.content)[:50] if hasattr(msg, 'content') else 'N/A'}"
        )

    # Verify the checkpointer stored the messages
    assert len(checkpoint_messages) >= 2, "Should have at least user + assistant message"

    # Second run - continue the conversation
    result2 = await graph.ainvoke({"messages": [HumanMessage(content="Second message")]}, config)

    print(f"\nSecond run result messages: {len(result2['messages'])}")

    # Get updated state
    state2 = await graph.aget_state(config)
    checkpoint_messages2 = state2.values.get("messages", [])
    print(f"Checkpointer messages after second run: {len(checkpoint_messages2)}")

    for i, msg in enumerate(checkpoint_messages2):
        print(
            f"  Message {i}: type={type(msg).__name__}, content={str(msg.content)[:50] if hasattr(msg, 'content') else 'N/A'}"
        )


@pytest.mark.asyncio
async def test_message_type_detection():
    """Test that message type is correctly detected."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    messages = [
        HumanMessage(content="User message"),
        AIMessage(content="Assistant response"),
        ToolMessage(content="Tool result", tool_call_id="123"),
    ]

    for msg in messages:
        msg_type = "user"  # default
        if hasattr(msg, "type"):
            msg_type = "assistant" if msg.type in ("ai", "tool") else "user"

        print(f"Message: type_attr={getattr(msg, 'type', None)} -> classified as: {msg_type}")


@pytest.mark.asyncio
async def test_content_extraction():
    """Test various content formats."""
    from langchain_core.messages import AIMessage

    # String content
    msg1 = AIMessage(content="Simple string")
    print(f"String content: '{msg1.content}' (type: {type(msg1.content)})")

    # List content
    msg2 = AIMessage(content=[{"type": "text", "text": "List item"}])
    print(f"List content: '{msg2.content}' (type: {type(msg2.content)})")

    # Mixed list
    msg3 = AIMessage(
        content=[
            {"type": "text", "text": "Hello"},
            {"type": "tool_use", "id": "123", "name": "tool"},
        ]
    )
    print(f"Mixed content: '{msg3.content}' (type: {type(msg3.content)})")


if __name__ == "__main__":
    import asyncio

    async def run_tests():
        print("=" * 60)
        print("TEST: Checkpointer stores and retrieves messages")
        print("=" * 60)
        await test_checkpointer_stores_and_retrieves_messages()

        print("\n" + "=" * 60)
        print("TEST: Message type detection")
        print("=" * 60)
        await test_message_type_detection()

        print("\n" + "=" * 60)
        print("TEST: Content extraction")
        print("=" * 60)
        await test_content_extraction()

    asyncio.run(run_tests())
