"""
Git Tools Category.
Provides tools for Git repository operations.

Every repo_dir/target_dir argument resolves through resolve_in_workspace
(spec TS-2/TS-3). _resolve_repo_path used to contain an explicit escape
(`if os.path.isabs(repo_dir): return repo_dir`); it is gone. Repository
URLs are restricted to https (ext:: and file:: are command execution, not
transports); every other caller-supplied value (remote name, branch name,
initial branch) is rejected outright if it looks like a command-line
option, since git would otherwise parse it as one rather than as data
(e.g. `git pull --upload-pack='touch pwned' <remote>` runs an arbitrary
command against a local or ssh remote). GIT_HARDENING_ARGS additionally
disables the ext:: and file:: transports and any credential prompt/helper
at the git-process level, as defence in depth beyond the URL check.
"""

import subprocess
from typing import Any, Literal
from urllib.parse import urlparse

from error_contract import GitArgumentError
from localization import t

from ..core.base import BaseToolCategory
from ..core.sandbox import run_capped
from ..core.schema import BoundedLimit, ShortText
from ..core.workspace import (
    WorkspacePath,
    guard_workspace_escape,
    resolve_in_workspace,
    workspace_root,
)
from .response import tool_error_message

ALLOWED_URL_SCHEMES = {"https"}

# git reads these from the environment/command line; pinning them at the
# process level closes the ext:: and file:: transports (arbitrary command
# execution and local file read via a crafted "URL") even if a caller
# somehow supplies one, and stops a hung credential prompt or a stored
# credential helper from ever running.
GIT_HARDENING_ARGS = [
    "-c",
    "protocol.ext.allow=never",
    "-c",
    "protocol.file.allow=never",
    "-c",
    "protocol.git.allow=never",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "credential.helper=",
]


def reject_option_like(*values: str | None) -> None:
    """Reject any value git could parse as a command-line option."""
    for value in values:
        if value and value.startswith("-"):
            raise GitArgumentError(f"Value {value!r} looks like a git option")


def validate_repo_url(url: str) -> None:
    """Raise GitArgumentError unless url is a well-formed https URL."""
    reject_option_like(url)
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        raise GitArgumentError(
            f"Only {sorted(ALLOWED_URL_SCHEMES)} repository URLs are supported, got {parsed.scheme!r}"
        )
    if not parsed.netloc:
        raise GitArgumentError("Repository URL must include a host")


def _git(full_path: str, *args: str) -> list[str]:
    """Build a hardened git invocation scoped to full_path."""
    return ["git", *GIT_HARDENING_ARGS, "-C", full_path, *args]


