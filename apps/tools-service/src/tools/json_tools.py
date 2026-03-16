"""
JSON/Data Tools Category.
Provides tools for JSON formatting and querying.
"""

import json
from typing import Any

from ..core.base import BaseToolCategory


class JsonTools(BaseToolCategory):
    """JSON formatting and querying tools."""
    
    @property
    def name(self) -> str:
        return "json_data"
    
    @property
    def description(self) -> str:
        return "JSON formatting, validation, and querying"
    
    @property
    def label(self) -> str:
        return "JSON Data"
    
    def register_tools(self, mcp: Any) -> None:
        """Register all JSON tools with MCP."""
        
        @mcp.tool()
        def json_format(data: str, indent: int = 2) -> str:
            """
            Format and validate JSON data.
            
            Args:
                data: JSON string to format
                indent: Indentation level (default: 2)
            
            Returns:
                Formatted JSON or error message
            """
            try:
                parsed = json.loads(data)
                return json.dumps(parsed, indent=indent, ensure_ascii=False)
            except json.JSONDecodeError as e:
                return f"Invalid JSON: {str(e)}"
        
        @mcp.tool()
        def json_query(data: str, path: str) -> str:
            """
            Query JSON data using dot notation.
            
            Args:
                data: JSON string
                path: Dot-notation path (e.g., "users.0.name" or "config.settings")
            
            Returns:
                Value at the specified path
            """
            try:
                parsed = json.loads(data)
                
                for key in path.split("."):
                    if isinstance(parsed, list):
                        parsed = parsed[int(key)]
                    elif isinstance(parsed, dict):
                        parsed = parsed[key]
                    else:
                        return f"Cannot navigate further at '{key}'"
                
                if isinstance(parsed, (dict, list)):
                    return json.dumps(parsed, indent=2, ensure_ascii=False)
                return str(parsed)
                
            except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
                return f"Query error: {str(e)}"
