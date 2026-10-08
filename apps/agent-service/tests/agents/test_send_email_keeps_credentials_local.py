"""SMTP credentials never leave the service that owns them.

The wrapped `send_email` tool resolved the user's effective SMTP
configuration -- host, username and cleartext password -- and then handed
the whole thing to the tools-service MCP tool as a call argument. That put
live mail credentials on the wire on every send, and it meant the
tools-service tool had to declare `smtp_config` in its schema, which is
the same field an attacker-steered model would fill in to turn the
platform's mailer into an open relay. agent-service already owns the
configuration and already knows how to send; it now does the send itself.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agents.tooling import mail_tooling


class _RecordingMcpTool:
    name = "send_email"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, payload: dict[str, Any]) -> str:
        self.calls.append(payload)
        return "sent"


class _FakeMailService:
    def __init__(self) -> None:
        self.sends: list[tuple[str, str, dict[str, Any]]] = []
        self.result = {"success": True, "message": "ok", "result": "{}"}

    async def get_effective_user_smtp_config(self, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("the wrapper must not pull credentials out for the wire")

    async def send_email(
        self, user_id: str, config_id: str, payload: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        self.sends.append((user_id, config_id, payload))
        return self.result


@pytest.fixture
def mail_service(monkeypatch: pytest.MonkeyPatch) -> _FakeMailService:
    service = _FakeMailService()
    monkeypatch.setattr("service.auth.mail_config_service.get_mail_config_service", lambda: service)
    return service


def _wrapped(tool: _RecordingMcpTool):
    return mail_tooling.wrap_send_email_tool(
        tool,
        mail_config_id="cfg-1",
        user_id="user-1",
        owner_user_id="owner-1",
    )


@pytest.mark.asyncio
async def test_no_credentials_are_sent_to_the_tools_service(mail_service):
    remote = _RecordingMcpTool()

    await _wrapped(remote).ainvoke({"to": ["a@example.com"], "subject": "hi", "body": "hello"})

    assert remote.calls == [], "the send still went out over MCP with a payload"
    assert mail_service.sends, "the mail was never dispatched"


@pytest.mark.asyncio
async def test_the_send_is_scoped_to_the_caller_and_the_configured_account(mail_service):
    await _wrapped(_RecordingMcpTool()).ainvoke(
        {"to": ["a@example.com"], "subject": "hi", "body": "hello"}
    )

    user_id, config_id, payload = mail_service.sends[0]
    assert user_id == "user-1"
    assert config_id == "cfg-1"
    assert payload["to"] == ["a@example.com"]
    assert payload["subject"] == "hi"
    assert "smtp_config" not in payload


@pytest.mark.asyncio
async def test_a_failed_send_is_reported_rather_than_raised(mail_service):
    mail_service.result = {"success": False, "message": "SMTP refused", "result": "{}"}

    result = await _wrapped(_RecordingMcpTool()).ainvoke(
        {"to": ["a@example.com"], "subject": "hi", "body": "hello"}
    )

    assert "SMTP refused" in str(result)


@pytest.mark.asyncio
async def test_an_agent_without_a_mail_configuration_still_refuses(mail_service):
    tool = mail_tooling.wrap_send_email_tool(
        _RecordingMcpTool(), mail_config_id=None, user_id="user-1"
    )

    result = await tool.ainvoke({"to": ["a@example.com"], "subject": "hi", "body": "hello"})

    assert "mail configuration" in str(result)
    assert mail_service.sends == []


@pytest.mark.asyncio
async def test_the_model_never_sees_an_smtp_field(mail_service):
    schema = _wrapped(_RecordingMcpTool()).args_schema.model_json_schema()

    assert not [
        name for name in schema.get("properties", {}) if "smtp" in name or "password" in name
    ], json.dumps(schema["properties"], indent=2)
