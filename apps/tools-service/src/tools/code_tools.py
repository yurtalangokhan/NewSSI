"""
Code Execution and Testing Tools Category.
Provides tools for running and testing code in various languages.

Every path-taking tool in this module resolves its argument through
resolve_in_workspace before touching the filesystem or setting a
subprocess cwd — see spec TS-2. check_port was removed entirely: a
localhost port scanner has no legitimate use for a model and is internal
network reconnaissance for anyone else — see spec TS-4.

Every tool that runs a model-supplied program (run_python, run_python_file,
run_node, run_pytest, run_npm_command) or an external linter (run_linter)
goes through core.sandbox.run_sandboxed instead of a bare subprocess.run:
argv only, its own process group so a timeout kills grandchildren, rlimits
on CPU/memory/open files, a clean environment the service's own secrets
are never inherited into, and a server-side cap on the timeout a model can
request — see spec TS-7a.
"""

import json
from pathlib import Path
import tempfile
from typing import Any

from localization import t

from ..core.base import BaseToolCategory
from ..core.sandbox import SandboxResult, run_sandboxed
from ..core.schema import BoundedTimeout, LongText, ShortText
from ..core.workspace import (
    WorkspaceEscapeError,
    WorkspacePath,
    guard_workspace_escape,
    resolve_in_workspace,
    workspace_root,
)
from .response import tool_error_message


def normalize_code(code: str) -> str:
    """
    Normalize code string by converting escaped characters to actual characters.
    This handles input from JSON/UI where newlines are escaped as literal \\n.
    """
    # Convert literal \n to actual newlines (but not already-real newlines)
    code = code.replace("\\n", "\n")
    # Convert literal \t to actual tabs
    code = code.replace("\\t", "\t")
    # Convert literal \r to carriage return
    code = code.replace("\\r", "\r")
    return code


def _format_output(result: SandboxResult) -> str:
    output = result.stdout
    if result.stderr:
        output += f"\n[STDERR]: {result.stderr}"
    if result.exit_code != 0:
        output += f"\n[Exit Code: {result.exit_code}]"
    return output if output.strip() else "[No output]"


