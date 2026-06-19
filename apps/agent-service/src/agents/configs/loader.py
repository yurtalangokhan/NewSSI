"""Agent configuration loader - loads JSON/YAML configs."""

import json
from pathlib import Path
from typing import Any

from core.logger import get_logger

logger = get_logger(__name__)


def get_config_dir() -> Path:
    """Get the agent configs directory."""
    # Get path relative to agents module
    config_dir = Path(__file__).parent.parent / "configs"
    return config_dir


def load_agent_config(name: str) -> dict[str, Any] | None:
    """
    Load a single agent config by name.

    Args:
        name: Config name (without extension)

    Returns:
        Config dictionary or None if not found
    """
    config_dir = get_config_dir()

    # Try different extensions
    for ext in [".json", ".yaml", ".yml"]:
        config_path = config_dir / f"{name}{ext}"
        if config_path.exists():
            with open(config_path) as f:
                if ext in [".yaml", ".yml"]:
                    import yaml

                    return yaml.safe_load(f)
                return json.load(f)

    return None


def load_agent_configs() -> list[dict[str, Any]]:
    """
    Load all agent configs from the configs directory.

    Returns:
        List of agent config dictionaries
    """
    config_dir = get_config_dir()
    configs = []

    if not config_dir.exists():
        return configs

    for config_path in config_dir.glob("*.json"):
        try:
            with open(config_path) as f:
                config = json.load(f)
                if config.get("enabled", True):
                    configs.append(config)
        except Exception as e:
            logger.error("Error loading config %s: %s", config_path, e)

    for config_path in config_dir.glob("*.yaml"):
        try:
            import yaml

            with open(config_path) as f:
                config = yaml.safe_load(f)
                if config and config.get("enabled", True):
                    configs.append(config)
        except Exception as e:
            logger.error("Error loading config %s: %s", config_path, e)

    return configs


def save_agent_config(name: str, config: dict[str, Any]) -> None:
    """
    Save an agent config.

    Args:
        name: Config name (without extension)
        config: Config dictionary
    """
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / f"{name}.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def delete_agent_config(name: str) -> bool:
    """
    Delete an agent config.

    Args:
        name: Config name

    Returns:
        True if deleted, False if not found
    """
    config_dir = get_config_dir()

    for ext in [".json", ".yaml", ".yml"]:
        config_path = config_dir / f"{name}{ext}"
        if config_path.exists():
            config_path.unlink()
            return True

    return False


def list_config_names() -> list[str]:
    """List all available config names."""
    config_dir = get_config_dir()
    names = []

    if not config_dir.exists():
        return names

    for config_path in config_dir.glob("*.json"):
        names.append(config_path.stem)

    for config_path in config_dir.glob("*.yaml"):
        if config_path.stem not in names:
            names.append(config_path.stem)

    for config_path in config_dir.glob("*.yml"):
        if config_path.stem not in names:
            names.append(config_path.stem)

    return names
