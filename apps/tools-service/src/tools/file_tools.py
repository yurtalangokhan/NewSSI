"""
File Operation Tools Category.
Provides tools for reading, writing, and listing files.

Every tool in this module accepts a path relative to the workspace and
resolves it through ``resolve_in_workspace`` before touching the
filesystem — see spec TS-2. Before this fix, WORKSPACE_DIR was never even
imported here: every tool used a bare ``open()``/``Path()`` on whatever
string the model supplied, so ``file_read("/proc/self/environ")`` or
``file_write("/app/server.py", ...)`` worked exactly as asked.
"""

from itertools import islice
import shutil
from typing import Any

from localization import t

from ..core.base import BaseToolCategory
from ..core.observability import get_logger
from ..core.schema import BoundedLimit, GlobPattern, LongText
from ..core.workspace import (
    WorkspacePath,
    guard_workspace_escape,
    resolve_in_workspace,
    workspace_root,
)
from .response import tool_error_message

logger = get_logger(__name__)


def _safe_error(exc: Exception) -> str:
    """The exception's kind, never its text.

    ``str(exc)`` on an OSError carries the absolute path it failed on, and on
    a parser error the document's internals. The model gets the classification
    it can act on; the detail goes to the log.
    """
    logger.warning("%s failed: %s", type(exc).__name__, exc, exc_info=True)
    return tool_error_message(exc)


# Byte and item caps. Spec TS-11: file_read previously called
# f.readlines()[:max_lines], which materialises the entire file in memory
# before the slice is applied; file_list materialised the whole glob result
# before truncating to 100 items.
MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 5_000_000
MAX_LIST_ITEMS = 100


def normalize_content(content: str) -> str:
    """
    Normalize content string by converting escaped newline/tab sequences to
    their real characters **only outside** of string literals.

    When the LLM sends ``print("\\nHello")``, the ``\\n`` inside the quotes
    must stay as the two-character escape ``\\n`` so that the resulting file
    contains valid Python (or other language) code.  Meanwhile the ``\\n``
    that separates *lines of the file* must become a real newline.

    Strategy
    --------
    Walk through the string character by character, track whether we are
    inside a string literal (single-quoted, double-quoted, or their triple
    variants), and only convert ``\\n`` / ``\\t`` / ``\\r`` when we are
    *outside* any string literal.
    """

    result: list[str] = []
    i = 0
    length = len(content)

    in_string: str | None = None  # None | "'" | '"' | "'''" | '"""'

    while i < length:
        # ----- check for string-literal boundaries -----
        if in_string is None:
            # Try triple-quote first (''' or """)
            triple = content[i : i + 3]
            if triple in ("'''", '"""'):
                in_string = triple
                result.append(triple)
                i += 3
                continue
            # Single / double quote
            if content[i] in ("'", '"'):
                in_string = content[i]
                result.append(content[i])
                i += 1
                continue
        else:
            # Are we closing the current string?
            if in_string in ("'''", '"""'):
                if content[i : i + 3] == in_string:
                    result.append(in_string)
                    i += 3
                    in_string = None
                    continue
            else:
                # Skip escaped characters inside string (e.g. \' or \")
                if content[i] == "\\" and i + 1 < length:
                    result.append(content[i : i + 2])
                    i += 2
                    continue
                if content[i] == in_string:
                    result.append(content[i])
                    i += 1
                    in_string = None
                    continue

        # ----- outside string: convert escape sequences -----
        if in_string is None and content[i] == "\\" and i + 1 < length:
            nxt = content[i + 1]
            if nxt == "n":
                result.append("\n")
                i += 2
                continue
            elif nxt == "t":
                result.append("\t")
                i += 2
                continue
            elif nxt == "r":
                result.append("\r")
                i += 2
                continue
            elif nxt == '"':
                result.append('"')
                i += 2
                continue
            elif nxt == "'":
                result.append("'")
                i += 2
                continue
            elif nxt == "\\":
                result.append("\\")
                i += 2
                continue

        # ----- default: copy character as-is -----
        result.append(content[i])
        i += 1

    return "".join(result)


