import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents import chatbot as chatbot_module


@pytest.mark.asyncio
async def test_chatbot_injects_runtime_system_prompt(monkeypatch) -> None:
    captured_messages = []

    class FakeModel:
        async def ainvoke(self, messages):
            captured_messages.extend(messages)
            return AIMessage(content="ok")

    monkeypatch.setattr(
        chatbot_module,
        "get_model_from_config",
        lambda configurable, default_model: FakeModel(),
    )

    await chatbot_module.call_model(
        {"messages": [HumanMessage(content="Merhaba")]},
        {"configurable": {"system_prompt": "Always answer in Turkish."}},
        store=None,
    )

    assert isinstance(captured_messages[0], SystemMessage)
    assert captured_messages[0].content == "Always answer in Turkish."
    assert captured_messages[1].content == "Merhaba"
