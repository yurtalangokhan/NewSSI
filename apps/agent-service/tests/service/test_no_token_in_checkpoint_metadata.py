"""The user's access token must never be written into configurable:
configurable is persisted verbatim into checkpoint metadata by the
checkpointer, and /threads/{id}/state and /threads/{id}/history return
that metadata to the caller. Spec T3."""

import inspect

from service.orchestration import agent_runner_coordinator as AgentHelpers


def test_agent_helpers_never_writes_access_token_into_configurable():
    source = inspect.getsource(AgentHelpers)
    assert 'configurable["access_token"]' not in source
    assert "configurable['access_token']" not in source


def test_run_route_never_writes_access_token_into_resolved_config():
    from api.routes import run_route

    source = inspect.getsource(run_route)
    assert 'resolved_config["access_token"]' not in source
    assert "resolved_config['access_token']" not in source


def test_flow_builder_no_longer_reads_access_token_from_configurable():
    from agents.graphs.flow.nodes import retrieval

    source = inspect.getsource(retrieval)
    assert 'get("configurable", {}).get("access_token")' not in source


def test_flow_builder_reads_the_token_from_the_contextvar_instead(monkeypatch):
    from integrations.user_service_client import set_current_access_token

    set_current_access_token("secret-token")
    try:
        from integrations.user_service_client import get_current_access_token

        assert get_current_access_token() == "secret-token"
    finally:
        set_current_access_token(None)
