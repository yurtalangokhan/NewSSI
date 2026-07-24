"""
Code Execution and Testing Tools Category.
Provides tools for running and testing code in various languages.
"""

import ast
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..core.base import BaseToolCategory
from ..core.settings import optional_env

WORKSPACE_DIR = optional_env("WORKSPACE_DIR", "/workspace")


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


class CodeTools(BaseToolCategory):
    """Code execution and testing tools."""

    @property
    def name(self) -> str:
        return "code_execution"

    @property
    def description(self) -> str:
        return "Run and test code in Python, Node.js, and other languages"

    @property
    def label(self) -> str:
        return "Code Execution"

    def register_tools(self, mcp: Any) -> None:
        """Register all code execution tools with MCP."""

        @mcp.tool()
        def run_python(code: str, timeout: int = 30) -> str:
            """
            Execute Python code and return the output.
            Use \\n for newlines when writing multi-line code.

            Args:
                code: Python code to execute (use \\n for newlines)
                timeout: Timeout in seconds (default: 30)

            Returns:
                Code output (stdout + stderr) or error message
            """
            try:
                # Normalize escaped characters from UI input
                code = normalize_code(code)

                # Create a temporary file for the code
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".py",
                    delete=False,
                    dir=WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else None,
                ) as f:
                    f.write(code)
                    temp_file = f.name

                try:
                    result = subprocess.run(
                        ["python3", temp_file],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else None,
                    )

                    output = ""
                    if result.stdout:
                        output += result.stdout
                    if result.stderr:
                        if output:
                            output += "\n[STDERR]:\n"
                        output += result.stderr
                    if result.returncode != 0:
                        output += f"\n[Exit Code: {result.returncode}]"

                    return output if output.strip() else "[No output]"

                finally:
                    # Cleanup temp file
                    os.unlink(temp_file)

            except subprocess.TimeoutExpired:
                return f"Error: Code execution timed out after {timeout} seconds"
            except Exception as e:
                return f"Error executing Python code: {str(e)}"

        @mcp.tool()
        def run_python_file(file_path: str, args: str | None = None, timeout: int = 60) -> str:
            """
            Execute a Python file and return the output.

            Args:
                file_path: Path to the Python file (relative to workspace or absolute)
                args: Command line arguments (optional)
                timeout: Timeout in seconds (default: 60)

            Returns:
                Code output (stdout + stderr) or error message
            """
            # Resolve path
            if not os.path.isabs(file_path):
                file_path = os.path.join(WORKSPACE_DIR, file_path)

            if not os.path.exists(file_path):
                return f"Error: File not found: {file_path}"

            try:
                cmd = ["python3", file_path]
                if args:
                    cmd.extend(args.split())

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=os.path.dirname(file_path),
                )

                output = ""
                if result.stdout:
                    output += result.stdout
                if result.stderr:
                    if output:
                        output += "\n[STDERR]:\n"
                    output += result.stderr
                if result.returncode != 0:
                    output += f"\n[Exit Code: {result.returncode}]"

                return output if output.strip() else "[No output]"

            except subprocess.TimeoutExpired:
                return f"Error: Execution timed out after {timeout} seconds"
            except Exception as e:
                return f"Error executing Python file: {str(e)}"

        @mcp.tool()
        def validate_python(code: str) -> str:
            """
            Validate Python code syntax without executing it.
            Use \\n for newlines when writing multi-line code.

            Args:
                code: Python code to validate (use \\n for newlines)

            Returns:
                Validation result (OK or syntax errors)
            """
            try:
                # Normalize escaped characters from UI input
                code = normalize_code(code)

                ast.parse(code)
                return "✓ Python syntax is valid"
            except SyntaxError as e:
                return f"✗ Syntax Error at line {e.lineno}, column {e.offset}:\n{e.msg}\n\nProblematic line:\n{e.text}"
            except Exception as e:
                return f"✗ Validation error: {str(e)}"

        @mcp.tool()
        def run_node(code: str, timeout: int = 30) -> str:
            """
            Execute JavaScript/Node.js code and return the output.
            Use \\n for newlines when writing multi-line code.

            Args:
                code: JavaScript code to execute (use \\n for newlines)
                timeout: Timeout in seconds (default: 30)

            Returns:
                Code output or error message
            """
            try:
                # Normalize escaped characters from UI input
                code = normalize_code(code)

                # Create a temporary file for the code
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".js",
                    delete=False,
                    dir=WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else None,
                ) as f:
                    f.write(code)
                    temp_file = f.name

                try:
                    result = subprocess.run(
                        ["node", temp_file],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else None,
                    )

                    output = ""
                    if result.stdout:
                        output += result.stdout
                    if result.stderr:
                        if output:
                            output += "\n[STDERR]:\n"
                        output += result.stderr
                    if result.returncode != 0:
                        output += f"\n[Exit Code: {result.returncode}]"

                    return output if output.strip() else "[No output]"

                finally:
                    os.unlink(temp_file)

            except FileNotFoundError:
                return "Error: Node.js is not installed or not in PATH"
            except subprocess.TimeoutExpired:
                return f"Error: Code execution timed out after {timeout} seconds"
            except Exception as e:
                return f"Error executing Node.js code: {str(e)}"

        @mcp.tool()
        def run_pytest(test_path: str, args: str | None = None, timeout: int = 120) -> str:
            """
            Run pytest tests on a file or directory.

            Args:
                test_path: Path to test file or directory (relative to workspace or absolute)
                args: Additional pytest arguments (e.g., "-v", "-x", "--tb=short")
                timeout: Timeout in seconds (default: 120)

            Returns:
                Test results
            """
            # Resolve path
            if not os.path.isabs(test_path):
                test_path = os.path.join(WORKSPACE_DIR, test_path)

            if not os.path.exists(test_path):
                return f"Error: Test path not found: {test_path}"

            try:
                cmd = ["python3", "-m", "pytest", test_path, "-v"]
                if args:
                    cmd.extend(args.split())

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else None,
                )

                output = result.stdout
                if result.stderr:
                    output += f"\n[STDERR]:\n{result.stderr}"

                return output if output.strip() else "[No test output]"

            except subprocess.TimeoutExpired:
                return f"Error: Tests timed out after {timeout} seconds"
            except Exception as e:
                return f"Error running pytest: {str(e)}"

        @mcp.tool()
        def run_npm_command(project_dir: str, command: str, timeout: int = 120) -> str:
            """
            Run an npm command in a project directory.

            Args:
                project_dir: Project directory (relative to workspace or absolute)
                command: npm command to run (e.g., "install", "run build", "test")
                timeout: Timeout in seconds (default: 120)

            Returns:
                Command output
            """
            # Resolve path
            if not os.path.isabs(project_dir):
                project_dir = os.path.join(WORKSPACE_DIR, project_dir)

            if not os.path.exists(project_dir):
                return f"Error: Directory not found: {project_dir}"

            package_json = os.path.join(project_dir, "package.json")
            if not os.path.exists(package_json):
                return f"Error: No package.json found in {project_dir}"

            try:
                cmd = ["npm"] + command.split()

                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout, cwd=project_dir
                )

                output = result.stdout
                if result.stderr:
                    output += f"\n[STDERR]:\n{result.stderr}"
                if result.returncode != 0:
                    output += f"\n[Exit Code: {result.returncode}]"

                return output if output.strip() else "[No output]"

            except FileNotFoundError:
                return "Error: npm is not installed or not in PATH"
            except subprocess.TimeoutExpired:
                return f"Error: Command timed out after {timeout} seconds"
            except Exception as e:
                return f"Error running npm: {str(e)}"

        @mcp.tool()
        def validate_json_file(file_path: str) -> str:
            """
            Validate a JSON file's syntax.

            Args:
                file_path: Path to the JSON file

            Returns:
                Validation result
            """
            # Resolve path
            if not os.path.isabs(file_path):
                file_path = os.path.join(WORKSPACE_DIR, file_path)

            if not os.path.exists(file_path):
                return f"Error: File not found: {file_path}"

            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                json.loads(content)
                return f"✓ JSON is valid: {file_path}"

            except json.JSONDecodeError as e:
                return f"✗ JSON Error at line {e.lineno}, column {e.colno}:\n{e.msg}"
            except Exception as e:
                return f"✗ Error validating JSON: {str(e)}"

        @mcp.tool()
        def run_linter(file_path: str, linter: str = "auto") -> str:
            """
            Run a linter on a file.

            Args:
                file_path: Path to the file to lint
                linter: Linter to use ("auto", "pylint", "flake8", "eslint")

            Returns:
                Linter output
            """
            # Resolve path
            if not os.path.isabs(file_path):
                file_path = os.path.join(WORKSPACE_DIR, file_path)

            if not os.path.exists(file_path):
                return f"Error: File not found: {file_path}"

            # Auto-detect linter based on file extension
            ext = Path(file_path).suffix.lower()

            if linter == "auto":
                if ext == ".py":
                    linter = "flake8"
                elif ext in [".js", ".jsx", ".ts", ".tsx"]:
                    linter = "eslint"
                else:
                    return f"No linter available for {ext} files"

            try:
                if linter == "flake8":
                    cmd = ["python3", "-m", "flake8", file_path, "--max-line-length=120"]
                elif linter == "pylint":
                    cmd = ["python3", "-m", "pylint", file_path, "--disable=C0114,C0115,C0116"]
                elif linter == "eslint":
                    cmd = ["npx", "eslint", file_path]
                else:
                    return f"Unknown linter: {linter}"

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                output = result.stdout + result.stderr

                if not output.strip():
                    return f"✓ No linting issues found in {Path(file_path).name}"

                return output

            except FileNotFoundError:
                return f"Error: {linter} is not installed"
            except Exception as e:
                return f"Error running linter: {str(e)}"

        @mcp.tool()
        def start_dev_server(
            project_dir: str, port: int = 3000, command: str = "npm run dev"
        ) -> str:
            """
            Start a development server (non-blocking check).
            Note: This only validates the setup, actual server needs to run in background.

            Args:
                project_dir: Project directory
                port: Port to check (default: 3000)
                command: Command to suggest for starting the server

            Returns:
                Setup validation and instructions
            """
            # Resolve path
            if not os.path.isabs(project_dir):
                project_dir = os.path.join(WORKSPACE_DIR, project_dir)

            if not os.path.exists(project_dir):
                return f"Error: Directory not found: {project_dir}"

            # Check for package.json (Node.js project)
            package_json = os.path.join(project_dir, "package.json")
            has_node = os.path.exists(package_json)

            # Check for requirements.txt or setup.py (Python project)
            has_python = (
                os.path.exists(os.path.join(project_dir, "requirements.txt"))
                or os.path.exists(os.path.join(project_dir, "setup.py"))
                or os.path.exists(os.path.join(project_dir, "pyproject.toml"))
            )

            # Check for index.html (static site)
            has_html = os.path.exists(os.path.join(project_dir, "index.html"))

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

        @mcp.tool()
        def check_port(port: int) -> str:
            """
            Check if a port is in use.

            Args:
                port: Port number to check

            Returns:
                Port status
            """
            import socket

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    result = s.connect_ex(("localhost", port))

                    if result == 0:
                        return f"Port {port} is IN USE (something is listening)"
                    else:
                        return f"Port {port} is AVAILABLE"

            except Exception as e:
                return f"Error checking port: {str(e)}"
