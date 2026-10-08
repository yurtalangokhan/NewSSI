from __future__ import annotations

import json
import os
import time
import tomllib
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from connector import (
    ConnectorDisabledError,
    ConnectorKind,
    ConnectorNotFoundError,
    ConnectorRegistry,
    DuplicateConnectorError,
    EnvVisibilitySource,
    FileVisibilitySource,
    LayeredVisibilityPolicy,
    RuntimeOverrides,
    StaticVisibilitySource,
    VisibilityRules,
    default_policy,
)
from connector.destinations.memory import InMemoryDestination
from tests.conftest import FakeSource


def test_register_and_list(registry: ConnectorRegistry) -> None:
    names = [i.name for i in registry.list()]
    assert names == ["memory", "fake"] or set(names) == {"fake", "memory"}
    assert registry.get_source("fake") is FakeSource
    assert registry.get_destination("memory") is InMemoryDestination
    assert "fake" in registry and len(registry) == 2


def test_duplicate_registration_rejected(registry: ConnectorRegistry) -> None:
    class Other(FakeSource):
        pass

    with pytest.raises(DuplicateConnectorError):
        registry.register(Other)
    registry.register(Other, replace=True)
    assert registry.get_source("fake") is Other


def test_unknown_connector(registry: ConnectorRegistry) -> None:
    with pytest.raises(ConnectorNotFoundError):
        registry.get_source("nope")


def test_kind_mismatch_rejected() -> None:
    reg = ConnectorRegistry()
    with pytest.raises(ConnectorNotFoundError):
        reg.get_destination("fake")
    with pytest.raises(TypeError):
        reg.register(object)  # type: ignore[arg-type]


def test_runtime_override_hides_and_restores(registry: ConnectorRegistry) -> None:
    registry.set_enabled("fake", False)
    assert [i.name for i in registry.list(ConnectorKind.SOURCE)] == []
    hidden = registry.list(ConnectorKind.SOURCE, include_hidden=True)
    assert hidden[0].is_available is False
    assert "runtime" in (hidden[0].unavailable_reason or "")
    with pytest.raises(ConnectorDisabledError):
        registry.get_source("fake")
    assert registry.get_source("fake", allow_hidden=True) is FakeSource

    registry.set_enabled("fake", True)
    assert registry.get_source("fake") is FakeSource


def test_env_source_is_read_live(monkeypatch: pytest.MonkeyPatch) -> None:
    reg = ConnectorRegistry(policy=LayeredVisibilityPolicy([EnvVisibilitySource()]))
    reg.register(FakeSource)
    assert reg.is_visible("fake", ConnectorKind.SOURCE)
    monkeypatch.setenv("CONNECTOR_DISABLED", "fa*")
    assert not reg.is_visible("fake", ConnectorKind.SOURCE)
    monkeypatch.setenv("CONNECTOR_DISABLED", "")
    monkeypatch.setenv("CONNECTOR_DEFAULT", "disabled")
    assert not reg.is_visible("fake", ConnectorKind.SOURCE)
    monkeypatch.setenv("CONNECTOR_ENABLED", "fake")
    assert reg.is_visible("fake", ConnectorKind.SOURCE)


def test_file_source_reloads_on_change(tmp_path: Path) -> None:
    cfg = tmp_path / "connectors.json"
    cfg.write_text(json.dumps({"disabled": ["fake"]}), encoding="utf-8")
    src = FileVisibilitySource(cfg)
    reg = ConnectorRegistry(policy=LayeredVisibilityPolicy([src]))
    reg.register(FakeSource)
    assert not reg.is_visible("fake", ConnectorKind.SOURCE)

    time.sleep(0.01)
    cfg.write_text(json.dumps({"enabled": ["fake"]}), encoding="utf-8")
    os.utime(cfg, None)
    # Force a distinct mtime on coarse filesystems.
    st = cfg.stat()
    os.utime(cfg, (st.st_atime, st.st_mtime + 1))
    assert reg.is_visible("fake", ConnectorKind.SOURCE)

    cfg.unlink()
    assert reg.is_visible(
        "fake", ConnectorKind.SOURCE
    )  # missing file -> no opinion -> default visible


def test_file_source_nested_key(tmp_path: Path) -> None:
    cfg = tmp_path / "app.json"
    cfg.write_text(
        json.dumps({"connectors": {"visibility": {"default": "disabled"}}}), encoding="utf-8"
    )
    src = FileVisibilitySource(cfg, key="connectors.visibility")
    assert src.rules().default == "disabled"


