"""
Airbyte Connector Management Module.

This module provides utilities to discover, configure, and run Airbyte source connectors
using PyAirbyte. It enables access to 600+ data source connectors without requiring
the full Airbyte platform.

Connector categories are fetched dynamically from the Airbyte OSS registry
(sourceType field) instead of being hardcoded.

Caching strategy:
  - The OSS registry JSON is cached to disk (AIRBYTE_CACHE_ROOT/registry_cache.json)
    so it survives container restarts. In-memory TTL = 1 hour, disk TTL = 24 hours.
  - Connector specs are cached to disk (AIRBYTE_CACHE_ROOT/specs/<name>.json)
    so connectors don't need to be started just to read the spec.
"""
import asyncio
import json
import logging
import os
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
from functools import lru_cache

import httpx
import airbyte as ab
from langchain_core.documents import Document
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Airbyte OSS Registry URL – contains metadata for all connectors
AIRBYTE_REGISTRY_URL = "https://connectors.airbyte.com/files/registries/v0/oss_registry.json"

# Persistent cache directory (backed by Docker named volume)
_CACHE_DIR = Path(os.environ.get("AIRBYTE_CACHE_ROOT", "/airbyte/cache"))
_REGISTRY_DISK_PATH = _CACHE_DIR / "registry_cache.json"
_SPEC_CACHE_DIR = _CACHE_DIR / "specs"
_ORIGINAL_SPEC_CACHE_DIR = _CACHE_DIR / "specs_original"  # unflattened originals

# Display labels for sourceType values from the registry
SOURCE_TYPE_LABELS: Dict[str, str] = {
    "api": "API",
    "database": "Database",
    "file": "File",
    "custom": "Custom",
    "unknown": "Other",
}

# Retry settings for connector operations (download / install / spec)
_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2  # seconds – linear backoff: 2, 4, 6, 8, 10

# In-memory cache for registry data
_registry_cache: Optional[Dict[str, str]] = None
_registry_cache_time: float = 0
_REGISTRY_MEM_TTL = 3600      # 1 hour  – in-memory
_REGISTRY_DISK_TTL = 86400    # 24 hours – on-disk


def _load_registry_from_disk() -> Optional[Dict[str, str]]:
    """Try to load cached registry from disk."""
    try:
        if _REGISTRY_DISK_PATH.exists():
            stat = _REGISTRY_DISK_PATH.stat()
            age = time.time() - stat.st_mtime
            if age < _REGISTRY_DISK_TTL:
                data = json.loads(_REGISTRY_DISK_PATH.read_text())
                logger.info(
                    f"Loaded registry from disk cache ({len(data)} connectors, "
                    f"age={int(age)}s)"
                )
                return data
            else:
                logger.info("Disk registry cache expired, will re-fetch")
    except Exception as e:
        logger.warning(f"Could not read disk registry cache: {e}")
    return None


def _save_registry_to_disk(data: Dict[str, str]) -> None:
    """Persist registry data to disk."""
    try:
        _REGISTRY_DISK_PATH.parent.mkdir(parents=True, exist_ok=True)
        _REGISTRY_DISK_PATH.write_text(json.dumps(data))
        logger.info(f"Saved registry to disk cache ({len(data)} connectors)")
    except Exception as e:
        logger.warning(f"Could not write disk registry cache: {e}")


