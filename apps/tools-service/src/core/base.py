"""
Base classes for tool categories.
Provides abstract base class that all tool categories must implement.
"""

import json
from abc import ABC, abstractmethod
from typing import Any


class BaseToolCategory(ABC):
    """
    Abstract base class for all tool categories.

    Each tool category should inherit from this class and implement
    the required methods. This ensures consistent behavior across
    all tool categories and enables the plugin system.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Returns the unique name of this tool category.
        Used for registration and identification.
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Returns a human-readable description of this tool category.
        """
        pass

    @property
    @abstractmethod
    def label(self) -> str:
        """
        Returns the display label for this tool category.
        This is shown in the frontend UI as the category title.
        Example: "📁 File Operations", "🧮 Calculator"
        """
        pass

    @abstractmethod
    def register_tools(self, mcp: Any) -> None:
        """
        Register all tools in this category with the MCP server.

        Args:
            mcp: The FastMCP instance to register tools with.
        """
        pass

    async def initialize(self) -> None:
        """
        Called when the tool category is being initialized.
        Override this method to perform any async initialization.
        """
        return None

    async def cleanup(self) -> None:
        """
        Called when the tool category is being cleaned up.
        Override this method to perform any cleanup tasks.
        """
        return None

    @staticmethod
    def success_response(data: dict[str, Any]) -> str:
        """
        Create a standardized success response.

        Args:
            data: The data to include in the response.

        Returns:
            JSON string with success=True and the data.
        """
        return json.dumps({"success": True, **data}, indent=2)

    @staticmethod
    def error_response(error: str) -> str:
        """
        Create a standardized error response.

        Args:
            error: The error message.

        Returns:
            JSON string with success=False and the error.
        """
        return json.dumps({"success": False, "error": error})

    @staticmethod
    def parse_json_param(param: str | None) -> dict[str, Any]:
        """
        Safely parse a JSON string parameter.

        Args:
            param: Optional JSON string to parse.

        Returns:
            Parsed dict or empty dict if param is None/invalid.
        """
        if not param:
            return {}
        try:
            return json.loads(param)
        except json.JSONDecodeError:
            return {}
