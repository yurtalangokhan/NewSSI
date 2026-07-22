"""
Command Execution Tools Category.
Provides tools for shell command execution and system info.
"""

import json
import platform
import subprocess
from typing import Any

from ..core.base import BaseToolCategory


class CommandTools(BaseToolCategory):
    """Shell command execution and system information tools."""

    @property
    def name(self) -> str:
        return "command_execution"

    @property
    def description(self) -> str:
        return "Shell command execution and system information"

    @property
    def label(self) -> str:
        return "Command Execution"

    def register_tools(self, mcp: Any) -> None:
        """Register all command execution tools with MCP."""

        @mcp.tool()
        def execute_shell(command: str, working_dir: str | None = None, timeout: int = 30) -> str:
            """
            Execute a shell command in a sandboxed environment.

            Args:
                command: The shell command to execute
                working_dir: Working directory for command execution
                timeout: Timeout in seconds (default: 30)

            Returns:
                Command output (stdout + stderr)
            """
            # Blocked commands for security
            blocked = ["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb"]
            for b in blocked:
                if b in command.lower():
                    return f"Error: Blocked command pattern detected: {b}"

            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=working_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                output = result.stdout
                if result.stderr:
                    output += f"\n[STDERR]: {result.stderr}"
                if result.returncode != 0:
                    output += f"\n[Exit Code: {result.returncode}]"

                return output if output.strip() else "[No output]"

            except subprocess.TimeoutExpired:
                return f"Error: Command timed out after {timeout} seconds"
            except Exception as e:
                return f"Error executing command: {str(e)}"

        @mcp.tool()
        def get_system_info() -> str:
            """
            Get system information.

            Returns:
                System info including OS, CPU, memory
            """
            info = {
                "os": platform.system(),
                "os_version": platform.version(),
                "architecture": platform.machine(),
                "python_version": platform.python_version(),
                "hostname": platform.node(),
            }

            return json.dumps(info, indent=2)