class FileTools(BaseToolCategory):
    """File system operation tools."""

    @property
    def name(self) -> str:
        return "file_operations"

    @property
    def description(self) -> str:
        return t(
            "categories.file_operations.description",
            default="File read, write, and directory listing",
        )

    @property
    def label(self) -> str:
        return t("categories.file_operations.label", default="📁 File Operations")

    def register_tools(self, mcp: Any) -> None:
        """Register all file operation tools with MCP."""

        @mcp.tool()
        @guard_workspace_escape
        def file_read(file_path: WorkspacePath, max_lines: BoundedLimit = 1000) -> str:
            """
            Read content from a file inside the workspace.

            Args:
                file_path: Path to the file, relative to the workspace
                max_lines: Maximum lines to read (default: 1000)

            Returns:
                File content
            """
            path = resolve_in_workspace(file_path, root=workspace_root())
            try:
                chunks: list[str] = []
                bytes_read = 0
                truncated = False
                lines_read = 0
                with open(path, encoding="utf-8") as f:
                    # Iterate line by line rather than f.readlines()[:max_lines]:
                    # the previous version materialised the entire file in
                    # memory before applying the slice.
                    for line in f:
                        if lines_read >= max_lines:
                            truncated = True
                            break
                        encoded_len = len(line.encode("utf-8"))
                        if bytes_read + encoded_len > MAX_READ_BYTES:
                            truncated = True
                            break
                        chunks.append(line)
                        bytes_read += encoded_len
                        lines_read += 1
                content = "".join(chunks)
                if truncated:
                    content += f"\n... [truncated at {lines_read} lines / {MAX_READ_BYTES} bytes]"
                return content
            except (OSError, UnicodeError, ValueError) as e:
                return t("file.read_error", error=_safe_error(e))

        @mcp.tool()
        @guard_workspace_escape
        def file_write(file_path: WorkspacePath, content: LongText, append: bool = False) -> str:
            """
            Write content to a file inside the workspace.
            Use \\n for newlines when writing multi-line content.

            Args:
                file_path: Path to the file, relative to the workspace
                content: Content to write (use \\n for newlines)
                append: Append to file instead of overwrite (default: False)

            Returns:
                Success or error message
            """
            path = resolve_in_workspace(file_path, root=workspace_root())
            content = normalize_content(content)
            if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
                return t(
                    "file.write_error",
                    error=f"content exceeds the {MAX_WRITE_BYTES} byte limit",
                )
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                mode = "a" if append else "w"
                with open(path, mode, encoding="utf-8") as f:
                    f.write(content)
                return f"Successfully wrote to {file_path}"
            except (OSError, UnicodeError, ValueError) as e:
                return t("file.write_error", error=_safe_error(e))

        @mcp.tool()
        @guard_workspace_escape
        def file_list(directory: WorkspacePath = ".", pattern: GlobPattern | None = None) -> str:
            """
            List files in a directory inside the workspace.

            Args:
                directory: Directory path, relative to the workspace
                pattern: Optional glob pattern (e.g., "*.py")

            Returns:
                List of files
            """
            path = resolve_in_workspace(directory, root=workspace_root())
            try:
                if not path.exists():
                    return t("file.directory_not_found", directory=directory)
                if not path.is_dir():
                    return t("file.directory_not_found", directory=directory)

                iterator = path.glob(pattern) if pattern else path.iterdir()

                result = []
                shown = 0
                # islice rather than list(...)[:100]: the previous version
                # materialised the entire glob/iterdir result before slicing.
                for entry in islice(iterator, MAX_LIST_ITEMS):
                    if entry.is_symlink():
                        # A symlink inside the workspace can point anywhere;
                        # listing it as if it were a plain file would surface
                        # its target's metadata without a boundary check.
                        continue
                    file_type = "DIR" if entry.is_dir() else "FILE"
                    size = entry.stat().st_size if entry.is_file() else "-"
                    result.append(f"{file_type}\t{size}\t{entry.name}")
                    shown += 1

                if next(iterator, None) is not None:
                    result.append(f"... and more items (showing first {MAX_LIST_ITEMS})")

                return "\n".join(result) if result else "Empty directory"
            except (OSError, UnicodeError, ValueError) as e:
                return t("file.list_error", error=_safe_error(e))

        @mcp.tool()
        @guard_workspace_escape
        def create_directory(dir_path: WorkspacePath, parents: bool = True) -> str:
            """
            Create a directory inside the workspace (and parent directories if needed).

            Args:
                dir_path: Path to the directory to create, relative to the workspace
                parents: Create parent directories if they don't exist (default: True)

            Returns:
                Success or error message
            """
            path = resolve_in_workspace(dir_path, root=workspace_root())
            try:
                if path.exists():
                    return t("file.directory_exists", dir_path=dir_path)

                path.mkdir(parents=parents, exist_ok=True)
                return f"Successfully created directory: {dir_path}"
            except (OSError, UnicodeError, ValueError) as e:
                return t("file.create_directory_error", error=_safe_error(e))

        @mcp.tool()
        @guard_workspace_escape
        def file_exists(file_path: WorkspacePath) -> str:
            """
            Check if a file or directory exists inside the workspace.

            Args:
                file_path: Path to check, relative to the workspace

            Returns:
                Existence status and type (file/directory)
            """
            path = resolve_in_workspace(file_path, root=workspace_root())
            try:
                if not path.exists():
                    return t("file.path_not_found", file_path=file_path)

                if path.is_file():
                    size = path.stat().st_size
                    return f"FILE exists: {file_path} ({size} bytes)"
                elif path.is_dir():
                    items = sum(1 for _ in islice(path.iterdir(), MAX_LIST_ITEMS))
                    return f"DIRECTORY exists: {file_path} ({items} items)"
                else:
                    return f"EXISTS (special): {file_path}"
            except (OSError, UnicodeError, ValueError) as e:
                return t("file.check_error", error=_safe_error(e))

        @mcp.tool()
        @guard_workspace_escape
        def file_update(file_path: WorkspacePath, old_text: LongText, new_text: LongText) -> str:
            """
            Update an existing file inside the workspace by replacing a specific
            text block with new content.
            Use \\n for newlines in both old_text and new_text.

            This tool finds the exact occurrence of old_text in the file and replaces it
            with new_text. Useful for fixing bugs, updating functions, or modifying
            specific sections of code.

            Args:
                file_path: Path to the file to update, relative to the workspace
                old_text: The exact text to find and replace (use \\n for newlines)
                new_text: The replacement text (use \\n for newlines)

            Returns:
                Success message with details or error message

            Example:
                file_update(
                    file_path="myproject/main.py",
                    old_text="def add(a, b):\\n    return a + b",
                    new_text="def add(a, b):\\n    \"\"\"Add two numbers.\"\"\"\\n    return a + b"
                )
            """
            path = resolve_in_workspace(file_path, root=workspace_root())
            try:
                if not path.exists():
                    return t("file.file_not_found", file_path=file_path)
                if not path.is_file():
                    return t("file.not_a_file", file_path=file_path)

                # Normalize escaped characters
                old_text = normalize_content(old_text)
                new_text = normalize_content(new_text)

                # Read current content
                with open(path, encoding="utf-8") as f:
                    content = f.read()

                # Check if old_text exists
                count = content.count(old_text)
                if count == 0:
                    # Provide helpful context
                    lines = content.split("\n")
                    preview = "\n".join(lines[:20])
                    return t(
                        "file.text_not_found",
                        file_path=file_path,
                        line_count=len(lines),
                        preview=preview,
                    )

                if count > 1:
                    return t("file.multiple_occurrences", count=count)

                # Replace
                new_content = content.replace(old_text, new_text, 1)

                # Write back
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                # Calculate change stats
                old_lines = old_text.count("\n") + 1
                new_lines = new_text.count("\n") + 1

                return (
                    f"✓ Successfully updated {file_path}\n"
                    f"  Replaced {old_lines} lines with {new_lines} lines\n"
                    f"  Occurrences replaced: 1"
                )

            except (OSError, UnicodeError, ValueError) as e:
                return t("file.update_error", error=_safe_error(e))

        @mcp.tool()
        @guard_workspace_escape
        def file_delete(file_path: WorkspacePath, recursive: bool = False) -> str:
            """
            Delete a file or directory inside the workspace.

            Args:
                file_path: Path to delete, relative to the workspace
                recursive: Delete directories recursively (default: False for safety)

            Returns:
                Success or error message
            """
            root = workspace_root().resolve()
            path = resolve_in_workspace(file_path, root=root)
            if path == root:
                # resolve_in_workspace allows the root itself (it is a valid
                # read/list target); deleting it would destroy every other
                # principal's data sharing the same workspace mount.
                return t(
                    "file.delete_error",
                    error="refusing to delete the workspace root",
                )
            try:
                if not path.exists():
                    return t("file.delete_path_not_found", file_path=file_path)

                if path.is_file() or path.is_symlink():
                    path.unlink()
                    return f"Successfully deleted file: {file_path}"
                elif path.is_dir():
                    if recursive:
                        shutil.rmtree(path)
                        return f"Successfully deleted directory recursively: {file_path}"
                    else:
                        # Only delete if empty
                        if any(path.iterdir()):
                            return t("file.directory_not_empty", file_path=file_path)
                        path.rmdir()
                        return f"Successfully deleted empty directory: {file_path}"

                return t("file.cannot_delete", file_path=file_path)
            except (OSError, UnicodeError, ValueError) as e:
                return t("file.delete_error", error=_safe_error(e))
