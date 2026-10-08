"""
Java Tools Category.
Provides tools for running JAR files, compiling Java code,
and performing syntax/compilation checks.

Every path-taking tool in this module resolves its argument through
resolve_in_workspace before touching the filesystem or setting a
subprocess cwd — see spec TS-2. run_java/validate_java additionally
validate class_name as a Java identifier before using it to build a file
name (f"{class_name}.java"): an unchecked value like "../../etc/pwned"
would otherwise let the source file land outside the temp compile
directory.
"""

import os
import re
import subprocess
import tempfile
from typing import Any

from localization import t

from ..core.base import BaseToolCategory
from ..core.sandbox import run_capped
from ..core.schema import BoundedTimeout, LongText, ShortText
from ..core.workspace import (
    WorkspacePath,
    guard_workspace_escape,
    resolve_in_workspace,
    workspace_root,
)
from .response import tool_error_message

_JAVA_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


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
        return t(
            "categories.java.description",
            default="Run JAR files, compile and execute Java code, syntax checking",
        )

    @property
    def label(self) -> str:
        return t("categories.java.label", default="Java")

    def register_tools(self, mcp: Any) -> None:
        """Register all Java tools with MCP."""

        # ----------------------------------------------------------------
        # 1) JAR Execution
        # ----------------------------------------------------------------
        @mcp.tool()
        @guard_workspace_escape
        def run_jar(
            jar_path: WorkspacePath,
            args: ShortText | None = None,
            main_class: ShortText | None = None,
            jvm_args: ShortText | None = None,
            timeout: BoundedTimeout = 120,
        ) -> str:
            """
            Execute a JAR file inside the workspace and return the output.

            Args:
                jar_path: Path to the JAR file, relative to the workspace
                args: Application arguments (optional, space-separated)
                main_class: Main class to run with -cp instead of -jar (optional)
                jvm_args: Extra JVM arguments like -Xmx512m (optional, space-separated)
                timeout: Timeout in seconds (default: 120)

            Returns:
                Program output (stdout + stderr) or error message
            """
            root = workspace_root()
            path = resolve_in_workspace(jar_path, root=root)

            if not path.exists():
                return t("java.jar_not_found", path=jar_path)

            if path.suffix != ".jar":
                return t("java.not_a_jar", path=jar_path)

            try:
                cmd = ["java"]

                # JVM arguments (memory, system properties, etc.)
                if jvm_args:
                    cmd.extend(jvm_args.split())

                if main_class:
                    # Run a specific class from the JAR classpath
                    cmd.extend(["-cp", str(path), main_class])
                else:
                    # Standard executable JAR
                    cmd.extend(["-jar", str(path)])

                # Application arguments
                if args:
                    cmd.extend(args.split())

                result = run_capped(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(root) if root.exists() else None,
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
                return t("java.jdk_not_installed")
            except subprocess.TimeoutExpired:
                return t("java.jar_timeout", seconds=timeout)
            except (subprocess.SubprocessError, OSError, UnicodeError, ValueError) as e:
                return t("java.jar_execution_error", error=tool_error_message(e))

        # ----------------------------------------------------------------
        # 2) Compile & Run Java source code
        # ----------------------------------------------------------------
        @mcp.tool()
        def run_java(code: LongText, class_name: ShortText = "Main", timeout: BoundedTimeout = 60) -> str:
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
            if not _JAVA_IDENTIFIER.match(class_name):
                return t(
                    "java.invalid_class_name",
                    class_name=class_name,
                    default=f"Invalid class name: {class_name!r}",
                )

            root = workspace_root()
            try:
                code = normalize_code(code)

                # Create a temp directory for compilation, inside the
                # workspace so the compiled program's own relative file
                # access stays within the same boundary as every other tool.
                with tempfile.TemporaryDirectory(dir=str(root) if root.exists() else None) as tmp_dir:
                    src_file = os.path.join(tmp_dir, f"{class_name}.java")
                    with open(src_file, "w", encoding="utf-8") as f:
                        f.write(code)

                    # Compile
                    compile_result = run_capped(
                        ["javac", src_file],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=tmp_dir,
                    )

                    if compile_result.returncode != 0:
                        errors = compile_result.stderr or compile_result.stdout
                        return t("java.compilation_failed", errors=errors)

                    # Run
                    run_result = run_capped(
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
                return t("java.jdk_javac_not_installed")
            except subprocess.TimeoutExpired:
                return t("java.run_timeout", seconds=timeout)
            except (subprocess.SubprocessError, OSError, UnicodeError, ValueError) as e:
                return t("common.error", error=tool_error_message(e))

        # ----------------------------------------------------------------
        # 3) Compile a Java file (no execution)
        # ----------------------------------------------------------------
        @mcp.tool()
        @guard_workspace_escape
        def compile_java_file(
            file_path: WorkspacePath,
            output_dir: WorkspacePath | None = None,
            timeout: BoundedTimeout = 60,
        ) -> str:
            """
            Compile a Java source file inside the workspace without running it.

            Args:
                file_path: Path to .java file, relative to the workspace
                output_dir: Directory for compiled .class files, relative to
                    the workspace (optional)
                timeout: Timeout in seconds (default: 60)

            Returns:
                Compilation result (success or error details)
            """
            root = workspace_root()
            path = resolve_in_workspace(file_path, root=root)

            if not path.exists():
                return t("java.file_not_found", path=file_path)

            try:
                cmd = ["javac"]
                if output_dir:
                    out = resolve_in_workspace(output_dir, root=root)
                    out.mkdir(parents=True, exist_ok=True)
                    cmd.extend(["-d", str(out)])
                cmd.append(str(path))

                result = run_capped(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(root) if root.exists() else None,
                )

                if result.returncode == 0:
                    return f"✓ Compilation successful: {path.name}"
                else:
                    errors = result.stderr or result.stdout
                    return t("java.compilation_failed", errors=errors)

            except FileNotFoundError:
                return t("java.javac_not_found")
            except subprocess.TimeoutExpired:
                return t("java.compile_timeout", seconds=timeout)
            except (subprocess.SubprocessError, OSError, UnicodeError, ValueError) as e:
                return t("common.error", error=tool_error_message(e))

        # ----------------------------------------------------------------
        # 4) Java Syntax Check (compile-only, no .class output)
        # ----------------------------------------------------------------
        @mcp.tool()
        def validate_java(code: LongText, class_name: ShortText = "Main") -> str:
            """
            Validate Java code syntax without producing class files.
            Uses javac with a temp file to catch all compile-time errors.
            Use \\n for newlines when writing multi-line code.

            Args:
                code: Java source code to validate (use \\n for newlines)
                class_name: Public class name in the code (default: Main)

            Returns:
                Validation result - OK or detailed error list
            """
            if not _JAVA_IDENTIFIER.match(class_name):
                return t(
                    "java.invalid_class_name",
                    class_name=class_name,
                    default=f"Invalid class name: {class_name!r}",
                )

            root = workspace_root()
            try:
                code = normalize_code(code)

                with tempfile.TemporaryDirectory(dir=str(root) if root.exists() else None) as tmp_dir:
                    src_file = os.path.join(tmp_dir, f"{class_name}.java")
                    with open(src_file, "w", encoding="utf-8") as f:
                        f.write(code)

                    result = run_capped(
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
                        return "✓ Java syntax is valid - no errors or warnings"
                    else:
                        errors = result.stderr or result.stdout
                        return t("java.syntax_errors", errors=errors)

            except FileNotFoundError:
                return t("java.javac_not_found_validate")
            except subprocess.TimeoutExpired:
                return t("java.validation_timeout")
            except (subprocess.SubprocessError, OSError, UnicodeError, ValueError) as e:
                return t("common.error", error=tool_error_message(e))

        # ----------------------------------------------------------------
        # 5) Validate a Java file on disk
        # ----------------------------------------------------------------
        @mcp.tool()
        @guard_workspace_escape
        def validate_java_file(file_path: WorkspacePath) -> str:
            """
            Validate syntax of a Java file inside the workspace without
            producing class files.

            Args:
                file_path: Path to .java file, relative to the workspace

            Returns:
                Validation result - OK or detailed error list
            """
            root = workspace_root()
            path = resolve_in_workspace(file_path, root=root)

            if not path.exists():
                return t("java.file_not_found", path=file_path)

            try:
                name = path.name

                with tempfile.TemporaryDirectory(dir=str(root) if root.exists() else None) as tmp_dir:
                    result = run_capped(
                        ["javac", "-Xlint:all", "-d", tmp_dir, str(path)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=str(root) if root.exists() else None,
                    )

                    if result.returncode == 0:
                        warnings = result.stderr.strip() if result.stderr else ""
                        if warnings:
                            return f"✓ {name} is valid (with warnings):\n{warnings}"
                        return f"✓ {name} - no syntax errors"
                    else:
                        errors = result.stderr or result.stdout
                        return t("java.file_has_errors", name=name, errors=errors)

            except FileNotFoundError:
                return t("java.javac_not_found")
            except subprocess.TimeoutExpired:
                return t("java.validation_timeout")
            except (subprocess.SubprocessError, OSError, UnicodeError, ValueError) as e:
                return t("common.error", error=tool_error_message(e))

        # ----------------------------------------------------------------
        # 6) Inspect JAR contents
        # ----------------------------------------------------------------
        @mcp.tool()
        @guard_workspace_escape
        def inspect_jar(jar_path: WorkspacePath, show_manifest: bool = True) -> str:
            """
            List contents of a JAR file inside the workspace and optionally
            show its manifest.

            Args:
                jar_path: Path to the JAR file, relative to the workspace
                show_manifest: Whether to display META-INF/MANIFEST.MF (default: True)

            Returns:
                JAR contents listing
            """
            path = resolve_in_workspace(jar_path, root=workspace_root())

            if not path.exists():
                return t("java.jar_not_found", path=jar_path)

            try:
                # List contents
                list_result = run_capped(
                    ["jar", "tf", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if list_result.returncode != 0:
                    return t("java.list_error", error=list_result.stderr)

                entries = list_result.stdout.strip().split("\n")
                output = f"📦 JAR: {path.name}\n"
                output += f"   Entries: {len(entries)}\n\n"

                # Show manifest if requested
                if show_manifest:
                    manifest_result = run_capped(
                        ["unzip", "-p", str(path), "META-INF/MANIFEST.MF"],
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
                return t("java.jar_unzip_not_found")
            except (subprocess.SubprocessError, OSError, UnicodeError, ValueError) as e:
                return t("java.inspect_error", error=tool_error_message(e))
