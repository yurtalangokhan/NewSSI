"""
Service Management Tools Category.
Provides tools for service/container restart operations.
"""

import subprocess
from typing import Any

from ..core.base import BaseToolCategory


class ServiceTools(BaseToolCategory):
    """Service management tools."""

    @property
    def name(self) -> str:
        return "service_management"

    @property
    def description(self) -> str:
        return "Docker and systemd service restart operations"

    @property
    def label(self) -> str:
        return "Service Management"

    def register_tools(self, mcp: Any) -> None:
        """Register all service management tools with MCP."""

        @mcp.tool()
        def service_restart(service_name: str, use_docker: bool = True) -> str:
            """
            Restart a service (Docker container or systemd service).

            Args:
                service_name: Name of the service/container
                use_docker: Use Docker restart (default: True)

            Returns:
                Restart result
            """
            try:
                if use_docker:
                    result = subprocess.run(
                        f"docker restart {service_name}",
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                else:
                    result = subprocess.run(
                        f"systemctl restart {service_name}",
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )

                if result.returncode == 0:
                    return f"Service {service_name} restarted successfully"
                return result.stderr
            except Exception as e:
                return f"Service restart error: {str(e)}"