class GitTools(BaseToolCategory):
    """Git repository management tools."""

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return t(
            "categories.git.description",
            default="Git clone, pull, push, commit, and branch operations",
        )

    @property
    def label(self) -> str:
        return t("categories.git.label", default="Git")

    def register_tools(self, mcp: Any) -> None:
        """Register all Git tools with MCP."""

        @mcp.tool()
        @guard_workspace_escape
        def git_clone(
            repo_url: ShortText,
            target_dir: WorkspacePath | None = None,
            branch: ShortText | None = None,
        ) -> str:
            """
            Clone an https Git repository into the workspace.

            Args:
                repo_url: Repository URL (https only)
                target_dir: Target directory name within the workspace
                    (optional, defaults to the repo name)
                branch: Specific branch to clone (optional)

            Returns:
                Clone result with the path where repository was cloned
            """
            try:
                validate_repo_url(repo_url)
                reject_option_like(branch)
            except GitArgumentError as e:
                return t("git.invalid_argument", error=tool_error_message(e), default=str(e))

            root = workspace_root()

            if not target_dir:
                # Handle URLs like https://github.com/user/repo.git
                repo_name = repo_url.rstrip("/").split("/")[-1]
                if repo_name.endswith(".git"):
                    repo_name = repo_name[:-4]
                target_dir = repo_name

            full_path = resolve_in_workspace(target_dir, root=root)

            if full_path.exists():
                return t("git.directory_already_exists", path=str(full_path))

            cmd = ["git", *GIT_HARDENING_ARGS, "clone", "--single-branch"]
            if branch:
                cmd.extend(["-b", branch])
            cmd.extend(["--", repo_url, str(full_path)])

            try:
                result = run_capped(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    return f"Repository cloned successfully to: {target_dir}"
                return t("git.clone_error", error=result.stderr)
            except subprocess.TimeoutExpired:
                return t("git.clone_timeout")
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.clone_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def git_pull(repo_dir: WorkspacePath, remote: ShortText = "origin", branch: ShortText | None = None) -> str:
            """
            Pull changes from a remote repository.

            Args:
                repo_dir: Local repository directory, relative to the workspace
                remote: Remote name (default: origin)
                branch: Branch name (optional, uses current branch if not specified)

            Returns:
                Pull result
            """
            try:
                reject_option_like(remote, branch)
            except GitArgumentError as e:
                return t("git.invalid_argument", error=tool_error_message(e), default=str(e))

            full_path = resolve_in_workspace(repo_dir, root=workspace_root())

            if not full_path.exists():
                return t("git.repo_not_found", path=str(full_path))

            cmd = _git(str(full_path), "pull", "--", remote)
            if branch:
                cmd.append(branch)

            try:
                result = run_capped(cmd, capture_output=True, text=True, timeout=120)
                return result.stdout + result.stderr
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.pull_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def git_push(repo_dir: WorkspacePath, remote: ShortText = "origin", branch: ShortText | None = None) -> str:
            """
            Push changes to a remote repository.

            Args:
                repo_dir: Local repository directory, relative to the workspace
                remote: Remote name (default: origin)
                branch: Branch name (optional, uses current branch if not specified)

            Returns:
                Push result
            """
            try:
                reject_option_like(remote, branch)
            except GitArgumentError as e:
                return t("git.invalid_argument", error=tool_error_message(e), default=str(e))

            full_path = resolve_in_workspace(repo_dir, root=workspace_root())

            if not full_path.exists():
                return t("git.repo_not_found", path=str(full_path))

            cmd = _git(str(full_path), "push", "--", remote)
            if branch:
                cmd.append(branch)

            try:
                result = run_capped(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0:
                    return "Push successful" + (f"\n{result.stdout}" if result.stdout else "")
                return result.stderr
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.push_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def git_status(repo_dir: WorkspacePath) -> str:
            """
            Get Git repository status.

            Args:
                repo_dir: Local repository directory, relative to the workspace

            Returns:
                Git status output
            """
            full_path = resolve_in_workspace(repo_dir, root=workspace_root())

            if not full_path.exists():
                return t("git.repo_not_found", path=str(full_path))

            try:
                result = run_capped(_git(str(full_path), "status"), capture_output=True, text=True, timeout=30)
                return result.stdout
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.status_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def git_commit(repo_dir: WorkspacePath, message: ShortText, add_all: bool = True) -> str:
            """
            Create a Git commit.

            Args:
                repo_dir: Local repository directory, relative to the workspace
                message: Commit message
                add_all: Stage all changes before committing (default: True)

            Returns:
                Commit result
            """
            full_path = resolve_in_workspace(repo_dir, root=workspace_root())

            if not full_path.exists():
                return t("git.repo_not_found", path=str(full_path))

            try:
                if add_all:
                    run_capped(_git(str(full_path), "add", "-A"), timeout=30)

                result = run_capped(
                    _git(str(full_path), "commit", "-m", message),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                output = result.stdout + result.stderr

                # Detect "Author identity unknown" and provide actionable guidance
                if result.returncode != 0 and "author identity unknown" in output.lower():
                    return t("git.identity_unknown")

                return output
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.commit_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def git_branch(repo_dir: WorkspacePath, branch_name: ShortText | None = None, create: bool = False) -> str:
            """
            List branches or create/switch to a branch.

            Args:
                repo_dir: Local repository directory, relative to the workspace
                branch_name: Branch name (optional, lists branches if not provided)
                create: Create new branch (default: False)

            Returns:
                Branch list or operation result
            """
            try:
                reject_option_like(branch_name)
            except GitArgumentError as e:
                return t("git.invalid_argument", error=tool_error_message(e), default=str(e))

            full_path = resolve_in_workspace(repo_dir, root=workspace_root())

            if not full_path.exists():
                return t("git.repo_not_found", path=str(full_path))

            try:
                if not branch_name:
                    result = run_capped(
                        _git(str(full_path), "branch", "-a"),
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    return result.stdout

                if create:
                    cmd = _git(str(full_path), "checkout", "-b", "--", branch_name)
                else:
                    cmd = _git(str(full_path), "checkout", "--", branch_name)

                result = run_capped(cmd, capture_output=True, text=True, timeout=30)
                return result.stdout + result.stderr
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.branch_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def git_init(repo_dir: WorkspacePath, initial_branch: ShortText = "main") -> str:
            """
            Initialize a new Git repository inside the workspace.

            Args:
                repo_dir: Directory to initialize, relative to the workspace
                initial_branch: Name of the initial branch (default: main)

            Returns:
                Initialization result
            """
            try:
                reject_option_like(initial_branch)
            except GitArgumentError as e:
                return t("git.invalid_argument", error=tool_error_message(e), default=str(e))

            full_path = resolve_in_workspace(repo_dir, root=workspace_root())

            full_path.mkdir(parents=True, exist_ok=True)

            git_dir = full_path / ".git"
            if git_dir.exists():
                return t("git.already_initialized", path=str(full_path))

            try:
                result = run_capped(
                    _git(str(full_path), "init", "-b", initial_branch),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    return f"Initialized empty Git repository in {full_path}"
                return t("git.init_error", error=result.stderr)
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.init_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def git_remote_add(repo_dir: WorkspacePath, remote_url: ShortText, remote_name: ShortText = "origin") -> str:
            """
            Add or update a remote repository (https only).

            Args:
                repo_dir: Local repository directory, relative to the workspace
                remote_url: URL of the remote repository (https only)
                remote_name: Name for the remote (default: origin)

            Returns:
                Operation result
            """
            try:
                validate_repo_url(remote_url)
                reject_option_like(remote_name)
            except GitArgumentError as e:
                return t("git.invalid_argument", error=tool_error_message(e), default=str(e))

            full_path = resolve_in_workspace(repo_dir, root=workspace_root())

            if not full_path.exists():
                return t("git.repo_not_found", path=str(full_path))

            try:
                check_result = run_capped(
                    _git(str(full_path), "remote", "get-url", "--", remote_name),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if check_result.returncode == 0:
                    result = run_capped(
                        _git(str(full_path), "remote", "set-url", "--", remote_name, remote_url),
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        return f"Updated remote '{remote_name}' to: {remote_url}"
                else:
                    result = run_capped(
                        _git(str(full_path), "remote", "add", "--", remote_name, remote_url),
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        return f"Added remote '{remote_name}': {remote_url}"

                return t("git.remote_error", error=result.stderr)
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.remote_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def git_log(repo_dir: WorkspacePath, max_commits: BoundedLimit = 10) -> str:
            """
            Show git commit history.

            Args:
                repo_dir: Local repository directory, relative to the workspace
                max_commits: Maximum number of commits to show (default: 10)

            Returns:
                Commit history
            """
            full_path = resolve_in_workspace(repo_dir, root=workspace_root())

            if not full_path.exists():
                return t("git.repo_not_found", path=str(full_path))

            try:
                result = run_capped(
                    _git(str(full_path), "log", f"-{max_commits}", "--oneline", "--decorate"),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.stdout if result.stdout else "No commits yet"
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.log_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def git_config(
            user_email: ShortText | None = None,
            user_name: ShortText | None = None,
            repo_dir: WorkspacePath | None = None,
            scope: Literal["global", "local"] = "global",
        ) -> str:
            """
            Set or get Git configuration values (user.email, user.name).

            Use this tool when a git commit fails with "Author identity unknown"
            or when the user wants to configure their git identity.

            Args:
                user_email: Email address to set for git commits (optional)
                user_name: Display name to set for git commits (optional)
                repo_dir: Repository directory for local scope, relative to the
                    workspace (optional)
                scope: Configuration scope - 'global' (default) or 'local' (requires repo_dir)

            Returns:
                Configuration result or current configuration values
            """
            try:
                reject_option_like(user_email, user_name)
            except GitArgumentError as e:
                return t("git.invalid_argument", error=tool_error_message(e), default=str(e))

            results = []

            if scope not in ("global", "local"):
                return t("git.invalid_scope", scope=scope)

            scope_flag = f"--{scope}"

            base_cmd = ["git", *GIT_HARDENING_ARGS]
            if scope == "local":
                if not repo_dir:
                    return t("git.repo_dir_required")
                full_path = resolve_in_workspace(repo_dir, root=workspace_root())
                if not full_path.exists():
                    return t("git.repo_not_found", path=str(full_path))
                base_cmd = ["git", *GIT_HARDENING_ARGS, "-C", str(full_path)]

            try:
                if not user_email and not user_name:
                    email_result = run_capped(
                        [*base_cmd, "config", scope_flag, "user.email"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    name_result = run_capped(
                        [*base_cmd, "config", scope_flag, "user.name"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    current_email = email_result.stdout.strip() or "(not set)"
                    current_name = name_result.stdout.strip() or "(not set)"
                    return f"Current git config ({scope}):\n  user.email: {current_email}\n  user.name: {current_name}"

                if user_email:
                    result = run_capped(
                        [*base_cmd, "config", scope_flag, "user.email", "--", user_email],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        results.append(f"Set user.email = {user_email} ({scope})")
                    else:
                        results.append(f"Failed to set user.email: {result.stderr.strip()}")

                if user_name:
                    result = run_capped(
                        [*base_cmd, "config", scope_flag, "user.name", "--", user_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        results.append(f"Set user.name = {user_name} ({scope})")
                    else:
                        results.append(f"Failed to set user.name: {result.stderr.strip()}")

                return "\n".join(results)
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.config_error", error=tool_error_message(e))

        @mcp.tool()
        @guard_workspace_escape
        def git_diff(repo_dir: WorkspacePath, staged: bool = False) -> str:
            """
            Show changes in the working directory or staged changes.

            Args:
                repo_dir: Local repository directory, relative to the workspace
                staged: Show staged changes instead of working directory changes

            Returns:
                Diff output
            """
            full_path = resolve_in_workspace(repo_dir, root=workspace_root())

            if not full_path.exists():
                return t("git.repo_not_found", path=str(full_path))

            try:
                cmd = _git(str(full_path), "diff")
                if staged:
                    cmd.append("--staged")

                result = run_capped(cmd, capture_output=True, text=True, timeout=30)
                return result.stdout if result.stdout else "No changes"
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                return t("git.diff_error", error=tool_error_message(e))