class CodeTools(BaseToolCategory):
    """Code execution and testing tools."""

    @property
    def name(self) -> str:
        return "code_execution"

    @property
    def description(self) -> str:
        return t(
            "categories.code_execution.description",
            default="Run and test code in Python, Node.js, and other languages",
        )

    @property
    def label(self) -> str:
        return t("categories.code_execution.label", default="Code Execution")

    def register_tools(self, mcp: Any) -> None:
        """Register all code execution tools with MCP."""

        @mcp.tool()
        async def run_python(code: LongText, timeout: BoundedTimeout = 30) -> str:  # noqa: ASYNC109 - timeout is part of the MCP tool schema
            """
            Execute Python code and return the output.
            Use \\n for newlines when writing multi-line code.

            Args:
                code: Python code to execute (use \\n for newlines)
                timeout: Timeout in seconds (default: 30, capped server-side)

            Returns:
                Code output (stdout + stderr) or error message
            """
            try:
                root = workspace_root()
                code = normalize_code(code)

                # A temporary file inside the workspace, so the code's own
                # cwd-relative file access stays within the same boundary as
                # every other tool.
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False, dir=str(root), encoding="utf-8"
                ) as f:
                    f.write(code)
                    script = Path(f.name)

                try:
                    result = await run_sandboxed(["python3", str(script)], cwd=root, execution_timeout=timeout)
                finally:
                    script.unlink(missing_ok=True)  # noqa: ASYNC240 - unlink is a negligible blocking op  # noqa: ASYNC240 - unlink is a negligible blocking op

                if result.timed_out:
                    return t("code.execution_timeout", seconds=timeout)
                return _format_output(result)
            except (OSError, ValueError) as e:
                return t("code.python_execution_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        async def run_python_file(
            file_path: WorkspacePath,
            args: ShortText | None = None,
            timeout: BoundedTimeout = 60,  # noqa: ASYNC109 - part of the MCP tool schema
        ) -> str:
            """
            Execute a Python file inside the workspace and return the output.

            Args:
                file_path: Path to the Python file, relative to the workspace
                args: Command line arguments (optional)
                timeout: Timeout in seconds (default: 60, capped server-side)

            Returns:
                Code output (stdout + stderr) or error message
            """
            try:
                path = resolve_in_workspace(file_path, root=workspace_root())

                if not path.exists():
                    return t("code.file_not_found", path=file_path)

                cmd = ["python3", str(path)]
                if args:
                    cmd.extend(args.split())

                result = await run_sandboxed(cmd, cwd=path.parent, execution_timeout=timeout)

                if result.timed_out:
                    return t("code.file_execution_timeout", seconds=timeout)
                return _format_output(result)
            except WorkspaceEscapeError:
                raise
            except (OSError, ValueError) as e:
                return t("code.python_file_error", error=tool_error_message(e))

        @mcp.tool()
        def validate_python(code: LongText) -> str:
            """
            Validate Python code syntax without executing it.
            Use \\n for newlines when writing multi-line code.

            Args:
                code: Python code to validate (use \\n for newlines)

            Returns:
                Validation result (OK or syntax errors)
            """
            import ast

            try:
                # Normalize escaped characters from UI input
                code = normalize_code(code)

                ast.parse(code)
                return "✓ Python syntax is valid"
            except SyntaxError as e:
                return t(
                    "code.python_syntax_error",
                    lineno=e.lineno,
                    offset=e.offset,
                    msg=e.msg,
                    text=e.text,
                )
            except ValueError as e:
                # ast.parse raises ValueError (not SyntaxError) for input
                # containing NUL bytes.
                return t("code.validation_error", error=tool_error_message(e))

        @mcp.tool()
        async def run_node(code: LongText, timeout: BoundedTimeout = 30) -> str:  # noqa: ASYNC109 - timeout is part of the MCP tool schema
            """
            Execute JavaScript/Node.js code and return the output.
            Use \\n for newlines when writing multi-line code.

            Args:
                code: JavaScript code to execute (use \\n for newlines)
                timeout: Timeout in seconds (default: 30, capped server-side)

            Returns:
                Code output or error message
            """
            try:
                root = workspace_root()
                code = normalize_code(code)

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".js", delete=False, dir=str(root), encoding="utf-8"
                ) as f:
                    f.write(code)
                    script = Path(f.name)

                try:
                    try:
                        result = await run_sandboxed(["node", str(script)], cwd=root, execution_timeout=timeout)
                    except FileNotFoundError:
                        return t("code.node_not_installed")
                finally:
                    script.unlink(missing_ok=True)  # noqa: ASYNC240 - unlink is a negligible blocking op

                if result.timed_out:
                    return t("code.execution_timeout", seconds=timeout)
                return _format_output(result)
            except (OSError, ValueError) as e:
                return t("code.node_execution_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        async def run_pytest(
            test_path: WorkspacePath,
            args: ShortText | None = None,
            timeout: BoundedTimeout = 120,  # noqa: ASYNC109 - part of the MCP tool schema
        ) -> str:
            """
            Run pytest tests on a file or directory inside the workspace.

            Args:
                test_path: Path to test file or directory, relative to the workspace
                args: Additional pytest arguments (e.g., "-v", "-x", "--tb=short")
                timeout: Timeout in seconds (default: 120, capped server-side)

            Returns:
                Test results
            """
            try:
                root = workspace_root()
                path = resolve_in_workspace(test_path, root=root)

                if not path.exists():
                    return t("code.test_path_not_found", path=test_path)

                cmd = ["python3", "-m", "pytest", str(path), "-v"]
                if args:
                    cmd.extend(args.split())

                result = await run_sandboxed(cmd, cwd=root, execution_timeout=timeout)

                if result.timed_out:
                    return t("code.test_timeout", seconds=timeout)
                output = result.stdout
                if result.stderr:
                    output += f"\n[STDERR]:\n{result.stderr}"
                return output if output.strip() else "[No test output]"
            except WorkspaceEscapeError:
                raise
            except (OSError, ValueError) as e:
                return t("code.pytest_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        async def run_npm_command(project_dir: WorkspacePath, command: ShortText, timeout: BoundedTimeout = 120) -> str:  # noqa: ASYNC109 - timeout is part of the MCP tool schema
            """
            Run an npm command in a project directory inside the workspace.

            Args:
                project_dir: Project directory, relative to the workspace
                command: npm command to run (e.g., "install", "run build", "test")
                timeout: Timeout in seconds (default: 120, capped server-side)

            Returns:
                Command output
            """
            try:
                path = resolve_in_workspace(project_dir, root=workspace_root())

                if not path.exists():
                    return t("code.directory_not_found", path=project_dir)

                package_json = path / "package.json"
                if not package_json.exists():
                    return t("code.package_json_not_found", path=project_dir)

                cmd = ["npm", *command.split()]

                try:
                    result = await run_sandboxed(cmd, cwd=path, execution_timeout=timeout)
                except FileNotFoundError:
                    return t("code.npm_not_installed")

                if result.timed_out:
                    return t("code.command_timeout", seconds=timeout)
                return _format_output(result)
            except WorkspaceEscapeError:
                raise
            except (OSError, ValueError) as e:
                return t("code.npm_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def validate_json_file(file_path: WorkspacePath) -> str:
            """
            Validate a JSON file's syntax. The file must be inside the workspace.

            Args:
                file_path: Path to the JSON file, relative to the workspace

            Returns:
                Validation result
            """
            path = resolve_in_workspace(file_path, root=workspace_root())

            if not path.exists():
                return t("code.file_not_found", path=file_path)

            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()

                json.loads(content)
                return f"✓ JSON is valid: {file_path}"

            except json.JSONDecodeError as e:
                return t("code.json_syntax_error", lineno=e.lineno, colno=e.colno, msg=e.msg)
            except (OSError, UnicodeError, ValueError) as e:
                return t("code.json_validate_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        async def run_linter(file_path: WorkspacePath, linter: ShortText = "auto") -> str:
            """
            Run a linter on a file inside the workspace.

            Args:
                file_path: Path to the file to lint, relative to the workspace
                linter: Linter to use ("auto", "pylint", "flake8", "eslint")

            Returns:
                Linter output
            """
            try:
                path = resolve_in_workspace(file_path, root=workspace_root())

                if not path.exists():
                    return t("code.file_not_found", path=file_path)

                # Auto-detect linter based on file extension
                ext = path.suffix.lower()

                if linter == "auto":
                    if ext == ".py":
                        linter = "flake8"
                    elif ext in [".js", ".jsx", ".ts", ".tsx"]:
                        linter = "eslint"
                    else:
                        return t("code.no_linter_for_extension", ext=ext)

                if linter == "flake8":
                    cmd = ["python3", "-m", "flake8", str(path), "--max-line-length=120"]
                elif linter == "pylint":
                    cmd = ["python3", "-m", "pylint", str(path), "--disable=C0114,C0115,C0116"]
                elif linter == "eslint":
                    cmd = ["npx", "eslint", str(path)]
                else:
                    return t("code.unknown_linter", linter=linter)

                try:
                    result = await run_sandboxed(cmd, cwd=path.parent, execution_timeout=60)
                except FileNotFoundError:
                    return t("code.linter_not_installed", linter=linter)

                if result.timed_out:
                    return t("code.linter_timeout", linter=linter, default=f"{linter} timed out")

                output = result.stdout + result.stderr
                if not output.strip():
                    return f"✓ No linting issues found in {path.name}"
                return output
            except WorkspaceEscapeError:
                raise
            except (OSError, ValueError) as e:
                return t("code.linter_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def start_dev_server(project_dir: WorkspacePath, port: int = 3000, command: ShortText = "npm run dev") -> str:
            """
            Start a development server (non-blocking check).
            Note: This only validates the setup, actual server needs to run in background.

            Args:
                project_dir: Project directory, relative to the workspace
                port: Port to check (default: 3000)
                command: Command to suggest for starting the server

            Returns:
                Setup validation and instructions
            """
            path = resolve_in_workspace(project_dir, root=workspace_root())

            if not path.exists():
                return t("code.directory_not_found", path=project_dir)

            # Check for package.json (Node.js project)
            has_node = (path / "package.json").exists()

            # Check for requirements.txt or setup.py (Python project)
            has_python = (
                (path / "requirements.txt").exists()
                or (path / "setup.py").exists()
                or (path / "pyproject.toml").exists()
            )

            # Check for index.html (static site)
            has_html = (path / "index.html").exists()

            result = f"Project directory: {project_dir}\n\n"
            result += "Detected project types:\n"

            if has_node:
                result += "  ✓ Node.js project (package.json found)\n"
                result += f"    Start command: cd {project_dir} && {command}\n"

            if has_python:
                result += "  ✓ Python project\n"
                result += f"    Start command: cd {project_dir} && python -m http.server {port}\n"

            if has_html:
                result += "  ✓ Static HTML site (index.html found)\n"
                result += f"    Start command: cd {project_dir} && python -m http.server {port}\n"

            if not (has_node or has_python or has_html):
                result += "  ⚠ No recognized project structure\n"

            result += f"\nServer would be available at: http://localhost:{port}"

            return result
