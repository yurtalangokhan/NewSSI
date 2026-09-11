"""Tests for handle-type compatibility.

Coercions are deliberately asymmetric — silent coercion is how visual builders
produce flows that validate and then behave unexpectedly at runtime.

Spec: .tmp/flow-canvas-design.md section 4.7.
Brief: .tmp/flow-canvas-task-3-brief.md
"""

import itertools

from domain.flows.handle_types import is_compatible
from models.flows import PortType


def test_identical_port_types_are_compatible():
    """3.1 — every type connects to itself."""
    for port in PortType:
        assert is_compatible(port, port) is True


def test_message_flows_into_text():
    """3.2 — a message carries text."""
    assert is_compatible(PortType.MESSAGE, PortType.TEXT) is True


def test_text_does_not_flow_into_message():
    """3.3 — the reverse would silently invent a message role."""
    assert is_compatible(PortType.TEXT, PortType.MESSAGE) is False


def test_documents_require_explicit_adapter_for_text():
    """3.4 — needs an explicit DocumentContext-style node, not a silent cast."""
    assert is_compatible(PortType.DOCUMENTS, PortType.TEXT) is False


def test_data_accepts_any_source_but_feeds_nothing():
    """3.5 — Data is opaque cargo: takes anything (but a signal), yields nothing but Data.

    Trigger is the deliberate exception: it carries no payload, so Trigger
    isolation (3.6) wins over the Data catch-all rather than the other way
    around — a Trigger cannot satisfy a Data port just because Data otherwise
    accepts anything.
    """
    for port in PortType:
        if port is PortType.TRIGGER:
            continue
        assert is_compatible(port, PortType.DATA) is True

    for port in PortType:
        if port is PortType.DATA:
            continue
        assert is_compatible(PortType.DATA, port) is False


def test_trigger_only_connects_to_trigger():
    """3.6 — Trigger is an isolated signal type."""
    for port in PortType:
        if port is PortType.TRIGGER:
            continue
        assert is_compatible(PortType.TRIGGER, port) is False
        assert is_compatible(port, PortType.TRIGGER) is False


def test_compatibility_is_total_over_all_port_pairs():
    """3.7 — every pair returns a bool. A new port type must fail a test
    elsewhere (registry guards), never raise here."""
    for source, target in itertools.product(PortType, PortType):
        assert isinstance(is_compatible(source, target), bool)
