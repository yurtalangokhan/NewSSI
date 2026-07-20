from api.routes.ChatRoute import DEFAULT_AGENT, _resolve_custom_persona_agent


def test_dynamic_custom_persona_executes_through_persona_id() -> None:
    assistant_id, llm_override = _resolve_custom_persona_agent(
        19,
        {
            "base_agent": "dynamic-agent",
            "system_prompt": "Coordinate the team.",
            "mcp_tools": [{"id": "tool-1"}],
            "rag_config": {"enabled": True},
        },
        {"model": "test-model"},
    )

    assert assistant_id == "19"
    assert llm_override == {
        "model": "test-model",
        "system_prompt": "Coordinate the team.",
        "mcp_tools": [{"id": "tool-1"}],
        "rag_config": {"enabled": True},
        "_persona_id": 19,
    }


def test_non_dynamic_custom_persona_executes_through_base_agent() -> None:
    assistant_id, llm_override = _resolve_custom_persona_agent(
        20,
        {"base_agent": "configurable-mcp-agent"},
        None,
    )

    assert assistant_id == "configurable-mcp-agent"
    assert llm_override == {"_persona_id": 20}


def test_custom_persona_without_base_agent_uses_default_agent() -> None:
    assistant_id, llm_override = _resolve_custom_persona_agent(21, {}, None)

    assert assistant_id == DEFAULT_AGENT
    assert llm_override == {"_persona_id": 21}
