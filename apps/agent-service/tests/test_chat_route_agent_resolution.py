from service.ChatAgentResolver import DEFAULT_AGENT, _resolve_custom_persona_agent


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
        "connector_bindings": [],
        "binding_references": {"connectors.persona_id": "19"},
        "_persona_id": 19,
    }


def test_non_dynamic_custom_persona_executes_through_base_agent() -> None:
    assistant_id, llm_override = _resolve_custom_persona_agent(
        20,
        {"base_agent": "configurable-mcp-agent"},
        None,
    )

    assert assistant_id == "configurable-mcp-agent"
    assert llm_override == {
        "connector_bindings": [],
        "binding_references": {"connectors.persona_id": "20"},
        "_persona_id": 20,
    }


def test_custom_persona_uses_only_saved_connector_bindings() -> None:
    saved_bindings = [
        {
            "datasource_id": "9d1ebcbc-9205-4bb0-99aa-5911a13a79b7",
            "operations": ["list_resources", "read"],
        }
    ]

    _assistant_id, llm_override = _resolve_custom_persona_agent(
        20,
        {
            "base_agent": "configurable-mcp-agent",
            "connector_bindings": saved_bindings,
        },
        {
            "connector_bindings": [
                {
                    "datasource_id": "f6c43c0d-f8e8-4f2f-a74a-13826177890b",
                    "operations": ["read"],
                }
            ],
            "binding_references": {"client.value": "ignored"},
        },
    )

    assert llm_override["connector_bindings"] == saved_bindings
    assert llm_override["binding_references"] == {
        "client.value": "ignored",
        "connectors.persona_id": "20",
    }


def test_custom_persona_with_no_saved_connectors_clears_client_override() -> None:
    _assistant_id, llm_override = _resolve_custom_persona_agent(
        20,
        {"base_agent": "configurable-mcp-agent"},
        {
            "connector_bindings": [
                {
                    "datasource_id": "f6c43c0d-f8e8-4f2f-a74a-13826177890b",
                    "operations": ["read"],
                }
            ]
        },
    )

    assert llm_override["connector_bindings"] == []


def test_custom_persona_without_base_agent_uses_default_agent() -> None:
    assistant_id, llm_override = _resolve_custom_persona_agent(21, {}, None)

    assert assistant_id == DEFAULT_AGENT
    assert llm_override == {
        "connector_bindings": [],
        "binding_references": {"connectors.persona_id": "21"},
        "_persona_id": 21,
    }
