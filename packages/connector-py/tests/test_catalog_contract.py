"""Contract every bundled connector must satisfy, discovered by scanning the package."""

from __future__ import annotations

import importlib
import json
import pkgutil
import tomllib
import xml.dom.minidom
from pathlib import Path

import pytest

import connector.destinations
import connector.sources
from connector import BaseConnector, ConnectorCategory, ConnectorKind, ConnectorRegistry

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _bundled() -> list[type[BaseConnector]]:
    found: dict[tuple[str, str], type[BaseConnector]] = {}
    for package in (connector.sources, connector.destinations):
        for info in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"{package.__name__}.{info.name}")
            for value in vars(module).values():
                if (
                    isinstance(value, type)
                    and issubclass(value, BaseConnector)
                    and value.__module__ == module.__name__
                    and "definition" in vars(value)
                ):
                    found[(value.definition.kind.value, value.definition.name)] = value
    return [found[k] for k in sorted(found)]


CONNECTORS = _bundled()
IDS = [f"{c.definition.kind.value}:{c.definition.name}" for c in CONNECTORS]


def test_expected_number_of_connectors() -> None:
    sources = [c for c in CONNECTORS if c.definition.kind is ConnectorKind.SOURCE]
    destinations = [c for c in CONNECTORS if c.definition.kind is ConnectorKind.DESTINATION]
    assert len(sources) >= 60 and len(destinations) >= 4


@pytest.mark.parametrize("cls", CONNECTORS, ids=IDS)
def test_definition_icon_and_spec(cls: type[BaseConnector]) -> None:
    d = cls.definition
    assert d.name and d.name == d.name.lower() and " " not in d.name
    assert d.display_name and isinstance(d.category, ConnectorCategory)
    svg = cls.icon_svg()
    assert svg, f"{d.name} has no icon"
    xml.dom.minidom.parseString(svg)
    assert "currentColor" in svg or 'fill="#' in svg  # themed generic mark or brand colour

    spec = cls.spec()
    schema = spec.connection_specification
    json.dumps(schema)  # the frontend form renderer needs plain JSON
    assert schema.get("type") == "object" and spec.icon_svg == svg
    for secret in cls.secret_fields():
        prop = schema["properties"][secret]
        assert prop.get("x-secret") is True and prop.get("writeOnly") is True
    likely = [
        n
        for n in schema.get("properties", {})
        if any(w in n.lower() for w in ("password", "secret", "token", "api_key"))
        and not n.endswith(("_url", "_id", "_name"))
    ]
    assert set(likely) <= cls.secret_fields(), f"{d.name}: unmarked secrets {likely}"


def test_every_connector_has_an_entry_point_and_registers() -> None:
    entry_points = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["entry-points"]
    declared = {
        (kind, name): target
        for kind, group in (
            ("source", "connector.sources"),
            ("destination", "connector.destinations"),
        )
        for name, target in entry_points[group].items()
    }
    registry = ConnectorRegistry()
    for cls in CONNECTORS:
        key = (cls.definition.kind.value, cls.definition.name)
        assert key in declared, f"{key} missing from pyproject entry points"
        module, _, attr = declared[key].partition(":")
        assert getattr(importlib.import_module(module), attr) is cls
        registry.register(cls)
    assert len(registry) == len(CONNECTORS)
    assert len(declared) == len(CONNECTORS), set(declared) - {
        (c.definition.kind.value, c.definition.name) for c in CONNECTORS
    }
