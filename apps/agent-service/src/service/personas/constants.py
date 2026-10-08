"""Persona constants and agent-to-persona mappings.

Two different maps used to share the name ``AGENT_TO_PERSONA_ID``: the catalog
map below (nine composable agents, persona ids 1..9) and the preset map that
lived in ``service/threads/session_service.py`` (the two static-registry agents,
persona ids 0 and 1). Same name, two values — and they disagreed about which
agent persona 1 is. They are named apart now, and both live here.
"""

#: Catalog agents that answer under a generic persona id. ``PersonaService`` uses
#: it to recognise an agent id as an authorized invoke/stream target.
AGENT_TO_PERSONA_ID: dict[str, int] = {
    "supervisor": 1,
    "software_engineer": 2,
    "financial_analyst": 3,
    "web_researcher": 4,
    "deep_researcher": 5,
    "document_designer": 6,
    "prompt_engineer": 7,
    "flow_agent": 8,
    "rag_agent": 9,
}

PERSONA_ID_TO_AGENT: dict[int, str] = {v: k for k, v in AGENT_TO_PERSONA_ID.items()}

#: The preset personas chat offers before anything is saved: the two
#: static-registry agents, numbered from zero. ``SessionService.get_personas``
#: numbers the built-in list with this map, and chat routing decodes an incoming
#: numeric persona id with its inverse.
BUILTIN_AGENT_TO_PERSONA_ID: dict[str, int] = {
    "chatbot": 0,
    "configurable-mcp-agent": 1,
}

BUILTIN_PERSONA_ID_TO_AGENT: dict[int, str] = {v: k for k, v in BUILTIN_AGENT_TO_PERSONA_ID.items()}
