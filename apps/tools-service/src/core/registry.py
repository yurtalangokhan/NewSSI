"""
Tool Registry for plugin-based tool management.
Automatically discovers and registers tool categories.
"""

import importlib
import importlib.util
from pathlib import Path
from typing import Any

from i18n import t

from .base import BaseToolCategory


def _safe_t(key: str, default: str | None = None) -> str | None:
    val = t(key)
    if not val or val == key or val.startswith("tools.") or val.startswith("categories."):
        return default
    return val


class ToolRegistry:
    """
    Central registry for managing tool categories.

    Provides plugin discovery, registration, and lifecycle management
    for all tool categories. Supports dynamic enabling/disabling of
    categories and automatic tool registration with FastMCP.
    """

    def __init__(self, mcp: Any):
        """
        Initialize the registry with a FastMCP instance.

        Args:
            mcp: The FastMCP instance to register tools with.
        """
        self.mcp = mcp
        self._categories: dict[str, BaseToolCategory] = {}
        self._enabled: dict[str, bool] = {}
        self._setup_i18n_wrapper()

    def _setup_i18n_wrapper(self) -> None:
        """Wrap FastMCP.list_tools to dynamically translate tool metadata per request."""
        if getattr(self.mcp, "_i18n_wrapped", False):
            return

        orig_list_tools = self.mcp.list_tools

        async def list_tools_i18n(*args: Any, **kwargs: Any) -> Any:
            tools = await orig_list_tools(*args, **kwargs)
            translated_tools = []
            for tool in tools:
                cat_name = getattr(tool, "_category_name", None)
                orig_desc = getattr(tool, "_original_doc", None)
                orig_name = getattr(tool, "_original_name", tool.name)

                desc_str = tool.description or ""
                if not cat_name and "[category:" in desc_str:
                    try:
                        c_start = desc_str.find("[category:") + len("[category:")
                        c_end = desc_str.find("]", c_start)
                        if c_end > c_start:
                            cat_name = desc_str[c_start:c_end]
                    except Exception:
                        pass

                if orig_desc is None:
                    base_desc = desc_str
                    if "[category:" in base_desc:
                        base_desc = (
                            base_desc.split("[category:")[0].split("[category_label:")[0].strip()
                        )
                    orig_desc = base_desc

                cat_label = (
                    _safe_t(f"categories.{cat_name}.label", cat_name or "") if cat_name else ""
                )

                trans_desc = None
                if cat_name:
                    trans_desc = _safe_t(f"tools.{cat_name}.{orig_name}.description")
                if trans_desc is None:
                    trans_desc = _safe_t(f"tools.{orig_name}.description", orig_desc)

                if trans_desc and "[category:" in trans_desc:
                    trans_desc = trans_desc.split("[category:")[0].strip()

                trans_title = None
                if cat_name:
                    trans_title = _safe_t(f"tools.{cat_name}.{orig_name}.name")
                if trans_title is None:
                    trans_title = _safe_t(
                        f"tools.{orig_name}.name", orig_name.replace("_", " ").title()
                    )

                category_tag = f"[category:{cat_name}]" if cat_name else ""
                label_tag = f"[category_label:{cat_label}]" if cat_label else ""
                title_tag = f"[title:{trans_title}]" if trans_title else ""
                full_desc = f"{category_tag}{label_tag}{title_tag} {trans_desc or ''}".strip()

                tool.name = orig_name
                tool.description = full_desc
                translated_tools.append(tool)

            return translated_tools

        self.mcp.list_tools = list_tools_i18n
        self.mcp._i18n_wrapped = True

    def register_category(self, category: BaseToolCategory) -> None:
        """
        Register a tool category with the registry.

        Args:
            category: The tool category instance to register.
        """
        name = category.name
        if name in self._categories:
            raise ValueError(f"Category '{name}' is already registered")

        self._categories[name] = category
        self._enabled[name] = True

        # Wrap the MCP instance to inject category tags into tool descriptions
        wrapped_mcp = _CategoryTaggedMCP(self.mcp, name, category.description, category.label)

        # Register tools with the wrapped MCP (adds category metadata)
        category.register_tools(wrapped_mcp)
        print(f"  ✓ Registered category: {name} ({category.label}) - {category.description}")

    def discover_plugins(self, plugins_dir: str) -> int:
        """
        Automatically discover and register tool categories from a directory.

        Scans the specified directory for Python files that contain
        classes inheriting from BaseToolCategory.

        Args:
            plugins_dir: Path to the directory containing tool modules.

        Returns:
            Number of categories registered.
        """
        plugins_path = Path(plugins_dir)
        if not plugins_path.exists():
            print(f"Warning: Plugins directory does not exist: {plugins_dir}")
            return 0

        registered = 0
        print(f"Discovering plugins in: {plugins_dir}")

        for file_path in plugins_path.glob("*_tools.py"):
            try:
                category = self._load_category_from_file(file_path)
                if category:
                    self.register_category(category)
                    registered += 1
            except Exception as e:
                print(f"  ✗ Failed to load {file_path.name}: {e}")

        print(f"Registered {registered} tool categories")
        return registered

    def _load_category_from_file(self, file_path: Path) -> BaseToolCategory | None:
        """
        Load a tool category from a Python file.

        Args:
            file_path: Path to the Python file.

        Returns:
            Instance of the tool category, or None if not found.
        """
        module_name = file_path.stem

        # Use proper package import to handle relative imports
        # The module should be imported as src.tools.<module_name>
        try:
            full_module_name = f"src.tools.{module_name}"
            module = importlib.import_module(full_module_name)
        except ImportError:
            # Fallback: try loading from file location
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

        # Find classes that inherit from BaseToolCategory
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseToolCategory)
                and attr is not BaseToolCategory
            ):
                # Instantiate and return the category
                return attr()

        return None

    def enable_category(self, name: str) -> bool:
        """
        Enable a registered tool category.

        Args:
            name: The name of the category to enable.

        Returns:
            True if category was enabled, False if not found.
        """
        if name in self._enabled:
            self._enabled[name] = True
            return True
        return False

    def disable_category(self, name: str) -> bool:
        """
        Disable a registered tool category.

        Note: This only marks the category as disabled; tools already
        registered with MCP will remain active.

        Args:
            name: The name of the category to disable.

        Returns:
            True if category was disabled, False if not found.
        """
        if name in self._enabled:
            self._enabled[name] = False
            return True
        return False

    def get_category(self, name: str) -> BaseToolCategory | None:
        """
        Get a registered category by name.

        Args:
            name: The name of the category.

        Returns:
            The category instance, or None if not found.
        """
        return self._categories.get(name)

    def list_categories(self) -> list[dict[str, Any]]:
        """
        List all registered categories with their status.

        Returns:
            List of category info dicts with name, description, enabled status.
        """
        return [
            {
                "name": name,
                "description": cat.translated_description,
                "label": cat.translated_label,
                "enabled": self._enabled.get(name, False),
            }
            for name, cat in self._categories.items()
        ]

    async def initialize_all(self) -> None:
        """Initialize all registered categories."""
        for name, category in self._categories.items():
            if self._enabled.get(name, False):
                try:
                    await category.initialize()
                except Exception as e:
                    print(f"Failed to initialize category '{name}': {e}")

    async def cleanup_all(self) -> None:
        """Cleanup all registered categories."""
        for name, category in self._categories.items():
            try:
                await category.cleanup()
            except Exception as e:
                print(f"Failed to cleanup category '{name}': {e}")


