"""
Java Tools Category.
Provides tools for running JAR files, compiling Java code,
and performing syntax/compilation checks.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..core.base import BaseToolCategory
from ..core.settings import optional_env

WORKSPACE_DIR = optional_env("WORKSPACE_DIR", "/workspace")


def normalize_code(code: str) -> str:
    """Normalize escaped characters from UI/JSON input."""
    code = code.replace("\\n", "\n")
    code = code.replace("\\t", "\t")
    code = code.replace("\\r", "\r")
    code = code.replace('\\"', '"')
    return code


class JavaTools(BaseToolCategory):
    """Java execution, JAR runner, and syntax validation tools."""

    @property
    def name(self) -> str:
        return "java"

    @property
    def description(self) -> str:
        return "Run JAR files, compile and execute Java code, syntax checking"

    @property
    def label(self) -> str:
        return "Java"

    def register_tools(self, mcp: Any) -> None:
        """Register all Java tools with MCP."""

        # ----------------------------------------------------------------
        # 1) JAR Execution
        # ----------------------------------------------------------------
        @mcp.tool()
        def run_jar(
            jar_path: str,
            args: str | None = None,
            main_class: str | None = None,
            jvm_args: str | None = None,
            timeout: int = 120,
        ) -> str:
            """
            Execute a JAR file and return the output.

            Args:
                jar_path: Path to the JAR file (relative to workspace or absolute)
                args: Application arguments (optional, space-separated)
                main_class: Main class to run with -cp instead of -jar (optional)
                jvm_args: Extra JVM arguments like -Xmx512m (optional, space-separated)
                timeout: Timeout in seconds (default: 120)

            Returns:
                Program output (stdout + stderr) or error message
            """
            # Resolve path
            if not os.path.isabs(jar_path):
                jar_path = os.path.join(WORKSPACE_DIR, jar_path)

            if not os.path.exists(jar_path):
                return f"Error: JAR file not found: {jar_path}"

            if not jar_path.endswith(".jar"):
                return f"Error: Not a JAR file: {jar_path}"

            try:
                cmd = ["java"]

                # JVM arguments (memory, system properties, etc.)
                if jvm_args:
                    cmd.extend(jvm_args.split())

                if main_class:
                    # Run a specific class from the JAR classpath
                    cmd.extend(["-cp", jar_path, main_class])
                else:
                    # Standard executable JAR
                    cmd.extend(["-jar", jar_path])

                # Application arguments
                if args:
                    cmd.extend(args.split())

                result = subprocess.run(
                    cmd,
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

            except FileNotFoundError:
                return "Error: Java (JDK/JRE) is not installed or not in PATH"
            except subprocess.TimeoutExpired:
                return f"Error: JAR execution timed out after {timeout} seconds"
            except Exception as e:
                return f"Error executing JAR: {str(e)}"

        # ----------------------------------------------------------------
        # 2) Compile & Run Java source code
        # ----------------------------------------------------------------
        @mcp.tool()
        def run_java(code: str, class_name: str = "Main", timeout: int = 60) -> str:
            """
            Compile and execute Java source code.
            Use \\n for newlines when writing multi-line code.

            Args:
                code: Java source code (use \\n for newlines)
                class_name: Public class name in the code (default: Main)
                timeout: Timeout in seconds (default: 60)

            Returns:
                Program output or compilation errors
            """
            try:
                code = normalize_code(code)

                # Create a temp directory for compilation
                with tempfile.TemporaryDirectory(
                    dir=WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else None
                ) as tmp_dir:
                    src_file = os.path.join(tmp_dir, f"{class_name}.java")
                    with open(src_file, "w", encoding="utf-8") as f:
                        f.write(code)

                    # Compile
                    compile_result = subprocess.run(
                        ["javac", src_file],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=tmp_dir,
                    )

                    if compile_result.returncode != 0:
                        errors = compile_result.stderr or compile_result.stdout
                        return f"✗ Compilation failed:\n{errors}"

                    # Run
                    run_result = subprocess.run(
                        ["java", "-cp", tmp_dir, class_name],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=tmp_dir,
                    )

                    output = ""
                    if run_result.stdout:
                        output += run_result.stdout
                    if run_result.stderr:
                        if output:
                            output += "\n[STDERR]:\n"
                        output += run_result.stderr
                    if run_result.returncode != 0:
                        output += f"\n[Exit Code: {run_result.returncode}]"

                    return output if output.strip() else "[No output]"

            except FileNotFoundError:
                return "Error: Java (JDK) is not installed or not in PATH. javac is required."
            except subprocess.TimeoutExpired:
                return f"Error: Execution timed out after {timeout} seconds"
            except Exception as e:
                return f"Error: {str(e)}"

        # ----------------------------------------------------------------
        # 3) Compile a Java file (no execution)
        # ----------------------------------------------------------------
        @mcp.tool()
        def compile_java_file(
            file_path: str,
            output_dir: str | None = None,
            timeout: int = 60,
        ) -> str:
            """
            Compile a Java source file without running it.

            Args:
                file_path: Path to .java file (relative to workspace or absolute)
                output_dir: Directory for compiled .class files (optional)
                timeout: Timeout in seconds (default: 60)

            Returns:
                Compilation result (success or error details)
            """
            if not os.path.isabs(file_path):
                file_path = os.path.join(WORKSPACE_DIR, file_path)

            if not os.path.exists(file_path):
                return f"Error: File not found: {file_path}"

            try:
                cmd = ["javac"]
                if output_dir:
                    out = (
                        output_dir
                        if os.path.isabs(output_dir)
                        else os.path.join(WORKSPACE_DIR, output_dir)
                    )
                    os.makedirs(out, exist_ok=True)
                    cmd.extend(["-d", out])
                cmd.append(file_path)

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else None,
                )

                if result.returncode == 0:
                    return f"✓ Compilation successful: {Path(file_path).name}"
                else:
                    errors = result.stderr or result.stdout
                    return f"✗ Compilation failed:\n{errors}"

            except FileNotFoundError:
                return "Error: javac not found. JDK is required."
            except subprocess.TimeoutExpired:
                return f"Error: Compilation timed out after {timeout} seconds"
            except Exception as e:
                return f"Error: {str(e)}"

        # ----------------------------------------------------------------
        # 4) Java Syntax Check (compile-only, no .class output)
        # ----------------------------------------------------------------
        @mcp.tool()
        def validate_java(code: str, class_name: str = "Main") -> str:
            """
            Validate Java code syntax without producing class files.
            Uses javac with a temp file to catch all compile-time errors.
            Use \\n for newlines when writing multi-line code.

            Args:
                code: Java source code to validate (use \\n for newlines)
                class_name: Public class name in the code (default: Main)

            Returns:
                Validation result – OK or detailed error list
            """
            try:
                code = normalize_code(code)

                with tempfile.TemporaryDirectory(
                    dir=WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else None
                ) as tmp_dir:
                    src_file = os.path.join(tmp_dir, f"{class_name}.java")
                    with open(src_file, "w", encoding="utf-8") as f:
                        f.write(code)

                    result = subprocess.run(
                        ["javac", "-Xlint:all", src_file],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=tmp_dir,
                    )

                    if result.returncode == 0:
                        warnings = result.stderr.strip() if result.stderr else ""
                        if warnings:
                            return f"✓ Java syntax is valid (with warnings):\n{warnings}"
                        return "✓ Java syntax is valid – no errors or warnings"
                    else:
                        errors = result.stderr or result.stdout
                        return f"✗ Java syntax errors:\n{errors}"

            except FileNotFoundError:
                return "Error: javac not found. JDK is required for validation."
            except subprocess.TimeoutExpired:
                return "Error: Validation timed out"
            except Exception as e:
                return f"Error: {str(e)}"

        # ----------------------------------------------------------------
        # 5) Validate a Java file on disk
        # ----------------------------------------------------------------
        @mcp.tool()
        def validate_java_file(file_path: str) -> str:
            """
            Validate syntax of an existing Java file without producing class files.

            Args:
                file_path: Path to .java file (relative to workspace or absolute)

            Returns:
                Validation result – OK or detailed error list
            """
            if not os.path.isabs(file_path):
                file_path = os.path.join(WORKSPACE_DIR, file_path)

            if not os.path.exists(file_path):
                return f"Error: File not found: {file_path}"

            try:
                name = Path(file_path).name

                with tempfile.TemporaryDirectory(
                    dir=WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else None
                ) as tmp_dir:
                    result = subprocess.run(
                        ["javac", "-Xlint:all", "-d", tmp_dir, file_path],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=WORKSPACE_DIR if os.path.exists(WORKSPACE_DIR) else None,
                    )

                    if result.returncode == 0:
                        warnings = result.stderr.strip() if result.stderr else ""
                        if warnings:
                            return f"✓ {name} is valid (with warnings):\n{warnings}"
                        return f"✓ {name} – no syntax errors"
                    else:
                        errors = result.stderr or result.stdout
                        return f"✗ {name} has errors:\n{errors}"

            except FileNotFoundError:
                return "Error: javac not found. JDK is required."
            except subprocess.TimeoutExpired:
                return "Error: Validation timed out"
            except Exception as e:
                return f"Error: {str(e)}"

        # ----------------------------------------------------------------
        # 6) Inspect JAR contents
        # ----------------------------------------------------------------
        @mcp.tool()
        def inspect_jar(jar_path: str, show_manifest: bool = True) -> str:
            """
            List contents of a JAR file and optionally show its manifest.

            Args:
                jar_path: Path to the JAR file (relative to workspace or absolute)
                show_manifest: Whether to display META-INF/MANIFEST.MF (default: True)

            Returns:
                JAR contents listing
            """
            if not os.path.isabs(jar_path):
                jar_path = os.path.join(WORKSPACE_DIR, jar_path)

            if not os.path.exists(jar_path):
                return f"Error: JAR file not found: {jar_path}"

            try:
                # List contents
                list_result = subprocess.run(
                    ["jar", "tf", jar_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if list_result.returncode != 0:
                    return f"Error listing JAR: {list_result.stderr}"

                entries = list_result.stdout.strip().split("\n")
                output = f"📦 JAR: {Path(jar_path).name}\n"
                output += f"   Entries: {len(entries)}\n\n"

                # Show manifest if requested
                if show_manifest:
                    manifest_result = subprocess.run(
                        ["unzip", "-p", jar_path, "META-INF/MANIFEST.MF"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if manifest_result.returncode == 0 and manifest_result.stdout.strip():
                        output += "── MANIFEST.MF ──\n"
                        output += manifest_result.stdout.strip() + "\n\n"

                # Group entries by top-level directory
                dirs = set()
                files_root = []
                for entry in entries:
                    parts = entry.split("/")
                    if len(parts) > 1:
                        dirs.add(parts[0] + "/")
                    else:
                        files_root.append(entry)

                output += "── Structure ──\n"
                for d in sorted(dirs):
                    count = sum(1 for e in entries if e.startswith(d) and not e.endswith("/"))
                    output += f"  📁 {d}  ({count} files)\n"
                for f in sorted(files_root):
                    if f.strip():
                        output += f"  📄 {f}\n"

                return output

            except FileNotFoundError:
                return "Error: jar/unzip command not found"
            except Exception as e:
                return f"Error inspecting JAR: {str(e)}"
