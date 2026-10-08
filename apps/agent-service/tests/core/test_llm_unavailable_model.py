"""Spec: "no provider could be resolved" must be a type, not a sentence.

`get_model` hands back a fake chat model when no provider answers, and the
only way callers could tell that apart from a real answer was to
substring-match the English prose inside it ("No LLM models are currently
available", "not found"). That is in-band signalling: reword the message and
every caller silently starts treating the apology as a real model response --
which is how "No LLM models are currently available" ended up as a chat
session title.

A deliberate fake model (USE_FAKE_MODEL, model_name="fake") is a different
thing and must NOT be reported as unavailable: it is a working stand-in that
tests ask for on purpose.
"""

from unittest.mock import patch

from infrastructure.llm.llm import FakeToolModel, UnavailableModel, _get_model_direct, is_unavailable_model


def test_unavailable_placeholder_is_recognised_by_type() -> None:
    assert is_unavailable_model(UnavailableModel(responses=["anything at all"])) is True


def test_deliberate_fake_model_is_not_reported_as_unavailable() -> None:
    assert is_unavailable_model(FakeToolModel(responses=["test response"])) is False


def test_real_models_are_not_reported_as_unavailable() -> None:
    assert is_unavailable_model(object()) is False


def test_direct_resolution_without_any_backend_yields_the_placeholder() -> None:
    with (
        patch("infrastructure.llm.llm._ollama_base_url", return_value=""),
        patch.dict("os.environ", {"OLLAMA_BASE_URL": ""}),
    ):
        model = _get_model_direct("llama3.1:8b")

    assert is_unavailable_model(model)


def test_placeholder_is_still_a_usable_chat_model() -> None:
    """It must keep answering, so an unaware caller degrades instead of crashing."""
    model = UnavailableModel(responses=["fallback text"])

    assert isinstance(model, FakeToolModel)
    assert model.invoke("hi").content == "fallback text"