class _CategoryTaggedMCP:
    """
    A wrapper around FastMCP that injects category metadata tags
    into tool descriptions during registration.

    This allows the frontend to parse the [category:name] and
    [category_label:label] tags from tool descriptions and group
    tools by category with proper display labels.
    """

    def __init__(
        self, mcp: Any, category_name: str, category_description: str, category_label: str
    ):
        self._mcp = mcp
        self._category_name = category_name
        self._category_description = category_description
        self._category_label = category_label

    def tool(self, *args, **kwargs):
        """
        Wrap the @mcp.tool() decorator to inject category tag
        into the tool's docstring/description.
        """
        original_decorator = self._mcp.tool(*args, **kwargs)
        category_tag = f"[category:{self._category_name}]"
        label_tag = f"[category_label:{self._category_label}]"

        def wrapper(func):
            original_doc = func.__doc__ or ""
            original_name = getattr(func, "__name__", "tool")
            func.__doc__ = f"{category_tag}{label_tag} {original_doc}"
            res_tool = original_decorator(func)

            target = res_tool if res_tool is not None else func
            target._category_name = self._category_name
            target._original_name = original_name
            target._original_doc = original_doc
            return res_tool

        return wrapper

    def __getattr__(self, name):
        """Proxy all other attributes to the original MCP instance."""
        return getattr(self._mcp, name)
