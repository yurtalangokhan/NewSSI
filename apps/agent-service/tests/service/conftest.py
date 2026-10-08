from collections.abc import Callable

import pytest


@pytest.fixture
def persona_factory() -> Callable[[int, str], dict]:
    def build_persona(persona_id: int, owner_id: str) -> dict:
        return {
            "id": persona_id,
            "name": f"Persona {persona_id}",
            "description": "Test persona",
            "user_id": owner_id,
            "mcp_tools": [],
            "rag_config": {"document_processing": [], "knowledge_graph": []},
            "is_public": True,
        }

    return build_persona
