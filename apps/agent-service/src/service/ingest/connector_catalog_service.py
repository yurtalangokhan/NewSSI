"""Connector catalog: what can be connected, how it is configured, does it work.

Backed by the in-process connector registry (``packages/connector-py``). A
connector's configuration is a pydantic model; its JSON Schema is reshaped here
into the *form schema* the admin UI renders, and form submissions are turned
back into a configuration the connector accepts.

Form schema rules (kept deliberately small, the UI's renderer is generic):

* ``$ref`` is inlined; ``X | None`` collapses to ``X`` and the field is optional.
* Secret fields keep ``x-secret`` / ``writeOnly`` and render as password inputs.
* A field the renderer has no widget for — a mapping, or a list of objects — is
  presented as a JSON text area; :func:`config_from_form` parses it back.
* A mapping that may hold credentials keeps ``x-sensitive-keys``: in its JSON,
  what a key named like a credential holds is shown as the mask.
"""

from __future__ import annotations

import base64
from copy import deepcopy
from functools import lru_cache
import json
from typing import Any

from connector import BaseSource, ConnectorInfo as RegistryConnectorInfo, ConnectorKind
from connector.base import SENSITIVE_KEYS_KEY
from connector.errors import ConfigValidationError, ConnectorError
from pydantic_core import to_jsonable_python

from core.observability.logger import get_logger
from schemas.connectors import ConnectorInfo, ConnectorSpec
from service.ingest.connector_runtime import get_connector_runtime

logger = get_logger(__name__)

#: Value shown instead of a stored secret; sent back unchanged it means "keep".
SECRET_MASK = "********"  # noqa: S105 - a placeholder, not a credential
_NOT_STORED: Any = object()

_CATEGORY_LABELS: dict[str, str] = {
    "api": "API",
    "saas": "SaaS",
    "knowledge_base": "Knowledge Base",
    "code_repository": "Code Repository",
    "search_engine": "Search Engine",
    "vector_store": "Vector Store",
    "other": "Other",
}
#: Icons drawn in ``currentColor`` would render black inside an ``<img>``; a
#: neutral tone stays visible on both themes.
_NEUTRAL_ICON_COLOR = "#64748b"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def _icon_data_uri(svg: str | None) -> str | None:
    if not svg:
        return None
    encoded = base64.b64encode(svg.replace("currentColor", _NEUTRAL_ICON_COLOR).encode()).decode()
    return f"data:image/svg+xml;base64,{encoded}"


def _to_info(info: RegistryConnectorInfo, source: type[BaseSource]) -> ConnectorInfo:
    return ConnectorInfo(
        name=info.name,
        display_name=info.display_name,
        category=info.category.value if info.category else "other",
        icon_url=info.icon_url or _icon_data_uri(source.icon_svg()),
        documentation_url=info.documentation_url,
        is_available=info.is_available,
    )


def discover_connectors() -> list[ConnectorInfo]:
    """Every source connector visible under the current configuration."""
    registry = get_connector_runtime().registry
    return [_to_info(info, registry.get_source(info.name)) for info in registry.list(ConnectorKind.SOURCE)]


def get_connectors_by_category() -> dict[str, list[ConnectorInfo]]:
    """Connectors grouped by category."""
    by_category: dict[str, list[ConnectorInfo]] = {}
    for connector in discover_connectors():
        by_category.setdefault(connector.category or "other", []).append(connector)
    return by_category


def get_connector_categories() -> list[str]:
    """Sorted category keys, with ``other`` last."""
    categories = sorted(get_connectors_by_category())
    if "other" in categories:
        categories.remove("other")
        categories.append("other")
    return categories


def get_category_labels() -> dict[str, str]:
    """Category key -> display label."""
    return {
        category: _CATEGORY_LABELS.get(category, category.replace("_", " ").title())
        for category in get_connector_categories()
    }


def search_connectors(query: str) -> list[ConnectorInfo]:
    """Connectors whose name or display name contains ``query``."""
    needle = query.lower()
    return [c for c in discover_connectors() if needle in c.name.lower() or needle in c.display_name.lower()]


def find_connector_by_name(connector_name: str) -> ConnectorInfo | None:
    """One visible connector by its machine name (e.g. ``postgres``)."""
    return next((c for c in discover_connectors() if c.name == connector_name), None)