def _fetch_registry() -> Dict[str, str]:
    """
    Fetch the Airbyte OSS registry and return a mapping of
    connector docker_repository -> sourceType.

    Uses a 2-level cache:
      1. In-memory (1h TTL) – avoids any I/O
      2. On-disk   (24h TTL) – survives container restarts

    Returns dict like: {"source-postgres": "database", "source-hubspot": "api", ...}
    """
    global _registry_cache, _registry_cache_time

    # Level 1: in-memory cache
    now = time.time()
    if _registry_cache is not None and (now - _registry_cache_time) < _REGISTRY_MEM_TTL:
        return _registry_cache

    # Level 2: disk cache
    disk_data = _load_registry_from_disk()
    if disk_data is not None:
        _registry_cache = disk_data
        _registry_cache_time = now
        return disk_data

    # Level 3: fetch from remote
    source_type_map: Dict[str, str] = {}
    try:
        resp = httpx.get(AIRBYTE_REGISTRY_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for entry in data.get("sources", []):
            docker_repo = entry.get("dockerRepository", "")
            # docker repo is like "airbyte/source-postgres" – strip prefix
            name = docker_repo.split("/")[-1] if "/" in docker_repo else docker_repo
            source_type = entry.get("sourceType", "unknown")
            if name:
                source_type_map[name] = source_type

        logger.info(f"Fetched Airbyte registry from remote: {len(source_type_map)} source connectors")
        _save_registry_to_disk(source_type_map)
    except Exception as e:
        logger.warning(f"Failed to fetch Airbyte registry: {e}")
        # Last resort: try expired disk cache
        try:
            if _REGISTRY_DISK_PATH.exists():
                source_type_map = json.loads(_REGISTRY_DISK_PATH.read_text())
                logger.info(f"Using expired disk cache as fallback ({len(source_type_map)} connectors)")
        except Exception:
            pass

    _registry_cache = source_type_map
    _registry_cache_time = now
    return source_type_map


def get_connector_categories() -> List[str]:
    """
    Get the list of unique categories (sourceType values) from the registry.
    """
    registry = _fetch_registry()
    categories = sorted(set(registry.values()))
    # Ensure 'unknown' is at the end
    if "unknown" in categories:
        categories.remove("unknown")
        categories.append("unknown")
    return categories


def get_category_labels() -> Dict[str, str]:
    """
    Return a mapping of category id -> display label for all known categories.
    """
    categories = get_connector_categories()
    labels: Dict[str, str] = {}
    for cat in categories:
        labels[cat] = SOURCE_TYPE_LABELS.get(cat, f"📦 {cat.title()}")
    return labels


class ConnectorInfo(BaseModel):
    """Information about an Airbyte connector."""
    name: str
    display_name: str
    category: Optional[str] = None
    is_available: bool = True


class ConnectorSpec(BaseModel):
    """Configuration specification for a connector."""
    name: str
    connection_specification: Dict[str, Any]
    documentation_url: Optional[str] = None


def _format_connector_name(connector_name: str) -> str:
    """Convert connector name to human-readable format."""
    # source-postgres -> PostgreSQL
    name = connector_name.replace("source-", "").replace("-", " ")
    # Special cases
    special_names = {
        "postgres": "PostgreSQL",
        "mysql": "MySQL",
        "mongodb v2": "MongoDB",
        "mssql": "Microsoft SQL Server",
        "gcs": "Google Cloud Storage",
        "s3": "Amazon S3",
        "google analytics v4": "Google Analytics (UA)",
        "google analytics data api": "Google Analytics 4",
    }
    return special_names.get(name.lower(), name.title())


def _get_connector_category(connector_name: str) -> str:
    """Get the category (sourceType) for a connector from the Airbyte registry."""
    registry = _fetch_registry()
    return registry.get(connector_name, "unknown")


@lru_cache(maxsize=1)
def get_available_connectors() -> List[str]:
    """
    List all available Airbyte source connectors.
    Results are cached for performance.
    """
    all_known: set[str] = set()

    # Seed with connectors from the Airbyte registry
    registry = _fetch_registry()
    all_known.update(registry.keys())

    try:
        # Try to get full list from PyAirbyte
        connectors = list(ab.get_available_connectors())
        # Filter to source connectors only
        source_connectors = [c for c in connectors if c.startswith("source-")]
        if source_connectors:
            all_known.update(source_connectors)
            logger.info(f"Found {len(source_connectors)} connectors from PyAirbyte")
    except Exception as e:
        logger.warning(f"Could not fetch connectors from PyAirbyte (this is OK if Docker is not running): {e}")

    return sorted(all_known)


def get_connector_list() -> List[ConnectorInfo]:
    """Get list of connectors with metadata."""
    available = get_available_connectors()
    result = []
    
    for name in available:
        result.append(ConnectorInfo(
            name=name,
            display_name=_format_connector_name(name),
            category=_get_connector_category(name),
            is_available=True,
        ))
    
    return result


def get_connectors_by_category() -> Dict[str, List[ConnectorInfo]]:
    """Get connectors organized by category."""
    connectors = get_connector_list()
    by_category: Dict[str, List[ConnectorInfo]] = {}
    
    for connector in connectors:
        category = connector.category or "other"
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(connector)
    
    return by_category


def search_connectors(query: str) -> List[ConnectorInfo]:
    """Search connectors by name."""
    query = query.lower()
    connectors = get_connector_list()
    
    return [
        c for c in connectors 
        if query in c.name.lower() or query in c.display_name.lower()
    ]


def _find_discriminator(option: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """
    Find the discriminator field and its value inside a single oneOf option.

    Airbyte uses two patterns:
      1. ``{"const": "VALUE"}``  (e.g. MongoDB cluster_type)
      2. ``{"enum": ["VALUE"]}`` with a single element (e.g. MySQL method, mode, tunnel_method)

    Returns ``(field_name, discriminator_value)`` or ``(None, None)``.
    """
    for prop_key, prop_value in option.get("properties", {}).items():
        if not isinstance(prop_value, dict):
            continue
        if "const" in prop_value:
            return prop_key, prop_value["const"]
        enum_vals = prop_value.get("enum")
        if isinstance(enum_vals, list) and len(enum_vals) == 1:
            return prop_key, enum_vals[0]
    return None, None


def _flatten_spec_properties(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten Airbyte oneOf specs to expose nested fields at root level.

    Goals:
    * Extract fields from all oneOf variants so the UI can render them.
    * Detect the discriminator field (``const`` **or** single-value ``enum``)
      and expose it as a simple string/enum selector.
    * Only mark fields from the **first (default) variant** as required –
      fields from other variants are optional (they only apply when the user
      picks that variant).
    * Keep normal properties untouched.
    """
    all_properties: Dict[str, Any] = {}
    required: List[str] = list(spec.get("required", []))

    for key, prop_schema in spec.get("properties", {}).items():
        if not isinstance(prop_schema, dict):
            all_properties[key] = prop_schema
            continue

        # ---- oneOf property (e.g. database_config, tunnel_method, ssl_mode) ----
        if "oneOf" in prop_schema and prop_schema.get("type") == "object":
            options = prop_schema["oneOf"]
            logger.info(
                "[FLATTEN] Found nested oneOf in '%s' with %d option(s)",
                key, len(options),
            )

            selector_field: Optional[str] = None
            selector_values: List[str] = []

            for i, option in enumerate(options):
                option_title = option.get("title", f"Option {i}")
                option_props = option.get("properties", {})
                option_required = option.get("required", [])

                disc_field, disc_value = _find_discriminator(option)
                if disc_field:
                    selector_field = disc_field
                    if disc_value not in selector_values:
                        selector_values.append(disc_value)

                logger.info(
                    "[FLATTEN]   option '%s': fields=%s disc=%s=%s",
                    option_title, list(option_props.keys()), disc_field, disc_value,
                )

                for prop_key, prop_value in option_props.items():
                    if not isinstance(prop_value, dict):
                        continue
                    # Skip discriminator – we'll create a clean selector below
                    if prop_key == selector_field:
                        continue
                    if prop_key not in all_properties:
                        all_properties[prop_key] = dict(prop_value)

                # Only the FIRST (default) variant drives required fields.
                # Other variants' fields are optional in the flattened view.
                if i == 0:
                    for req in option_required:
                        if req not in required and req != selector_field:
                            required.append(req)

            # Expose the discriminator as a simple enum selector
            if selector_field and selector_values:
                all_properties[selector_field] = {
                    "type": "string",
                    "title": prop_schema.get("title", key),
                    "description": prop_schema.get("description", ""),
                    "enum": selector_values,
                    "default": selector_values[0],
                    "order": prop_schema.get("order", 0),
                    "group": prop_schema.get("group", "connection"),
                }
                # The discriminator itself is always required
                if selector_field not in required:
                    required.append(selector_field)
                logger.info(
                    "[FLATTEN] Created selector '%s' enum=%s default=%s",
                    selector_field, selector_values, selector_values[0],
                )

            # If the parent key is in the spec-level required list,
            # replace it with the selector field (parent was an object,
            # now it's gone – the selector takes its place).
            if key in required:
                required.remove(key)
                if selector_field and selector_field not in required:
                    required.append(selector_field)
        else:
            # Regular (non-oneOf) property – keep as-is
            all_properties[key] = prop_schema

    result: Dict[str, Any] = {
        "type": "object",
        "properties": all_properties,
        "required": required,
    }
    if "groups" in spec:
        result["groups"] = spec["groups"]

    logger.info("[FLATTEN] Final properties: %s", list(all_properties.keys()))
    logger.info("[FLATTEN] Final required:   %s", required)
    return result



def _get_source_with_retry(connector_name: str, **kwargs) -> Any:
    """
    Wrapper around ab.get_source that retries up to _MAX_RETRIES times
    on transient failures (download errors, Docker pull timeouts, etc.).

    Uses exponential back-off: 3 s, 6 s, 12 s, 24 s, 48 s.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            source = ab.get_source(connector_name, **kwargs)
            if attempt > 1:
                logger.info(
                    f"ab.get_source('{connector_name}') succeeded on attempt {attempt}"
                )
            return source
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * attempt
                logger.warning(
                    f"ab.get_source('{connector_name}') failed (attempt {attempt}/{_MAX_RETRIES}): {exc}  "
                    f"– retrying in {delay}s …"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"ab.get_source('{connector_name}') failed after {_MAX_RETRIES} attempts: {exc}"
                )
    raise last_exc  # type: ignore[misc]


def get_connector_spec(connector_name: str) -> ConnectorSpec:
    """
    Get the configuration specification for a connector.
    This describes what configuration fields are required.

    Specs are cached to disk so that restarting the container doesn't
    require re-pulling and starting the connector Docker image just
    to read the spec.
    """
    # --- Check disk cache first ---
    spec_cache_file = _SPEC_CACHE_DIR / f"{connector_name}.json"
    try:
        if spec_cache_file.exists():
            cached = json.loads(spec_cache_file.read_text())
            logger.info(f"Loaded spec for {connector_name} from disk cache")
            return ConnectorSpec(**cached)
    except Exception as e:
        logger.warning(f"Could not read cached spec for {connector_name}: {e}")

    # --- Fetch from connector ---
    try:
        source = _get_source_with_retry(connector_name, config={}, install_if_missing=True, docker_image=True)
        
        # Handle different PyAirbyte versions
        if hasattr(source, "config_spec"):
            # This is the property that exists in the current version (based on debug logs)
            spec = source.config_spec
        elif hasattr(source, "spec") and not callable(source.spec):
            # Newer versions: spec is a property
            spec = source.spec
        elif hasattr(source, "connector") and hasattr(source.connector, "spec"):
            # Alternative path
            spec = source.connector.spec
        elif hasattr(source, "get_spec"):
            # Older versions
            spec = source.get_spec()
        else:
            # DEBUG: Log again if we still can't find it
            logger.error(f"Source object attributes: {dir(source)}")
            raise AttributeError("Could not find config_spec, spec property or get_spec method on Source object")

        # Convert to dict if it's a Pydantic model or similar
        connection_spec = {}
        if isinstance(spec, dict):
             connection_spec = spec
        elif hasattr(spec, "connectionSpecification"):
             connection_spec = spec.connectionSpecification
        else:
             # Try to convert to dict
             try:
                 spec_dict = spec.dict() if hasattr(spec, "dict") else spec.model_dump() if hasattr(spec, "model_dump") else {}
                 # If config_spec directly returns the schema, use it
                 # Otherwise look for connectionSpecification
                 if "properties" in spec_dict or "type" in spec_dict:
                     connection_spec = spec_dict
                 else:
                     connection_spec = spec_dict.get("connectionSpecification", {})
             except:
                 connection_spec = {}

        # Smart flatten: handles both root-level oneOf AND nested oneOf in properties
        # MongoDB has oneOf inside database_config property, not at root
        has_nested_oneof = any(
            isinstance(p, dict) and "oneOf" in p and p.get("type") == "object"
            for p in connection_spec.get("properties", {}).values()
        )
        if connection_spec and ("oneOf" in connection_spec or has_nested_oneof):
            logger.info(f"Flattening complex spec for {connector_name} (nested oneOf: {has_nested_oneof})")
            # Save the ORIGINAL spec before flattening – needed by _reconstruct_config
            try:
                _ORIGINAL_SPEC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                (_ORIGINAL_SPEC_CACHE_DIR / f"{connector_name}.json").write_text(
                    json.dumps(connection_spec)
                )
                logger.info(f"Cached original (unflattened) spec for {connector_name}")
            except Exception as e:
                logger.warning(f"Could not cache original spec for {connector_name}: {e}")
            connection_spec = _flatten_spec_properties(connection_spec)

        result = ConnectorSpec(
            name=connector_name,
            connection_specification=connection_spec,
            documentation_url=getattr(source, "docs_url", None) or getattr(spec, "documentationUrl", None) if not isinstance(spec, dict) else spec.get("documentationUrl"),
        )

        # Persist flattened spec to disk cache
        try:
            _SPEC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            spec_cache_file.write_text(result.model_dump_json())
            logger.info(f"Cached spec for {connector_name} to disk")
        except Exception as e:
            logger.warning(f"Could not cache spec for {connector_name}: {e}")

        return result
    except Exception as e:
        logger.error(f"Failed to get spec for {connector_name}: {e}")
        raise ValueError(f"Could not get specification for connector: {connector_name}")




# ---------------------------------------------------------------------------
# Generic spec-driven config reconstruction
# ---------------------------------------------------------------------------

def _load_original_spec(connector_name: str) -> Optional[Dict[str, Any]]:
    """Load the original (unflattened) spec from the disk cache."""
    path = _ORIGINAL_SPEC_CACHE_DIR / f"{connector_name}.json"
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        logger.warning(f"Could not read original spec for {connector_name}: {e}")
    return None


def _reconstruct_config(connector_name: str, flat_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct the nested config structure that the Airbyte connector expects
    from the flat key/value pairs sent by the UI.

    **How it works (generic, spec-driven)**:
    1. Load the *original* (pre-flatten) JSON-Schema spec from disk.
    2. Identify every root-level property whose schema is ``{type: object, oneOf: [...]}``.
    3. For each such property, find the *discriminator field* (single-enum or const)
       and look up its value in ``flat_config``.
    4. Match the value to the correct oneOf variant, collect only the fields that
       belong to that variant, and nest them under the parent key.
    5. Remove the consumed fields from the root-level config.

    Falls back to **connector-specific** fixups for MongoDB v2 when the original
    spec is not available.
    """
    original_spec = _load_original_spec(connector_name)

    if original_spec is not None:
        return _reconstruct_from_spec(original_spec, flat_config, connector_name)

    # ------------------------------------------------------------------
    # Fallback: legacy MongoDB-specific reconstruction
    # ------------------------------------------------------------------
    if connector_name == "source-mongodb-v2":
        return _reconstruct_mongodb_config(flat_config)

    return flat_config


def _reconstruct_from_spec(
    original_spec: Dict[str, Any],
    flat_config: Dict[str, Any],
    connector_name: str,
) -> Dict[str, Any]:
    """
    Generic reconstruction using the original (unflattened) JSON-Schema.

    For every root-level property that is a ``oneOf`` object:
    * Determine which variant matches via the discriminator value.
    * Collect flat-config fields that belong to that variant.
    * Nest them under the parent property name.
    * Inject defaults for any fields that the variant requires but the
      user did not supply.
    """
    result = dict(flat_config)  # shallow copy
    consumed_keys: set[str] = set()

    for parent_key, prop_schema in original_spec.get("properties", {}).items():
        if not isinstance(prop_schema, dict):
            continue
        if "oneOf" not in prop_schema or prop_schema.get("type") != "object":
            continue

        options = prop_schema["oneOf"]

        # --- find discriminator field & its user-supplied value -----------
        disc_field: Optional[str] = None
        disc_values_by_option: Dict[int, str] = {}  # option-idx -> disc value

        for i, opt in enumerate(options):
            df, dv = _find_discriminator(opt)
            if df:
                disc_field = df
                disc_values_by_option[i] = dv  # type: ignore[assignment]

        if not disc_field:
            logger.debug(
                "[RECONSTRUCT] No discriminator found for '%s' – skipping", parent_key
            )
            continue

        # What value did the user pick?  May come from flat_config or use default.
        user_value = flat_config.get(disc_field)
        if user_value is None:
            # Fallback: first variant's default
            user_value = disc_values_by_option.get(0)
        if user_value is None:
            continue

        # --- find the matching variant ------------------------------------
        matched_idx: Optional[int] = None
        for idx, dv in disc_values_by_option.items():
            if dv == user_value:
                matched_idx = idx
                break

        if matched_idx is None:
            # No exact match – take the first variant as default
            matched_idx = 0
            user_value = disc_values_by_option.get(0, user_value)

        matched_option = options[matched_idx]
        variant_props = matched_option.get("properties", {})

        logger.info(
            "[RECONSTRUCT] '%s' → variant %d (%s=%s), fields=%s",
            parent_key, matched_idx, disc_field, user_value,
            list(variant_props.keys()),
        )

        # --- collect fields for this variant ------------------------------
        nested: Dict[str, Any] = {}
        for field_name, field_schema in variant_props.items():
            if not isinstance(field_schema, dict):
                continue
            if field_name in flat_config:
                val = flat_config[field_name]
                # Type coercion: arrays sent as comma-separated strings
                if field_schema.get("type") == "array" and isinstance(val, str):
                    val = [v.strip() for v in val.split(",") if v.strip()] if val.strip() else []
                # Type coercion: integers
                if field_schema.get("type") == "integer" and isinstance(val, str):
                    try:
                        val = int(val)
                    except ValueError:
                        pass
                # Type coercion: booleans
                if field_schema.get("type") == "boolean" and isinstance(val, str):
                    val = val.lower() in ("true", "1", "yes")
                nested[field_name] = val
                consumed_keys.add(field_name)
            elif "default" in field_schema:
                nested[field_name] = field_schema["default"]
            elif "const" in field_schema:
                nested[field_name] = field_schema["const"]
            elif "enum" in field_schema and len(field_schema["enum"]) == 1:
                nested[field_name] = field_schema["enum"][0]

        # Ensure discriminator is always present
        if disc_field not in nested:
            nested[disc_field] = user_value

        result[parent_key] = nested

    # Remove consumed keys from root level
    for k in consumed_keys:
        result.pop(k, None)
    # Also remove the parent keys if they were strings (leftover from flat)
    for parent_key, prop_schema in original_spec.get("properties", {}).items():
        if isinstance(prop_schema, dict) and "oneOf" in prop_schema:
            if parent_key in result and not isinstance(result[parent_key], dict):
                result.pop(parent_key, None)

    # --- MongoDB-specific fixups (array coercion, defaults) ---------------
    if connector_name == "source-mongodb-v2":
        result = _mongodb_post_fixup(result)

    logger.info("[RECONSTRUCT] %s final keys: %s", connector_name, list(result.keys()))
    return result


# ---------------------------------------------------------------------------
# MongoDB-specific helpers (kept for backward compat)
# ---------------------------------------------------------------------------

def _mongodb_post_fixup(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extra fixups for MongoDB v2 after generic reconstruction."""
    db_config = config.get("database_config")
    if isinstance(db_config, dict):
        # databases must be a list
        if "databases" in db_config:
            val = db_config["databases"]
            if isinstance(val, str):
                db_config["databases"] = [v.strip() for v in val.split(",") if v.strip()] if val.strip() else []
        # auth_source default
        if not db_config.get("auth_source"):
            db_config["auth_source"] = "admin"
        # schema_enforced default
        if "schema_enforced" not in db_config:
            db_config["schema_enforced"] = True
    # initial_waiting_seconds default
    if "initial_waiting_seconds" not in config:
        config["initial_waiting_seconds"] = 30
    return config


def _reconstruct_mongodb_config(flat_config: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy MongoDB-only reconstruction (fallback when no original spec)."""
    db_config_fields = [
        "cluster_type", "connection_string", "databases",
        "username", "password", "auth_source", "schema_enforced"
    ]
    database_config: Dict[str, Any] = {}
    other_config: Dict[str, Any] = {}
    for key, value in flat_config.items():
        if key in db_config_fields:
            database_config[key] = value
        else:
            other_config[key] = value
    # databases: string -> array
    if "databases" in database_config:
        db_value = database_config["databases"]
        if isinstance(db_value, str):
            if "," in db_value:
                database_config["databases"] = [d.strip() for d in db_value.split(",") if d.strip()]
            elif db_value.strip():
                database_config["databases"] = [db_value.strip()]
            else:
                database_config["databases"] = []
        elif not isinstance(db_value, list):
            database_config["databases"] = [str(db_value)] if db_value else []
    if not database_config.get("auth_source"):
        database_config["auth_source"] = "admin"
    if "schema_enforced" not in database_config:
        database_config["schema_enforced"] = True
    if "cluster_type" in database_config:
        ct = database_config["cluster_type"]
        valid_types = ["ATLAS_REPLICA_SET", "SELF_MANAGED_REPLICA_SET"]
        if ct not in valid_types:
            ct_upper = ct.upper().replace(" ", "_").replace("-", "_")
            database_config["cluster_type"] = "ATLAS_REPLICA_SET" if "ATLAS" in ct_upper else "SELF_MANAGED_REPLICA_SET"
    else:
        database_config["cluster_type"] = "ATLAS_REPLICA_SET"
    if "initial_waiting_seconds" not in other_config:
        other_config["initial_waiting_seconds"] = 30
    other_config["database_config"] = database_config
    logger.info(
        "[RECONSTRUCT] MongoDB config: cluster_type=%s, databases=%s, auth_source=%s",
        database_config.get("cluster_type"),
        database_config.get("databases"),
        database_config.get("auth_source"),
    )
    return other_config


def validate_connector_config(connector_name: str, config: Dict[str, Any]) -> bool:
    """
    Validate configuration for a connector by running a connection check.
    Returns True if valid, raises exception otherwise.
    """
    try:
        # Reconstruct config from flat UI format to original structure
        reconstructed_config = _reconstruct_config(connector_name, config)
        logger.info(f"Validating {connector_name} with config keys: {list(reconstructed_config.keys())}")
        
        source = _get_source_with_retry(connector_name, config=reconstructed_config, install_if_missing=True, docker_image=True, use_host_network=True)
        source.check()
        return True
    except Exception as e:
        logger.error(f"Connection check failed for {connector_name}: {e}")
        raise ValueError(f"Connection check failed: {str(e)}")


def get_available_streams(connector_name: str, config: Dict[str, Any]) -> List[str]:
    """Get list of available streams (tables/endpoints) from a source."""
    try:
        reconstructed_config = _reconstruct_config(connector_name, config)
        source = _get_source_with_retry(connector_name, config=reconstructed_config, install_if_missing=True, docker_image=True, use_host_network=True)
        source.check()
        return list(source.get_available_streams())
    except Exception as e:
        logger.error(f"Failed to get streams for {connector_name}: {e}")
        raise ValueError(f"Could not get streams: {str(e)}")


def extract_data_from_source(
    connector_name: str,
    config: Dict[str, Any],
    streams: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Extract raw data records from an Airbyte source.
    
    Args:
        connector_name: Name of the Airbyte connector (e.g., "source-postgres")
        config: Connector-specific configuration
        streams: Optional list of streams to sync. If None, syncs all.
    
    Returns:
        List of dictionaries containing the extracted records.
    """
    reconstructed_config = _reconstruct_config(connector_name, config)
    source = _get_source_with_retry(
        connector_name,
        config=reconstructed_config,
        install_if_missing=True,
        docker_image=True,
        use_host_network=True,
    )
    source.check()
    
    if streams:
        source.select_streams(streams)
    else:
        source.select_all_streams()

    # Use PyAirbyte 0.37+ force_full_refresh parameter to avoid CDC/Debezium issues
    logger.info(f"Reading data from {connector_name} with force_full_refresh=True")
    result = source.read(force_full_refresh=True)
    
    records = []
    for stream_name, stream_records in result.streams.items():
        for record in stream_records:
            record_dict = dict(record)
            record_dict["_stream"] = stream_name
            records.append(record_dict)
    
    return records


def _sanitize_metadata_value(value: Any) -> Any:
    """Convert non-JSON-serializable values to safe types.

    MySQL (and other connectors) may return ``date``, ``datetime``,
    ``Decimal``, ``bytes`` etc. which the stdlib ``json`` module
    cannot serialize.  This helper converts them to JSON-safe
    primitives so that ``langchain_postgres`` can store them in
    the ``cmetadata`` JSONB column.
    """
    if value is None:
        return value
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (dict, list)):
        return str(value)
    # Fallback – stringify anything unexpected
    return str(value)


def extract_documents(
    connector_name: str,
    config: Dict[str, Any],
    streams: Optional[List[str]] = None,
    content_fields: Optional[List[str]] = None,
) -> List[Document]:
    """
    Extract data from an Airbyte source and convert to LangChain Documents.
    
    Args:
        connector_name: Name of the Airbyte connector
        config: Connector-specific configuration
        streams: Optional list of streams to sync
        content_fields: Optional list of fields to include in document content.
                       If None, all fields are included.
    
    Returns:
        List of LangChain Document objects ready for vectorization.
    """
    logger.info(f"Extracting documents from {connector_name}")
    
    reconstructed_config = _reconstruct_config(connector_name, config)
    source = _get_source_with_retry(
        connector_name,
        config=reconstructed_config,
        install_if_missing=True,
        docker_image=True,
        use_host_network=True,
    )
    source.check()
    
    if streams:
        source.select_streams(streams)
    else:
        source.select_all_streams()

    # Use PyAirbyte 0.37+ force_full_refresh parameter to avoid CDC/Debezium issues
    logger.info(f"Reading data from {connector_name} with force_full_refresh=True")
    result = source.read(force_full_refresh=True)
    
    documents = []
    for stream_name, stream_records in result.streams.items():
        logger.info(f"Processing stream: {stream_name}")
        
        for record in stream_records:
            record_dict = dict(record)
            
            # Build content from specified fields or all fields
            if content_fields:
                content_parts = []
                for field in content_fields:
                    if field in record_dict and record_dict[field]:
                        content_parts.append(f"{field}: {record_dict[field]}")
                content = "\n".join(content_parts)
            else:
                # Prioritize semantic fields (title, content, description, text, name, summary)
                # and exclude metadata-only fields that add noise to embeddings
                PRIORITY_FIELDS = ["title", "name", "subject", "heading"]
                CONTENT_FIELDS = ["content", "text", "body", "description", "summary", "abstract", "message"]
                EXCLUDE_FIELDS = {"_id", "created_at", "updated_at", "source", "tags", "category", "id", "uuid", "_ab_cdc_cursor"}
                
                content_parts = []
                # First: add priority fields (title etc.)
                for field in PRIORITY_FIELDS:
                    if field in record_dict and record_dict[field]:
                        content_parts.append(f"{field}: {record_dict[field]}")
                # Second: add content fields
                for field in CONTENT_FIELDS:
                    if field in record_dict and record_dict[field]:
                        content_parts.append(f"{record_dict[field]}")
                # Third: if no priority/content fields found, fall back to all fields
                if not content_parts:
                    content_parts = [
                        f"{k}: {v}" for k, v in record_dict.items()
                        if v is not None and not k.startswith("_") and k.lower() not in EXCLUDE_FIELDS
                    ]
                content = "\n".join(content_parts)
            
            if not content.strip():
                continue
            
            # Build metadata from record fields
            doc_metadata = {
                "source": f"airbyte:{connector_name}",
                "stream": stream_name,
                "connector_type": connector_name,
            }
            
            # Add record fields to metadata for better display
            for k, v in record_dict.items():
                if v is not None and not k.startswith("_"):
                    doc_metadata[k] = _sanitize_metadata_value(v)
            
            documents.append(Document(
                page_content=content,
                metadata=doc_metadata,
            ))
    
    logger.info(f"Extracted {len(documents)} documents from {connector_name}")
    return documents


async def extract_documents_async(
    connector_name: str,
    config: Dict[str, Any],
    streams: Optional[List[str]] = None,
    content_fields: Optional[List[str]] = None,
) -> List[Document]:
    """Async wrapper for extract_documents."""
    return await asyncio.to_thread(
        extract_documents,
        connector_name,
        config,
        streams,
        content_fields,
    )
