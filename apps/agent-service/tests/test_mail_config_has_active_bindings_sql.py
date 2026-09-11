"""``has_active_bindings`` must not emit a JSON ``[]`` subscript.

The persona / agent-definition models type ``mcp_tool_configs`` as ``JSONB``,
so the ORM subscript accessor (``col["send_email"]["mail_config_id"]``) renders
a PostgreSQL ``[]`` subscript. That operator only works on ``jsonb`` — against a
database where the column is still ``json`` it raises
``cannot subscript type json``, which broke deleting a mail configuration
(``DELETE /api/v1/mail-configs/{id}`` -> 500). The ``->`` / ``->>`` operators
behave identically on ``json`` and ``jsonb``, so the query must use those.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from core.db.models.agent_definition import AgentDefinitionModel
from core.db.models.persona import PersonaModel
from core.db.repositories.mail_config_repo import _mail_config_id_ref


def _compiled(column) -> str:
    stmt = select(1).where(_mail_config_id_ref(column) == "cfg-1").limit(1)
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_persona_binding_predicate_uses_arrow_operators_not_subscript():
    sql = _compiled(PersonaModel.mcp_tool_configs)
    assert "mcp_tool_configs -> 'send_email'" in sql
    assert "->> 'mail_config_id'" in sql
    assert "mcp_tool_configs['send_email']" not in sql
    assert "mcp_tool_configs[" not in sql


def test_agent_definition_binding_predicate_uses_arrow_operators_not_subscript():
    sql = _compiled(AgentDefinitionModel.mcp_tool_configs)
    assert "mcp_tool_configs -> 'send_email'" in sql
    assert "->> 'mail_config_id'" in sql
    assert "mcp_tool_configs[" not in sql
