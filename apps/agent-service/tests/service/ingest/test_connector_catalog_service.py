"""The connector catalog: listing, form schemas, and form <-> configuration mapping."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any

from connector import (
    BaseSource,
    Catalog,
    CheckResult,
    ConnectorDefinition,
    ConnectorKind,
    Stream,
    secret_field,
    sensitive_mapping_field,
)
from pydantic import BaseModel, Field
import pytest

from service.ingest import connector_catalog_service as catalog
from service.ingest.connector_runtime import build_registry


class _DemoStream(BaseModel):
    name: str
    glob: str = "**"


class _DemoConfig(BaseModel):
    host: str
    password: str = secret_field(default="")
    port: int = 5432
    database: str | None = None
    tables: list[str] | None = None
    cursor_columns: dict[str, str] = Field(default_factory=dict, description="table -> column")
    headers: dict[str, str] = sensitive_mapping_field(default_factory=dict)
    streams: list[_DemoStream] = Field(default_factory=lambda: [_DemoStream(name="files")])
    reachable: bool = True


class _DemoSource(BaseSource[_DemoConfig]):
    definition = ConnectorDefinition(name="demo", display_name="Demo DB", kind=ConnectorKind.SOURCE)
    Config = _DemoConfig

    async def check(self) -> CheckResult:
        return CheckResult(ok=self.config.reachable, message=None if self.config.reachable else "refused")

    async def discover(self) -> Catalog:
        return Catalog(streams=[Stream(name="orders"), Stream(name="customers")])

    def read(self, catalog: Any, state: Any = None):  # pragma: no cover - not exercised
        raise NotImplementedError


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    monkeypatch.delenv("CONNECTORS_ENABLED", raising=False)
    monkeypatch.delenv("CONNECTORS_DISABLED", raising=False)
    registry = build_registry()
    registry.register(_DemoSource)
    monkeypatch.setattr(catalog, "get_connector_runtime", lambda: SimpleNamespace(registry=registry))
    return registry


def test_catalog_lists_sources_by_category_with_inline_icons():
    by_category = catalog.get_connectors_by_category()
    postgres = next(c for c in by_category["database"] if c.name == "postgres")

    assert postgres.display_name == "PostgreSQL" and postgres.is_available
    assert "source_definition_id" not in postgres.model_dump()
    prefix = "data:image/svg+xml;base64,"
    assert postgres.icon_url.startswith(prefix)
    assert "<svg" in base64.b64decode(postgres.icon_url[len(prefix) :]).decode()

    categories = catalog.get_connector_categories()
    assert set(categories) == set(by_category) and set(catalog.get_category_labels()) == set(categories)
    assert catalog.get_category_labels()["knowledge_base"] == "Knowledge Base"
    assert [c.name for c in catalog.search_connectors("postgre")] == ["postgres"]
    assert catalog.find_connector_by_name("postgres").name == "postgres"
    assert catalog.find_connector_by_name("rag_datasource") is None, "destinations are not offered as sources"


def test_display_names_fall_back_for_names_the_registry_does_not_know():
    assert catalog.format_connector_name("postgres") == "PostgreSQL"
    assert catalog.format_connector_name("source-google-sheets") == "Google Sheets"


def test_form_schema_is_flat_json_with_secrets_and_json_editors():
    spec = catalog.get_connector_spec("demo")
    schema = spec.connection_specification
    props = schema["properties"]

    assert spec.display_name == "Demo DB" and spec.supported_sync_modes == ["full_refresh"]
    assert schema["required"] == ["host"] and next(iter(props)) == "host"
    assert [props[name]["order"] for name in props] == list(range(len(props)))
    assert "$ref" not in json.dumps(schema) and "$defs" not in json.dumps(schema)
    assert props["password"]["x-secret"] is True and props["password"]["writeOnly"] is True
    # ``X | None`` is shown as ``X``; the field is simply optional.
    assert props["database"]["type"] == "string" and "anyOf" not in props["database"]
    assert props["tables"]["type"] == "array" and props["tables"]["items"] == {"type": "string"}
    # No widget exists for a mapping or a list of objects: they are JSON text.
    for name in ("cursor_columns", "streams"):
        assert props[name]["type"] == "string" and props[name]["format"] == "textarea"
        assert props[name]["x-json"] is True
    assert "default" not in props["cursor_columns"]
    assert json.loads(props["streams"]["default"]) == [{"name": "files", "glob": "**"}]
    # A mapping that may hold credentials says so: a mask inside its JSON is a kept value.
    assert props["headers"]["x-json"] is True and props["headers"]["x-sensitive-keys"] is True
    assert "x-sensitive-keys" not in props["cursor_columns"]


def test_every_visible_connector_has_a_renderable_form_schema(registry):
    for info in registry.list(ConnectorKind.SOURCE):
        schema = catalog.get_connector_spec(info.name).connection_specification
        text = json.dumps(schema)
        assert schema["type"] == "object" and "$ref" not in text, info.name
        for name, prop in schema["properties"].items():
            nullable = [v for v in prop.get("anyOf", []) if v.get("type") == "null"]
            assert not nullable, f"{info.name}.{name} still exposes a null variant"


def test_a_form_submission_becomes_a_connector_config():
    submitted = {
        "host": "db",
        "password": "pw",
        "database": "",
        "tables": ["a", "b"],
        "cursor_columns": '{"orders": "updated_at"}',
        "streams": "  ",
    }

    config = catalog.config_from_form(_DemoSource, submitted)

    assert config == {
        "host": "db",
        "password": "pw",
        "tables": ["a", "b"],
        "cursor_columns": {"orders": "updated_at"},
    }
    clean = catalog.validated_config(_DemoSource, config)
    assert clean["database"] is None and clean["streams"] == [{"name": "files", "glob": "**"}]

    with pytest.raises(ValueError, match="cursor_columns: not valid JSON"):
        catalog.config_from_form(_DemoSource, {"host": "db", "cursor_columns": "{oops"})
    with pytest.raises(ValueError, match="host"):
        catalog.validated_config(_DemoSource, {"port": 1})


def test_a_stored_config_is_shown_masked_and_secrets_survive_an_unchanged_form():
    stored = catalog.validated_config(_DemoSource, {"host": "db", "password": "s3cret"})

    shown = catalog.config_to_form(_DemoSource, stored)

    assert shown["password"] == catalog.SECRET_MASK and "s3cret" not in json.dumps(shown)
    assert json.loads(shown["streams"]) == [{"name": "files", "glob": "**"}]
    assert shown["cursor_columns"] == "{}"

    resubmitted = catalog.config_from_form(_DemoSource, {**shown, "host": "db2"})
    merged = catalog.merge_kept_secrets(_DemoSource, resubmitted, stored)
    assert merged["password"] == "s3cret" and merged["host"] == "db2"

    rotated = catalog.merge_kept_secrets(_DemoSource, {**resubmitted, "password": "new"}, stored)
    assert rotated["password"] == "new"

    # The mask stands for what is stored. With nothing stored it would be saved as the secret.
    with pytest.raises(ValueError, match="password: there is no stored value to keep"):
        catalog.merge_kept_secrets(_DemoSource, resubmitted, {"host": "db"})


def test_credentials_inside_a_mapping_field_are_masked_and_survive_an_unchanged_form():
    headers = {"Accept": "application/json", "X-Api-Key": "key-SECRET-1"}
    stored = catalog.validated_config(_DemoSource, {"host": "db", "headers": headers})

    shown = catalog.config_to_form(_DemoSource, stored)

    assert json.loads(shown["headers"]) == {"Accept": "application/json", "X-Api-Key": catalog.SECRET_MASK}
    assert "SECRET" not in json.dumps(shown)

    resubmitted = catalog.config_from_form(_DemoSource, shown)
    assert catalog.merge_kept_secrets(_DemoSource, resubmitted, stored)["headers"] == headers

    # Each entry on its own: one kept, one changed, one added.
    edited = {"Accept": "text/csv", "X-Api-Key": catalog.SECRET_MASK, "X-Auth-Token": "tok-NEW"}
    resubmitted = catalog.config_from_form(_DemoSource, {**shown, "headers": json.dumps(edited)})
    assert catalog.merge_kept_secrets(_DemoSource, resubmitted, stored)["headers"] == {
        "Accept": "text/csv",
        "X-Api-Key": "key-SECRET-1",
        "X-Auth-Token": "tok-NEW",
    }

    # A mask stands for the value stored in its place. Under another key, or with
    # nothing stored, it would be saved as the credential.
    renamed = {**resubmitted, "headers": {"X-Other-Key": catalog.SECRET_MASK}}
    with pytest.raises(ValueError, match=r"headers\.X-Other-Key: there is no stored value to keep"):
        catalog.merge_kept_secrets(_DemoSource, renamed, stored)
    with pytest.raises(ValueError, match=r"headers\.X-Api-Key: there is no stored value to keep"):
        catalog.merge_kept_secrets(_DemoSource, resubmitted, {"host": "db"})


@pytest.mark.asyncio
async def test_validate_and_discover_use_the_submitted_form():
    assert await catalog.validate_connector_config("demo", {"host": "db", "cursor_columns": "{}"}) is True
    assert await catalog.get_available_streams("demo", {"host": "db"}) == ["orders", "customers"]

    with pytest.raises(ValueError, match="Connection check failed: refused"):
        await catalog.validate_connector_config("demo", {"host": "db", "reachable": False})
    with pytest.raises(ValueError, match="Invalid configuration"):
        await catalog.validate_connector_config("demo", {})
    with pytest.raises(ValueError, match="Connector not found"):
        await catalog.validate_connector_config("nope", {})
    with pytest.raises(ValueError, match="Connector not found"):
        catalog.get_connector_spec("file_upload")
