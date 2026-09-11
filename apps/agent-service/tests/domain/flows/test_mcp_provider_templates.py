"""Tests for External MCP Provider and Mail resource templates.

Spec: .tmp/flow-canvas-design.md sections 4.7, 7.3.
Brief: .tmp/flow-canvas-task-30-brief.md
"""

from __future__ import annotations

import pytest

from domain.flows.registry import get_registry
from domain.flows.sources import KNOWN_OPTIONS_SOURCES
from domain.flows.templates.icons import ICON_ALLOWLIST
from models.flows import ComponentKind, FieldType, PortType


@pytest.fixture
def registry():
    return get_registry()


def test_mail_config_template_registers_with_mail_configs_source(registry):
    """30.1 — MailConfig resource template exists and uses mail.configs source."""
    template = registry.get("MailConfig")
    assert template.kind == ComponentKind.RESOURCE
    assert template.category == "tools"
    assert "config_id" in template.inputs
    field = template.inputs["config_id"]
    assert field.type == FieldType.OPTIONS
    assert field.required is True
    assert field.options_source == "mail.configs"

    # Emits Data
    assert len(template.handles.outputs) == 1
    assert template.handles.outputs[0].name == "data"
    assert PortType.DATA in template.handles.outputs[0].types


def test_external_mcp_provider_template_registers(registry):
    """30.2 — ExternalMCPServer resource template exists and uses mcp.providers source."""
    template = registry.get("ExternalMCPServer")
    assert template.kind == ComponentKind.RESOURCE
    assert template.category == "tools"
    assert "provider" in template.inputs
    field = template.inputs["provider"]
    assert field.type == FieldType.OPTIONS
    assert field.required is True
    assert field.options_source == "mcp.providers"

    # Emits Tools
    assert len(template.handles.outputs) == 1
    assert template.handles.outputs[0].name == "tools"
    assert PortType.TOOLS in template.handles.outputs[0].types


def test_external_mcp_provider_template_has_a_tools_multiselect(registry):
    """The ExternalMCPServer node lets you pick which of the provider's tools
    to bind, mirroring the built-in category tool nodes."""
    template = registry.get("ExternalMCPServer")
    assert "tools" in template.inputs
    field = template.inputs["tools"]
    assert field.type == FieldType.MULTISELECT
    assert field.options_source == "mcp.external_tools"
    assert field.options_source in KNOWN_OPTIONS_SOURCES
    # provider still renders first, so the tool picker can filter to it
    assert list(template.inputs) == ["provider", "tools"]


def test_mail_tools_declares_a_mail_config_input_handle(registry):
    """30.3 — MailTools template has a mail_config (Data) input handle and tools output."""
    template = registry.get("MailTools")
    assert template.kind == ComponentKind.RESOURCE
    assert template.category == "tools"
    assert "tools" in template.inputs
    assert template.inputs["tools"].options_source == "mcp.tools.mail"

    # Input handle: mail_config -> Data
    assert len(template.handles.inputs) == 1
    in_handle = template.handles.inputs[0]
    assert in_handle.name == "mail_config"
    assert PortType.DATA in in_handle.types

    # Output handle: tools -> Tools
    assert len(template.handles.outputs) == 1
    out_handle = template.handles.outputs[0]
    assert out_handle.name == "tools"
    assert PortType.TOOLS in out_handle.types


def test_new_icons_are_in_the_allowlist(registry):
    """30.9 — ExternalMCPServer, MailConfig, MailTools icons are in the allowlist."""
    for type_name in ("ExternalMCPServer", "MailConfig", "MailTools"):
        template = registry.get(type_name)
        assert template.icon in ICON_ALLOWLIST, (
            f"{type_name} icon '{template.icon}' not in ICON_ALLOWLIST"
        )
