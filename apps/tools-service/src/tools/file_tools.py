"""
File Operation Tools Category.
Provides tools for reading, writing, and listing files.
"""

from pathlib import Path
from typing import Any

from ..core.base import BaseToolCategory


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
        return "File read, write, and directory listing"

    @property
    def label(self) -> str:
        return "File Operations"

    def register_tools(self, mcp: Any) -> None:
        """Register all file operation tools with MCP."""

        @mcp.tool()
        def file_read(file_path: str, max_lines: int = 1000) -> str:
            """
            Read content from a file.

            Args:
                file_path: Path to the file
                max_lines: Maximum lines to read (default: 1000)

            Returns:
                File content
            """
            try:
                with open(file_path, encoding="utf-8") as f:
                    lines = f.readlines()[:max_lines]
                    content = "".join(lines)
                    if len(lines) == max_lines:
                        content += f"\n... [truncated at {max_lines} lines]"
                    return content
            except Exception as e:
                return f"Error reading file: {str(e)}"

        @mcp.tool()
        def file_write(file_path: str, content: str, append: bool = False) -> str:
            """
            Write content to a file.
            Use \\n for newlines when writing multi-line content.

            Args:
                file_path: Path to the file
                content: Content to write (use \\n for newlines)
                append: Append to file instead of overwrite (default: False)

            Returns:
                Success or error message
            """
            try:
                # Normalize escaped characters from UI input
                content = normalize_content(content)

                mode = "a" if append else "w"
                with open(file_path, mode, encoding="utf-8") as f:
                    f.write(content)
                return f"Successfully wrote to {file_path}"
            except Exception as e:
                return f"Error writing file: {str(e)}"

        @mcp.tool()
        def file_list(directory: str, pattern: str | None = None) -> str:
            """
            List files in a directory.

            Args:
                directory: Directory path
                pattern: Optional glob pattern (e.g., "*.py")

            Returns:
                List of files
            """
            try:
                path = Path(directory)
                if not path.exists():
                    return f"Directory not found: {directory}"

                files = list(path.glob(pattern)) if pattern else list(path.iterdir())

                result = []
                for f in files[:100]:  # Limit to 100 items
                    file_type = "DIR" if f.is_dir() else "FILE"
                    size = f.stat().st_size if f.is_file() else "-"
                    result.append(f"{file_type}\t{size}\t{f.name}")

                if len(files) > 100:
                    result.append(f"... and {len(files) - 100} more items")

                return "\n".join(result) if result else "Empty directory"
            except Exception as e:
                return f"Error listing directory: {str(e)}"

        @mcp.tool()
        def create_directory(dir_path: str, parents: bool = True) -> str:
            """
            Create a directory (and parent directories if needed).

            Args:
                dir_path: Path to the directory to create
                parents: Create parent directories if they don't exist (default: True)

            Returns:
                Success or error message
            """
            try:
                path = Path(dir_path)
                if path.exists():
                    return f"Directory already exists: {dir_path}"

                path.mkdir(parents=parents, exist_ok=True)
                return f"Successfully created directory: {dir_path}"
            except Exception as e:
                return f"Error creating directory: {str(e)}"

        @mcp.tool()
        def file_exists(file_path: str) -> str:
            """
            Check if a file or directory exists.

            Args:
                file_path: Path to check

            Returns:
                Existence status and type (file/directory)
            """
            try:
                path = Path(file_path)
                if not path.exists():
                    return f"Does not exist: {file_path}"

                if path.is_file():
                    size = path.stat().st_size
                    return f"FILE exists: {file_path} ({size} bytes)"
                elif path.is_dir():
                    items = len(list(path.iterdir()))
                    return f"DIRECTORY exists: {file_path} ({items} items)"
                else:
                    return f"EXISTS (special): {file_path}"
            except Exception as e:
                return f"Error checking path: {str(e)}"

        @mcp.tool()
        def file_update(file_path: str, old_text: str, new_text: str) -> str:
            """
            Update an existing file by replacing a specific text block with new content.
            Use \\n for newlines in both old_text and new_text.

            This tool finds the exact occurrence of old_text in the file and replaces it
            with new_text. Useful for fixing bugs, updating functions, or modifying
            specific sections of code.

            Args:
                file_path: Path to the file to update
                old_text: The exact text to find and replace (use \\n for newlines)
                new_text: The replacement text (use \\n for newlines)

            Returns:
                Success message with details or error message

            Example:
                file_update(
                    file_path="/workspace/myproject/main.py",
                    old_text="def add(a, b):\\n    return a + b",
                    new_text="def add(a, b):\\n    \"\"\"Add two numbers.\"\"\"\\n    return a + b"
                )
            """
            try:
                path = Path(file_path)
                if not path.exists():
                    return f"Error: File not found: {file_path}"
                if not path.is_file():
                    return f"Error: Not a file: {file_path}"

                # Normalize escaped characters
                old_text = normalize_content(old_text)
                new_text = normalize_content(new_text)

                # Read current content
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                # Check if old_text exists
                count = content.count(old_text)
                if count == 0:
                    # Provide helpful context
                    lines = content.split("\n")
                    preview = "\n".join(lines[:20])
                    return (
                        f"Error: Text not found in {file_path}.\n"
                        f"File has {len(lines)} lines.\n"
                        f"First 20 lines:\n{preview}"
                    )

                if count > 1:
                    return (
                        f"Warning: Found {count} occurrences of the text. "
                        f"Please provide more specific text to match exactly one occurrence. "
                        f"Only replacing the first occurrence."
                    )

                # Replace
                new_content = content.replace(old_text, new_text, 1)

                # Write back
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                # Calculate change stats
                old_lines = old_text.count("\n") + 1
                new_lines = new_text.count("\n") + 1

                return (
                    f"✓ Successfully updated {file_path}\n"
                    f"  Replaced {old_lines} lines with {new_lines} lines\n"
                    f"  Occurrences replaced: 1"
                )

            except Exception as e:
                return f"Error updating file: {str(e)}"

        @mcp.tool()
        def file_delete(file_path: str, recursive: bool = False) -> str:
            """
            Delete a file or directory.

            Args:
                file_path: Path to delete
                recursive: Delete directories recursively (default: False for safety)

            Returns:
                Success or error message
            """
            try:
                path = Path(file_path)
                if not path.exists():
                    return f"Path does not exist: {file_path}"

                if path.is_file():
                    path.unlink()
                    return f"Successfully deleted file: {file_path}"
                elif path.is_dir():
                    if recursive:
                        import shutil

                        shutil.rmtree(path)
                        return f"Successfully deleted directory recursively: {file_path}"
                    else:
                        # Only delete if empty
                        if any(path.iterdir()):
                            return f"Directory not empty. Use recursive=True to delete: {file_path}"
                        path.rmdir()
                        return f"Successfully deleted empty directory: {file_path}"

                return f"Cannot delete: {file_path}"
            except Exception as e:
                return f"Error deleting: {str(e)}"
