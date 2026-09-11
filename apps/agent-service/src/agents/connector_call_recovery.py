"""Retry a model that prints a connector call instead of emitting a native call."""

import json
from typing import Any

from i18n import t
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command

_RETRY_MARKER = "connector_native_call_retry"


def recover_connector_call(state: Any, available_tools: set[str]) -> dict | Command | None:
    messages = state["messages"] if isinstance(state, dict) else getattr(state, "messages", [])
    if not messages or not isinstance(messages[-1], AIMessage):
        return None
    answer = messages[-1]
    if answer.tool_calls or not isinstance(answer.content, str):
        return None
    decoder = json.JSONDecoder()
    serialized_call = False
    text = answer.content[:65536]
    for offset, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, offset)
        except ValueError:
            continue
        if (
            isinstance(value, dict)
            and isinstance(value.get("name"), str)
            and value.get("name") in available_tools
            and isinstance(value.get("parameters", value.get("arguments")), dict)
        ):
            serialized_call = True
            break
    if not serialized_call:
        return None

    for message in reversed(messages[:-1]):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, SystemMessage) and message.name == _RETRY_MARKER:
            return {
                "messages": [
                    answer.model_copy(
                        update={
                            "content": t(
                                "connectors.native_call_failed",
                                default="The model did not execute the requested connector tool. Please retry.",
                            )
                        }
                    )
                ]
            }

    return Command(
        goto="agent",
        update={
            "messages": [
                SystemMessage(
                    name=_RETRY_MARKER,
                    content=(
                        "Your last response printed a connector tool call as text, which did not execute. "
                        "Continue using native tool_calls for the available connector tools. Do not print "
                        "tool-call JSON in the answer. If connector_list_resources already succeeded, use "
                        "connector_read with the matching returned resource and assigned datasource ID "
                        "when the user requests its records. Answer using successful read results only; "
                        "report any tool error honestly."
                    ),
                )
            ]
        },
    )
