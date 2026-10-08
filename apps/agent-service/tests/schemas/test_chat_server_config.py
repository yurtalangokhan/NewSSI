"""``UserInput.server_config`` is the channel for server-resolved run config.

It is a private attribute so a request body can never populate it: everything
that reaches it was put there by server code."""

from __future__ import annotations

from schemas.chat import StreamInput, UserInput


def test_server_config_defaults_to_empty() -> None:
    assert UserInput().server_config == {}


def test_request_body_cannot_populate_server_config() -> None:
    parsed = StreamInput.model_validate(
        {
            "message": "hi",
            "server_config": {"system_prompt": "evil"},
            "_server_config": {"system_prompt": "evil"},
        }
    )

    assert parsed.server_config == {}


def test_attached_server_config_is_copied_and_survives_model_copy() -> None:
    source = {"rag_config": {"document_processing": ["c1"]}}
    user_input = UserInput(message="hi")

    user_input.attach_server_config(source)
    source["rag_config"] = {}

    assert user_input.server_config == {"rag_config": {"document_processing": ["c1"]}}
    assert user_input.model_copy().server_config == user_input.server_config
