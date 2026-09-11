"""Canonical catalog of the built-in MCP tool categories.

Single source of truth for the built-in MCP tool categories. Everything that
needs the category list derives it from here instead of re-declaring it:

- ``domain/flows/sources.py`` — the ``mcp.tools.{category}`` option-source keys
- ``domain/flows/resolvers.py`` — the offline fallback tool lists and the
  ``mcp.tools.{category}`` resolver dispatch table
- ``domain/flows/agent_expansion.py`` — the category → flow-canvas node ``type``
  map used when materializing a classic agent onto the canvas

Adding or renaming a category is a one-line change in :data:`MCP_CATEGORIES`.

The tool names/labels/descriptions were verified against the live tools
service; keep them in sync with that contract when it changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class BuiltinTool:
    """One tool exposed by a built-in MCP category (offline fallback data)."""

    value: str
    label: str
    description: str


@dataclass(frozen=True)
class McpCategory:
    """A built-in MCP tool category and how the flow canvas represents it."""

    key: str
    node_type: str | None
    """Flow-canvas node ``type`` carrying this category's tools.

    ``None`` when the category is represented by a bespoke node that needs
    extra wiring (``mail`` → ``MailTools`` + ``MailConfig``) and therefore
    must not be auto-materialized from a plain category node.
    """
    tools: tuple[BuiltinTool, ...] = ()


MCP_CATEGORIES: Final[tuple[McpCategory, ...]] = (
    McpCategory(
        "calculator",
        "CalculatorTools",
        (BuiltinTool("calculate", "Calculate", "Evaluate a mathematical expression safely."),),
    ),
    McpCategory(
        "code",
        "CodeTools",
        (
            BuiltinTool(
                "check_port", "Check Network Port", "Check if a network port is open/listening."
            ),
            BuiltinTool(
                "run_linter", "Run Code Linter", "Lint source code using installed linter."
            ),
            BuiltinTool("run_node", "Run Node.js Code", "Execute Node.js (JavaScript) code."),
            BuiltinTool(
                "run_npm_command",
                "Run NPM Command",
                "Run an npm command in a Node.js project directory.",
            ),
            BuiltinTool("run_pytest", "Run Pytest", "Run pytest on a test file or directory."),
            BuiltinTool(
                "run_python", "Run Python Code", "Execute Python code in an isolated subprocess."
            ),
            BuiltinTool(
                "run_python_file", "Run Python Script File", "Execute a Python script file."
            ),
            BuiltinTool(
                "start_dev_server",
                "Start Development Server",
                "Start a background development server.",
            ),
            BuiltinTool(
                "validate_json_file",
                "Validate JSON File",
                "Validate a JSON file for syntax errors.",
            ),
            BuiltinTool(
                "validate_python",
                "Validate Python Syntax",
                "Check Python code for syntax errors without executing.",
            ),
        ),
    ),
    McpCategory(
        "command",
        "CommandTools",
        (
            BuiltinTool(
                "execute_shell",
                "Execute Shell Command",
                "Execute a shell command in a sandboxed environment.",
            ),
            BuiltinTool(
                "get_system_info",
                "Get System Information",
                "Get system information (OS, CPU, memory, disk).",
            ),
        ),
    ),
    McpCategory(
        "docker",
        "DockerTools",
        (
            BuiltinTool(
                "docker_build", "Build Docker Image", "Build a Docker image from a Dockerfile."
            ),
            BuiltinTool(
                "docker_logs", "Get Docker Container Logs", "Get logs from a Docker container."
            ),
            BuiltinTool("docker_ps", "List Docker Containers", "List running Docker containers."),
            BuiltinTool("docker_run", "Run Docker Container", "Run a Docker container."),
            BuiltinTool("docker_stop", "Stop Docker Container", "Stop a running Docker container."),
        ),
    ),
    McpCategory(
        "file",
        "FileTools",
        (
            BuiltinTool("create_directory", "Create Directory", "Create a new directory."),
            BuiltinTool("file_delete", "Delete File", "Delete a file or directory."),
            BuiltinTool("file_exists", "Check File Exists", "Check if a file or directory exists."),
            BuiltinTool("file_list", "List Directory Files", "List contents of a directory."),
            BuiltinTool("file_read", "Read File", "Read contents of a text file."),
            BuiltinTool(
                "file_update",
                "Update File",
                "Update an existing file by replacing a specific text block.",
            ),
            BuiltinTool("file_write", "Write File", "Write content to a file."),
        ),
    ),
    McpCategory(
        "git",
        "GitTools",
        (
            BuiltinTool("git_branch", "Manage Git Branches", "List, create, or delete branches."),
            BuiltinTool("git_clone", "Clone Git Repository", "Clone a Git repository."),
            BuiltinTool("git_commit", "Commit Git Changes", "Commit staged changes."),
            BuiltinTool(
                "git_config",
                "Git Configuration",
                "Get or set Git configuration values (user.email, user.name).",
            ),
            BuiltinTool("git_diff", "Show Git Diff", "View git diff."),
            BuiltinTool(
                "git_init", "Initialize Git Repository", "Initialize a new Git repository."
            ),
            BuiltinTool("git_log", "Show Git Log", "View commit history log."),
            BuiltinTool(
                "git_pull", "Pull Git Repository", "Pull latest changes from remote repository."
            ),
            BuiltinTool(
                "git_push", "Push Git Repository", "Push local commits to remote repository."
            ),
            BuiltinTool("git_remote_add", "Add Git Remote", "Add a new remote repository."),
            BuiltinTool("git_status", "Get Git Status", "Get Git repository status."),
        ),
    ),
    McpCategory(
        "java",
        "JavaTools",
        (
            BuiltinTool("compile_java_file", "Compile Java File", "Compile a Java source file."),
            BuiltinTool(
                "inspect_jar",
                "Inspect JAR File",
                "Inspect contents of a JAR file (list classes and entries).",
            ),
            BuiltinTool("run_jar", "Run JAR File", "Execute a runnable JAR file."),
            BuiltinTool(
                "run_java", "Run Java Code", "Compile single-file Java source code and run it."
            ),
            BuiltinTool(
                "validate_java",
                "Validate Java Syntax",
                "Check Java source code for syntax errors without executing.",
            ),
            BuiltinTool(
                "validate_java_file",
                "Validate Java File",
                "Check Java source file for syntax errors.",
            ),
        ),
    ),
    McpCategory(
        "json",
        "JsonTools",
        (
            BuiltinTool("json_format", "Format JSON", "Format a JSON string with indentation."),
            BuiltinTool(
                "json_query", "Query JSON", "Extract value from JSON by key path (dot notation)."
            ),
        ),
    ),
    McpCategory(
        "mail",
        None,
        (BuiltinTool("send_email", "Send Email", "Send email using SMTP server."),),
    ),
    McpCategory(
        "pdf",
        "PdfTools",
        (
            BuiltinTool(
                "extract_pdf_tables", "Extract PDF Tables", "Extract tables from PDF pages."
            ),
            BuiltinTool(
                "get_pdf_info",
                "Get PDF Information",
                "Get PDF document metadata and page count information.",
            ),
            BuiltinTool("read_pdf", "Read PDF Content", "Read text content from a PDF file."),
            BuiltinTool("read_pdf_page", "Read PDF Page", "Read a specific page from a PDF file."),
            BuiltinTool(
                "search_pdf", "Search in PDF", "Search for text in a PDF and return matching pages."
            ),
        ),
    ),
    McpCategory(
        "service",
        "ServiceTools",
        (
            BuiltinTool(
                "service_restart",
                "Restart Service",
                "Restart a service (docker container or systemd service).",
            ),
        ),
    ),
    McpCategory(
        "text",
        "TextTools",
        (
            BuiltinTool(
                "text_analysis", "Text Analysis", "Count words, lines, and characters in text."
            ),
            BuiltinTool("translate_text", "Translate Text", "Translate text between languages."),
        ),
    ),
    McpCategory(
        "time",
        "TimeTools",
        (
            BuiltinTool(
                "get_current_time", "Get Current Time", "Get current date and time formatted."
            ),
        ),
    ),
    McpCategory(
        "utility",
        "UtilityTools",
        (
            BuiltinTool("decode_base64", "Decode Base64", "Decode base64 string to text."),
            BuiltinTool("encode_base64", "Encode Base64", "Encode text to base64."),
            BuiltinTool("generate_uuid", "Generate UUID", "Generate a random UUID (v4)."),
            BuiltinTool(
                "hash_text", "Hash Text", "Calculate hash (md5, sha1, sha256, sha512) of text."
            ),
        ),
    ),
    McpCategory(
        "web",
        "WebTools",
        (
            BuiltinTool(
                "fetch_webpage",
                "Fetch Webpage Content",
                "Fetch content of a webpage and extract clean text.",
            ),
            BuiltinTool("web_search", "Search the Web", "Search the web using search engine."),
        ),
    ),
)

MCP_CATEGORY_KEYS: Final[tuple[str, ...]] = tuple(c.key for c in MCP_CATEGORIES)

MCP_CATEGORY_BY_KEY: Final[dict[str, McpCategory]] = {c.key: c for c in MCP_CATEGORIES}

# category key -> flow-canvas node ``type``; only categories with a plain
# category node (mail is excluded — it needs a bespoke MailTools + MailConfig
# pair, wired elsewhere).
CATEGORY_NODE_TYPES: Final[dict[str, str]] = {
    c.key: c.node_type for c in MCP_CATEGORIES if c.node_type is not None
}

# category key -> option-source key consumed by component templates.
MCP_CATEGORY_OPTION_SOURCES: Final[tuple[str, ...]] = tuple(
    f"mcp.tools.{key}" for key in MCP_CATEGORY_KEYS
)