def format_connector_name(connector_name: str) -> str:
    """Display name of a connector; unknown names are title-cased."""
    registry = get_connector_runtime().registry
    try:
        return registry.get_source(connector_name, allow_hidden=True).definition.display_name
    except ConnectorError:
        return connector_name.replace("source-", "").replace("-", " ").replace("_", " ").title()


def get_source_class(connector_name: str) -> type[BaseSource]:
    """The source class of a visible connector. Raises ``ValueError`` when unknown."""
    try:
        return get_connector_runtime().registry.get_source(connector_name)
    except ConnectorError as exc:
        raise ValueError(f"Connector not found: {connector_name}") from exc


# ---------------------------------------------------------------------------
# Form schema
# ---------------------------------------------------------------------------


def _inline_refs(node: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_inline_refs(item, definitions) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        target = deepcopy(definitions.get(ref.removeprefix("#/$defs/"), {}))
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        return _inline_refs({**target, **siblings}, definitions)
    return {key: _inline_refs(value, definitions) for key, value in node.items() if key != "$defs"}


def _collapse_nullable(prop: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """``anyOf: [X, null]`` -> ``X``. Returns the property and whether it was nullable."""
    variants = prop.get("anyOf")
    if not isinstance(variants, list):
        return prop, False
    concrete = [v for v in variants if not (isinstance(v, dict) and v.get("type") == "null")]
    if len(concrete) == len(variants) or len(concrete) != 1:
        return prop, False
    merged = {key: value for key, value in prop.items() if key != "anyOf"}
    merged.update(concrete[0])
    if merged.get("default") is None:
        merged.pop("default", None)
    return merged, True


def _needs_json_editor(prop: dict[str, Any]) -> bool:
    kind = prop.get("type")
    if kind == "object":
        return not prop.get("properties")
    if kind == "array":
        items = prop.get("items")
        return isinstance(items, dict) and items.get("type") in {"object", "array"}
    return False


def _default_of(source: type[BaseSource], name: str) -> Any:
    """The model's default for a field, including one built by a ``default_factory``
    (which JSON Schema does not show)."""
    field = source.Config.model_fields.get(name)
    if field is None or field.is_required():
        return None
    return to_jsonable_python(field.get_default(call_default_factory=True))


def _as_json_editor(prop: dict[str, Any], model_default: Any) -> dict[str, Any]:
    hint = "JSON"
    description = prop.get("description")
    field: dict[str, Any] = {
        "type": "string",
        "format": "textarea",
        "title": prop.get("title"),
        "description": f"{description} ({hint})" if description else hint,
        "x-json": True,
        SENSITIVE_KEYS_KEY: prop.get(SENSITIVE_KEYS_KEY),
    }
    default = prop.get("default", model_default)
    if default not in (None, {}, []):
        field["default"] = json.dumps(default, indent=2)
    return {key: value for key, value in field.items() if value is not None}


@lru_cache(maxsize=256)
def _form_schema(source: type[BaseSource]) -> tuple[dict[str, Any], frozenset[str], frozenset[str]]:
    """``(form schema, fields edited as JSON text, optional fields)`` of a source."""
    raw = source.Config.model_json_schema()
    schema = _inline_refs(raw, raw.get("$defs", {}))
    required = list(schema.get("required", []))
    json_fields: set[str] = set()
    nullable: set[str] = set()
    properties: dict[str, Any] = {}

    names = list(schema.get("properties", {}))
    for name in [n for n in names if n in required] + [n for n in names if n not in required]:
        prop, was_nullable = _collapse_nullable(schema["properties"][name])
        if was_nullable:
            nullable.add(name)
        if _needs_json_editor(prop):
            json_fields.add(name)
            prop = _as_json_editor(prop, _default_of(source, name))
        prop["order"] = len(properties)
        properties[name] = prop

    form = {
        "type": "object",
        "title": schema.get("title"),
        "properties": properties,
        "required": required,
    }
    return form, frozenset(json_fields), frozenset(nullable)


def get_connector_spec(connector_name: str) -> ConnectorSpec:
    """The form schema and metadata of a connector. Raises ``ValueError`` when unknown."""
    source = get_source_class(connector_name)
    form, _json_fields, _nullable = _form_schema(source)
    definition = source.definition
    return ConnectorSpec(
        name=definition.name,
        display_name=definition.display_name,
        connection_specification=deepcopy(form),
        documentation_url=definition.documentation_url,
        supported_sync_modes=[mode.value for mode in source.supported_sync_modes()],
    )


def config_from_form(source: type[BaseSource], submitted: dict[str, Any]) -> dict[str, Any]:
    """Turn a form submission into the raw configuration the connector validates.

    JSON text areas are parsed, and an optional field left blank is dropped so
    its default applies. Raises ``ValueError`` for text that is not valid JSON.
    """
    _form, json_fields, nullable = _form_schema(source)
    config: dict[str, Any] = {}
    for key, value in (submitted or {}).items():
        if isinstance(value, str) and key in json_fields:
            if not value.strip():
                continue
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{key}: not valid JSON ({exc.msg})") from exc
        elif value == "" and key in nullable:
            continue
        config[key] = value
    return config


def config_to_form(source: type[BaseSource], config: dict[str, Any]) -> dict[str, Any]:
    """The stored configuration as the form shows it: secrets masked, JSON fields as text."""
    _form, json_fields, _nullable = _form_schema(source)
    masked = source.mask_config(config, mask=SECRET_MASK)
    return {
        key: json.dumps(value, indent=2) if key in json_fields and not isinstance(value, str) else value
        for key, value in masked.items()
    }


def merge_kept_secrets(
    source: type[BaseSource],
    submitted: dict[str, Any],
    stored: dict[str, Any],
) -> dict[str, Any]:
    """Put stored secrets back where the form returned the mask unchanged.

    That is a secret field, and any place inside a mapping that may hold
    credentials. Raises ``ValueError`` when a mask stands for a secret that is
    not stored: the placeholder is never saved as if it were the secret.
    """
    merged = dict(submitted)
    for field in source.secret_fields():
        if merged.get(field) != SECRET_MASK:
            continue
        if field not in stored:
            raise ValueError(f"{field}: there is no stored value to keep; enter it again")
        merged[field] = stored[field]
    for field in source.sensitive_mapping_fields():
        if field in merged:
            merged[field] = _restore_masks(merged[field], stored.get(field, _NOT_STORED), field)
    return merged


def _restore_masks(submitted: Any, stored: Any, path: str) -> Any:
    """``submitted`` with every mask replaced by what is stored in the same place."""
    if submitted == SECRET_MASK:
        if stored is _NOT_STORED or stored in (None, ""):
            raise ValueError(f"{path}: there is no stored value to keep; enter it again")
        return stored
    if isinstance(submitted, dict):
        kept = stored if isinstance(stored, dict) else {}
        return {
            key: _restore_masks(value, kept.get(key, _NOT_STORED), f"{path}.{key}") for key, value in submitted.items()
        }
    if isinstance(submitted, list):
        kept = stored if isinstance(stored, list) else []
        return [
            _restore_masks(value, kept[index] if index < len(kept) else _NOT_STORED, f"{path}[{index}]")
            for index, value in enumerate(submitted)
        ]
    return submitted


def validated_config(source: type[BaseSource], config: dict[str, Any]) -> dict[str, Any]:
    """Validate ``config`` and return it as plain JSON. Raises ``ValueError`` when invalid."""
    try:
        return source.validate_config(config).model_dump(mode="json")
    except ConfigValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error.get('loc', ())) or 'config'}: {error.get('msg', 'invalid')}"
            for error in exc.errors
        )
        raise ValueError(f"Invalid configuration: {problems}") from exc


# ---------------------------------------------------------------------------
# Connection testing and stream discovery
# ---------------------------------------------------------------------------


async def validate_connector_config(connector_name: str, config: dict[str, Any]) -> bool:
    """Check that ``config`` (a form submission) can reach the source.

    Returns ``True`` when it can; raises ``ValueError`` with the reason otherwise.
    """
    source_class = get_source_class(connector_name)
    clean = validated_config(source_class, config_from_form(source_class, config))
    async with source_class.from_config(clean) as source:
        result = await source.check_connection()
    if not result.ok:
        raise ValueError(f"Connection check failed: {result.message or 'unknown error'}")
    return True


async def get_available_streams(connector_name: str, config: dict[str, Any]) -> list[str]:
    """Stream names a configured connector (a form submission) can read."""
    source_class = get_source_class(connector_name)
    clean = validated_config(source_class, config_from_form(source_class, config))
    async with source_class.from_config(clean) as source:
        catalog = await source.discover()
    return catalog.names()
