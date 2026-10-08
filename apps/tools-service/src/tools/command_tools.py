"""
Command Execution Tools Category.
Provides tools for running server-defined commands and reading system info.

execute_shell was removed entirely: shell=True with a five-substring
blocklist (["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb"]) is not a
security boundary — "rm  -rf /" (double space), "rm -rf /*", or any
base64-wrapped command run through `sh -c` all defeated it trivially. The
model now selects a command by id from a server-defined registry
(core.commands.ALLOWED_COMMANDS); it never supplies a command string. See
spec TS-1.
"""

import json
import platform
from typing import Any, Literal

from localization import t

from ..core.base import BaseToolCategory
from ..core.commands import ALLOWED_COMMANDS, UnknownCommandError, build_argv
from ..core.sandbox import run_sandboxed
from ..core.schema import BoundedTimeout
from ..core.workspace import workspace_root
from .response import tool_error_message

CommandId = Literal["python_version", "node_version", "git_version", "disk_usage", "list_processes"]


class CommandTools(BaseToolCategory):
    """Registry-backed command execution and system information tools."""

    @property
    def name(self) -> str:
        return "command_execution"

    @property
    def description(self) -> str:
        return t(
            "categories.command_execution.description",
            default="Run a fixed set of server-defined, read-only commands and get system info",
        )

    @property
    def label(self) -> str:
        return t("categories.command_execution.label", default="Command Execution")

    def register_tools(self, mcp: Any) -> None:
        """Register all command execution tools with MCP."""

        @mcp.tool()
        async def run_command(command_id: CommandId, timeout: BoundedTimeout = 30) -> str:  # noqa: ASYNC109 - timeout is part of the MCP tool schema
            """
            Run one of the allowed, server-defined commands.

            Free-form shell commands are not supported. Call list_commands
            to see which command_id values exist.

            Args:
                command_id: One of the registered command identifiers
                timeout: Timeout in seconds (default: 30, capped server-side)

            Returns:
                Command output (stdout + stderr)
            """
            try:
                try:
                    argv = build_argv(command_id)
                except UnknownCommandError as e:
                    return t("command.not_allowed", command=command_id, default=str(e))

                result = await run_sandboxed(argv, cwd=workspace_root(), execution_timeout=timeout)

                if result.timed_out:
                    return t("command.timeout", seconds=timeout)
                output = result.stdout
                if result.stderr:
                    output += f"\n[STDERR]: {result.stderr}"
                if result.exit_code != 0:
                    output += f"\n[Exit Code: {result.exit_code}]"
                return output if output.strip() else "[No output]"
            except (OSError, ValueError) as e:
                return t("command.execution_error", error=tool_error_message(e))

        @mcp.tool()
        def list_commands() -> str:
            """List the command_id values run_command accepts."""
            return json.dumps(sorted(ALLOWED_COMMANDS), indent=2)

        @mcp.tool()
        def get_system_info() -> str:
            """
            Get system information.

            Returns:
                Architecture and runtime version info. Hostname and OS
                version are internal infrastructure details and are not
                included.
            """
            info = {
                "os": platform.system(),
                "architecture": platform.machine(),
                "python_version": platform.python_version(),
            }

            return json.dumps(info, indent=2)
