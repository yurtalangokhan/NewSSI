"""Server-defined command registry.

The model selects a command by id and (for now) no free-form arguments at
all. It never supplies a command string: a blocklist over free-form text
is not a security boundary (see spec TS-1 — execute_shell's five-substring
blocklist ["rm -rf /", "mkfs", "dd if=", ":(){", "fork bomb"] was defeated
by "rm  -rf /" with a double space, "rm -rf /*", or any base64-wrapped
command run through sh -c).
"""

from __future__ import annotations

from typing import Any

from error_contract import UnknownCommandError

# Deliberately small and read-only informational commands only. Anything
# that mutates state or accepts caller-supplied arguments belongs behind
# its own, more specific tool with its own validation — not here.
ALLOWED_COMMANDS: dict[str, list[str]] = {
    "python_version": ["python3", "--version"],
    "node_version": ["node", "--version"],
    "git_version": ["git", "--version"],
    "disk_usage": ["df", "-h", "."],
    "list_processes": ["ps", "-o", "pid,etime,comm"],
}


def build_argv(command_id: str, arguments: dict[str, Any] | None = None) -> list[str]:
    """Return the argv for command_id.

    `arguments` is reserved for future parameterised entries and must be
    empty for every command currently in the registry.
    """
    argv = ALLOWED_COMMANDS.get(command_id)
    if argv is None:
        raise UnknownCommandError(f"Command '{command_id}' is not allowed")
    if arguments:
        raise UnknownCommandError(f"Command '{command_id}' does not accept arguments")
    return list(argv)
