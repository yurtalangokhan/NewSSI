"""API versioning contract loaded from the repository config."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_BASE_PATH = "/api"
DEFAULT_VERSION = "v1"
DEFAULT_SUPPORTED_VERSIONS = (DEFAULT_VERSION,)
DEFAULT_DEPRECATED_VERSIONS: tuple[str, ...] = ()
CONFIG_ENV_VAR = "API_VERSIONING_CONFIG"


@dataclass(frozen=True)
class ApiVersioningConfig:
    """Resolved API versioning settings for one service."""

    base_path: str
    default_version: str
    supported_versions: tuple[str, ...]
    deprecated_versions: tuple[str, ...]

    @property
    def default_prefix(self) -> str:
        """Return the default versioned API path prefix."""
        return self.prefix_for(self.default_version)

    def prefix_for(self, version: str) -> str:
        """Return the API path prefix for a supported version."""
        if version not in self.supported_versions:
            raise ValueError(f"Unsupported API version: {version}")
        return f"{self.base_path}/{version}"


def find_api_versioning_config(start: Path | None = None) -> Path | None:
    """Find the nearest repository-level API versioning config."""
    configured = os.getenv(CONFIG_ENV_VAR)
    if configured:
        return Path(configured)

    current = (start or Path(__file__)).resolve()
    for parent in (current, *current.parents):
        candidate = parent / "configs" / "api-versioning.toml"
        if candidate.exists():
            return candidate
    return None


def load_api_versioning_config(
    service_name: str,
    *,
    config_path: Path | str | None = None,
) -> ApiVersioningConfig:
    """Load API versioning settings for a service."""
    resolved_path = Path(config_path) if config_path is not None else find_api_versioning_config()
    if resolved_path is None or not resolved_path.exists():
        return _validate_config(
            ApiVersioningConfig(
                base_path=DEFAULT_BASE_PATH,
                default_version=DEFAULT_VERSION,
                supported_versions=DEFAULT_SUPPORTED_VERSIONS,
                deprecated_versions=DEFAULT_DEPRECATED_VERSIONS,
            )
        )

    with resolved_path.open("rb") as config_file:
        raw_config = tomllib.load(config_file)

    api_config = _as_mapping(raw_config.get("api"))
    service_config = _as_mapping(_as_mapping(raw_config.get("services")).get(service_name))

    base_path = _normalize_base_path(
        _as_str(service_config.get("base_path"))
        or _as_str(api_config.get("base_path"))
        or DEFAULT_BASE_PATH
    )
    supported_versions = _as_str_tuple(
        service_config.get("supported_versions"),
        default=_as_str_tuple(
            api_config.get("supported_versions"),
            default=DEFAULT_SUPPORTED_VERSIONS,
        ),
    )
    default_version = (
        _as_str(service_config.get("default_version"))
        or _as_str(api_config.get("default_version"))
        or DEFAULT_VERSION
    )
    deprecated_versions = _as_str_tuple(
        service_config.get("deprecated_versions"),
        default=_as_str_tuple(
            api_config.get("deprecated_versions"),
            default=DEFAULT_DEPRECATED_VERSIONS,
        ),
    )

    return _validate_config(
        ApiVersioningConfig(
            base_path=base_path,
            default_version=default_version,
            supported_versions=supported_versions,
            deprecated_versions=deprecated_versions,
        )
    )


def load_api_prefix(
    service_name: str,
    *,
    config_path: Path | str | None = None,
) -> str:
    """Load the default API prefix for a service."""
    return load_api_versioning_config(service_name, config_path=config_path).default_prefix


def _as_mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_str_tuple(value: object, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return default
    values = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    return values or default


def _normalize_base_path(base_path: str) -> str:
    normalized = base_path.strip().strip("/")
    return f"/{normalized}" if normalized else ""


def _validate_config(config: ApiVersioningConfig) -> ApiVersioningConfig:
    if config.default_version not in config.supported_versions:
        raise ValueError("api default_version must be included in supported_versions")
    for version in config.deprecated_versions:
        if version not in config.supported_versions:
            raise ValueError("deprecated_versions must be included in supported_versions")
    return config


API_VERSIONING = load_api_versioning_config("agent-service")
API_PREFIX = API_VERSIONING.default_prefix
USER_SERVICE_API_PREFIX = load_api_prefix("user-service")
