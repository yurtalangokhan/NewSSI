from unittest.mock import AsyncMock, Mock, patch

from langchain_community.chat_models import FakeListChatModel
from langchain_ollama import ChatOllama

from core.llm import get_model


def test_get_model_fake():
    get_model.cache_clear()

    model = get_model("fake")

    assert isinstance(model, FakeListChatModel)
    assert model.responses == ["This is a test response from the fake model."]


def test_get_model_uses_provider_registry_when_model_is_known():
    get_model.cache_clear()
    provider = Mock()
    provider.get_model_instance.return_value = "model-instance"
    registry = Mock()
    registry.initialize.return_value = None
    registry.find_model = AsyncMock(return_value=(provider, {"name": "demo-model"}))

    with patch("core.providers.registry.provider_registry", registry):
        model = get_model("demo-model")

    assert model == "model-instance"
    provider.get_model_instance.assert_called_once_with("demo-model")


def test_get_model_falls_back_to_ollama_for_unknown_model():
    get_model.cache_clear()
    registry = Mock()
    registry.initialize.return_value = None
    registry.find_model = AsyncMock(return_value=(None, None))

    with patch("core.providers.registry.provider_registry", registry):
        with patch("core.llm._ollama_supports_reasoning", return_value=False):
            model = get_model("llama3.1:8b")

    assert isinstance(model, ChatOllama)
    assert model.model == "llama3.1:8b"
