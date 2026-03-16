"""
Time and Date Tools Category.
Provides tools for time and date operations.
"""

from datetime import datetime
from typing import Any, Optional

from ..core.base import BaseToolCategory


class TimeTools(BaseToolCategory):
    """Time and date utility tools."""
    
    @property
    def name(self) -> str:
        return "time_date"
    
    @property
    def description(self) -> str:
        return "Time and date utilities"
    
    @property
    def label(self) -> str:
        return "Time & Date"
    
    def register_tools(self, mcp: Any) -> None:
        """Register all time tools with MCP."""
        
        @mcp.tool()
        def get_current_time(timezone: Optional[str] = None) -> str:
            """
            Get the current date and time.
            
            Args:
                timezone: Optional timezone (e.g., 'UTC', 'Europe/Istanbul'). Defaults to local time.
            
            Returns:
                Current date and time as formatted string
            """
            try:
                if timezone:
                    from zoneinfo import ZoneInfo
                    now = datetime.now(ZoneInfo(timezone))
                else:
                    now = datetime.now()
                
                return now.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
            except Exception as e:
                return f"Error: {str(e)}"
