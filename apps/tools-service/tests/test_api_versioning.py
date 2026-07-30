from pathlib import Path

import pytest


def test_api_versioning_defaults_to_v1_when_config_is_missing(tmp_path: Path) -> None:
    from src.core.api_versioning import load_api_versioning_config

    config = load_api_versioning_config("tools-service", config_path=tmp_path / "missing.toml")

    assert config.base_path == "/api"
    assert config.default_version == "v1"
    assert config.supported_versions == ("v1",)
    assert config.deprecated_versions == ()
    assert config.default_prefix == "/api/v1"
    assert config.prefix_for("v1") == "/api/v1"


def test_api_versioning_reads_service_override(tmp_path: Path) -> None:
    from src.core.api_versioning import load_api_versioning_config

    config_path = tmp_path / "api-versioning.toml"
    config_path.write_text(
        """
[api]
base_path = "api/"
default_version = "v1"
supported_versions = ["v1"]

[services.tools-service]
default_version = "v2"
supported_versions = ["v1", "v2"]
deprecated_versions = ["v1"]
""",
        encoding="utf-8",
    )

    config = load_api_versioning_config("tools-service", config_path=config_path)

    assert config.default_prefix == "/api/v2"
    assert config.supported_versions == ("v1", "v2")
    assert config.deprecated_versions == ("v1",)


def test_api_versioning_rejects_default_version_outside_supported_versions(
    tmp_path: Path,
) -> None:
    from src.core.api_versioning import load_api_versioning_config

    config_path = tmp_path / "api-versioning.toml"
    config_path.write_text(
        """
[api]
default_version = "v2"
supported_versions = ["v1"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="default_version"):
        load_api_versioning_config("tools-service", config_path=config_path)


def test_user_service_api_prefix_can_differ_from_local_service(tmp_path: Path) -> None:
    from src.core.api_versioning import load_api_prefix

    config_path = tmp_path / "api-versioning.toml"
    config_path.write_text(
        """
[api]
default_version = "v1"
supported_versions = ["v1"]

[services.tools-service]
default_version = "v2"
supported_versions = ["v1", "v2"]

[services.user-service]
default_version = "v1"
supported_versions = ["v1"]
""",
        encoding="utf-8",
    )

    assert load_api_prefix("user-service", config_path=config_path) == "/api/v1"