def test_tag_rules() -> None:
    rules = VisibilityRules(tags={"disabled": ["testing"]})
    assert rules.decide(FakeSource.definition) == "disabled"
    rules = VisibilityRules(tags={"enabled": ["testing"]}, default="disabled")
    assert rules.decide(FakeSource.definition) == "enabled"
    # explicit deny beats tag allow
    rules = VisibilityRules(disabled=["fake"], tags={"enabled": ["testing"]})
    assert rules.decide(FakeSource.definition) == "disabled"


def test_layer_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = RuntimeOverrides()
    policy = default_policy(overrides=overrides, defaults={"default": "disabled"})
    reg = ConnectorRegistry(policy=policy, overrides=overrides)
    reg.register(FakeSource)

    assert not reg.is_visible("fake", ConnectorKind.SOURCE)  # static default
    monkeypatch.setenv("CONNECTOR_ENABLED", "fake")
    assert reg.is_visible("fake", ConnectorKind.SOURCE)  # env beats defaults
    overrides.set_enabled("fake", False)
    assert not reg.is_visible("fake", ConnectorKind.SOURCE)  # runtime beats env
    overrides.clear("fake")
    assert reg.is_visible("fake", ConnectorKind.SOURCE)


def test_static_source_and_default_visible_false() -> None:
    policy = LayeredVisibilityPolicy(
        [StaticVisibilitySource({"enabled": ["memory"]})], default_visible=False
    )
    reg = ConnectorRegistry(policy=policy)
    reg.register(FakeSource)
    reg.register(InMemoryDestination)
    assert [i.name for i in reg.list()] == ["memory"]


def test_entry_points_load_every_connector_the_package_declares() -> None:
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text("utf-8"))
    declared = project["project"]["entry-points"]
    if not entry_points(group="connector.sources"):
        pytest.skip("package not installed; entry points unavailable")
    reg = ConnectorRegistry()

    # Strict: a connector module that no longer imports fails here, not in a log line.
    count = reg.load_entry_points(strict=True)

    for group, kind in (
        ("connector.sources", ConnectorKind.SOURCE),
        ("connector.destinations", ConnectorKind.DESTINATION),
    ):
        loaded = {info.name for info in reg.list(kind, include_hidden=True)}
        assert loaded == set(declared[group]), "reinstall the package if pyproject.toml changed"
    assert count == sum(len(declared[group]) for group in declared)


def test_a_broken_entry_point_does_not_take_the_catalog_down(monkeypatch, caplog) -> None:
    from connector import registry as registry_module
    from connector.destinations.memory import InMemoryDestination
    from connector.sources.jsonl_file import JsonlFileSource

    class _EntryPoint:
        def __init__(self, name: str, target: object) -> None:
            self.name, self.value, self._target = name, f"pkg:{name}", target

        def load(self) -> object:
            if isinstance(self._target, Exception):
                raise self._target
            return self._target

    def fake_entry_points(*, group: str) -> list[_EntryPoint]:
        if group == registry_module.SOURCE_ENTRY_POINT_GROUP:
            return [
                _EntryPoint("broken", ImportError("built for another version")),
                _EntryPoint("jsonl_file", JsonlFileSource),
                _EntryPoint("not_a_connector", object),
            ]
        return [_EntryPoint("memory", InMemoryDestination)]

    monkeypatch.setattr(registry_module, "entry_points", fake_entry_points)

    registry = ConnectorRegistry()
    with caplog.at_level("ERROR", logger="connector.registry"):
        assert registry.load_entry_points() == 2
    assert "jsonl_file" in registry and "memory" in registry
    assert "broken" in caplog.text and "not_a_connector" in caplog.text

    with pytest.raises(ImportError, match="another version"):
        ConnectorRegistry().load_entry_points(strict=True)


def test_overrides_inside_a_layered_policy_are_found() -> None:
    from connector.sources.jsonl_file import JsonlFileSource

    overrides = RuntimeOverrides()
    policy = LayeredVisibilityPolicy(sources=[overrides])
    registry = ConnectorRegistry(policy=policy)
    registry.register(JsonlFileSource)

    assert registry.overrides is overrides
    registry.set_enabled("jsonl_file", False)
    assert not registry.is_visible("jsonl_file", ConnectorKind.SOURCE)
