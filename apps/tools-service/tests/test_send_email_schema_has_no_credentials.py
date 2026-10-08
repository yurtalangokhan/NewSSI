"""The registered `send_email` tool does not ask a model for SMTP credentials.

`smtp_config` was a declared parameter of the MCP tool, so its schema
advertised host, port, username and password as fields the caller supplies.
Anything that could reach the MCP endpoint -- including a prompt-injected
model on the agent path before the wrapper existed -- could therefore point
the platform's mailer at a server of its choosing and have it authenticate
there. Mail is now dispatched by agent-service, which owns the stored
configuration; this endpoint no longer accepts one.
"""

from __future__ import annotations

import inspect
import json

from src.tools import mail_tools


class _Recorder:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *_args: object, **_kwargs: object):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _registered():
    recorder = _Recorder()
    mail_tools.MailTools().register_tools(recorder)
    return recorder.tools["send_email"]


def test_the_tool_is_still_registered():
    assert callable(_registered())


def test_no_parameter_carries_smtp_settings():
    params = inspect.signature(_registered()).parameters

    assert "smtp_config" not in params
    assert not [name for name in params if "smtp" in name or "password" in name]


def test_the_recipient_arguments_are_unchanged():
    params = inspect.signature(_registered()).parameters

    for expected in ("to", "subject", "body", "cc", "bcc", "is_html", "reply_to"):
        assert expected in params


def test_calling_it_directly_refuses_rather_than_relaying():
    result = _registered()(to=["a@example.com"], subject="hi", body="hello")
    parsed = json.loads(result)

    assert parsed["success"] is False
    assert parsed["error_category"] == "configuration"
