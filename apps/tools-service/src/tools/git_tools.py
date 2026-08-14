"""
Git Tools Category.
Provides tools for Git repository operations.
"""

import os
import subprocess
from typing import Any

from i18n import t

from ..core.base import BaseToolCategory
from ..core.settings import optional_env

WORKSPACE_DIR = optional_env("WORKSPACE_DIR", "/workspace")


def _resolve_repo_path(repo_dir: str) -> str:
    """Resolve repository path relative to workspace."""
    if os.path.isabs(repo_dir):
        return repo_dir
    return os.path.join(WORKSPACE_DIR, repo_dir)


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
        def git_clone(
            repo_url: str, target_dir: str | None = None, branch: str | None = None
        ) -> str:
            """
            Clone a Git repository to the workspace directory.

            Args:
                repo_url: Repository URL (HTTPS or SSH)
                target_dir: Target directory name within workspace (optional, defaults to repo name)
                branch: Specific branch to clone (optional)

            Returns:
                Clone result with the path where repository was cloned
            """
            # Extract repo name from URL if target_dir not provided
            if not target_dir:
                # Handle URLs like https://github.com/user/repo.git or git@github.com:user/repo.git
                repo_name = repo_url.rstrip("/").split("/")[-1]
                if repo_name.endswith(".git"):
                    repo_name = repo_name[:-4]
                target_dir = repo_name

            # Ensure target is within workspace
            full_path = os.path.join(WORKSPACE_DIR, target_dir)

            # Check if directory already exists
            if os.path.exists(full_path):
                return t("git.directory_already_exists", path=full_path)

            cmd = ["git", "clone"]

            if branch:
                cmd.extend(["-b", branch])

            cmd.append(repo_url)
            cmd.append(full_path)

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    return f"Repository cloned successfully to: {full_path}"
                return t("git.clone_error", error=result.stderr)
            except subprocess.TimeoutExpired:
                return t("git.clone_timeout")
            except Exception as e:
                return t("git.clone_error", error=str(e))

        @mcp.tool()
        def git_pull(repo_dir: str, remote: str = "origin", branch: str | None = None) -> str:
            """
            Pull changes from remote repository.

            Args:
                repo_dir: Local repository directory (relative to workspace or absolute)
                remote: Remote name (default: origin)
                branch: Branch name (optional, uses current branch if not specified)

            Returns:
                Pull result
            """
            full_path = _resolve_repo_path(repo_dir)

            if not os.path.exists(full_path):
                return t("git.repo_not_found", path=full_path)

            cmd = ["git", "-C", full_path, "pull", remote]
            if branch:
                cmd.append(branch)

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                return result.stdout + result.stderr
            except Exception as e:
                return t("git.pull_error", error=str(e))

        @mcp.tool()
        def git_push(repo_dir: str, remote: str = "origin", branch: str | None = None) -> str:
            """
            Push changes to remote repository.

            Args:
                repo_dir: Local repository directory (relative to workspace or absolute)
                remote: Remote name (default: origin)
                branch: Branch name (optional, uses current branch if not specified)

            Returns:
                Push result
            """
            full_path = _resolve_repo_path(repo_dir)

            if not os.path.exists(full_path):
                return t("git.repo_not_found", path=full_path)

            cmd = ["git", "-C", full_path, "push", remote]
            if branch:
                cmd.append(branch)

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0:
                    return "Push successful" + (f"\n{result.stdout}" if result.stdout else "")
                return result.stderr
            except Exception as e:
                return t("git.push_error", error=str(e))

        @mcp.tool()
        def git_status(repo_dir: str) -> str:
            """
            Get Git repository status.

            Args:
                repo_dir: Local repository directory (relative to workspace or absolute)

            Returns:
                Git status output
            """
            full_path = _resolve_repo_path(repo_dir)

            if not os.path.exists(full_path):
                return t("git.repo_not_found", path=full_path)

            try:
                result = subprocess.run(
                    ["git", "-C", full_path, "status"], capture_output=True, text=True, timeout=30
                )
                return result.stdout
            except Exception as e:
                return t("git.status_error", error=str(e))

        @mcp.tool()
        def git_commit(repo_dir: str, message: str, add_all: bool = True) -> str:
            """
            Create a Git commit.

            Args:
                repo_dir: Local repository directory (relative to workspace or absolute)
                message: Commit message
                add_all: Stage all changes before committing (default: True)

            Returns:
                Commit result
            """
            full_path = _resolve_repo_path(repo_dir)

            if not os.path.exists(full_path):
                return t("git.repo_not_found", path=full_path)

            try:
                if add_all:
                    subprocess.run(["git", "-C", full_path, "add", "-A"], timeout=30)

                result = subprocess.run(
                    ["git", "-C", full_path, "commit", "-m", message],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                output = result.stdout + result.stderr

                # Detect "Author identity unknown" and provide actionable guidance
                if result.returncode != 0 and "author identity unknown" in output.lower():
                    return t("git.identity_unknown")

                return output
            except Exception as e:
                return t("git.commit_error", error=str(e))

        @mcp.tool()
        def git_branch(repo_dir: str, branch_name: str | None = None, create: bool = False) -> str:
            """
            List branches or create/switch to a branch.

            Args:
                repo_dir: Local repository directory (relative to workspace or absolute)
                branch_name: Branch name (optional, lists branches if not provided)
                create: Create new branch (default: False)

            Returns:
                Branch list or operation result
            """
            full_path = _resolve_repo_path(repo_dir)

            if not os.path.exists(full_path):
                return t("git.repo_not_found", path=full_path)

            try:
                if not branch_name:
                    # List branches
                    result = subprocess.run(
                        ["git", "-C", full_path, "branch", "-a"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    return result.stdout

                if create:
                    result = subprocess.run(
                        ["git", "-C", full_path, "checkout", "-b", branch_name],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                else:
                    result = subprocess.run(
                        ["git", "-C", full_path, "checkout", branch_name],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                return result.stdout + result.stderr
            except Exception as e:
                return t("git.branch_error", error=str(e))

        @mcp.tool()
        def git_init(repo_dir: str, initial_branch: str = "main") -> str:
            """
            Initialize a new Git repository.

            Args:
                repo_dir: Directory to initialize as Git repository (relative to workspace or absolute)
                initial_branch: Name of the initial branch (default: main)

            Returns:
                Initialization result
            """
            full_path = _resolve_repo_path(repo_dir)

            # Create directory if it doesn't exist
            if not os.path.exists(full_path):
                os.makedirs(full_path, exist_ok=True)

            # Check if already a git repo
            git_dir = os.path.join(full_path, ".git")
            if os.path.exists(git_dir):
                return t("git.already_initialized", path=full_path)

            try:
                result = subprocess.run(
                    ["git", "-C", full_path, "init", "-b", initial_branch],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    return f"Initialized empty Git repository in {full_path}"
                return t("git.init_error", error=result.stderr)
            except Exception as e:
                return t("git.init_error", error=str(e))

        @mcp.tool()
        def git_remote_add(repo_dir: str, remote_url: str, remote_name: str = "origin") -> str:
            """
            Add a remote repository.

            Args:
                repo_dir: Local repository directory (relative to workspace or absolute)
                remote_url: URL of the remote repository
                remote_name: Name for the remote (default: origin)

            Returns:
                Operation result
            """
            full_path = _resolve_repo_path(repo_dir)

            if not os.path.exists(full_path):
                return t("git.repo_not_found", path=full_path)

            try:
                # Check if remote already exists
                check_result = subprocess.run(
                    ["git", "-C", full_path, "remote", "get-url", remote_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if check_result.returncode == 0:
                    # Remote exists, update it
                    result = subprocess.run(
                        ["git", "-C", full_path, "remote", "set-url", remote_name, remote_url],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        return f"Updated remote '{remote_name}' to: {remote_url}"
                else:
                    # Add new remote
                    result = subprocess.run(
                        ["git", "-C", full_path, "remote", "add", remote_name, remote_url],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        return f"Added remote '{remote_name}': {remote_url}"

                return t("git.remote_error", error=result.stderr)
            except Exception as e:
                return t("git.remote_error", error=str(e))

        @mcp.tool()
        def git_log(repo_dir: str, max_commits: int = 10) -> str:
            """
            Show git commit history.

            Args:
                repo_dir: Local repository directory (relative to workspace or absolute)
                max_commits: Maximum number of commits to show (default: 10)

            Returns:
                Commit history
            """
            full_path = _resolve_repo_path(repo_dir)

            if not os.path.exists(full_path):
                return t("git.repo_not_found", path=full_path)

            try:
                result = subprocess.run(
                    ["git", "-C", full_path, "log", f"-{max_commits}", "--oneline", "--decorate"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.stdout if result.stdout else "No commits yet"
            except Exception as e:
                return t("git.log_error", error=str(e))

        @mcp.tool()
        def git_config(
            user_email: str | None = None,
            user_name: str | None = None,
            repo_dir: str | None = None,
            scope: str = "global",
        ) -> str:
            """
            Set or get Git configuration values (user.email, user.name).

            Use this tool when a git commit fails with "Author identity unknown"
            or when the user wants to configure their git identity.

            Args:
                user_email: Email address to set for git commits (optional)
                user_name: Display name to set for git commits (optional)
                repo_dir: Repository directory for local scope (optional, relative to workspace or absolute)
                scope: Configuration scope - 'global' (default) or 'local' (requires repo_dir)

            Returns:
                Configuration result or current configuration values
            """
            results = []

            if scope not in ("global", "local"):
                return t("git.invalid_scope", scope=scope)

            scope_flag = f"--{scope}"

            # For local scope, we need a repo directory
            base_cmd = ["git"]
            if scope == "local":
                if not repo_dir:
                    return t("git.repo_dir_required")
                full_path = _resolve_repo_path(repo_dir)
                if not os.path.exists(full_path):
                    return t("git.repo_not_found", path=full_path)
                base_cmd = ["git", "-C", full_path]

            try:
                # If no values provided, show current config
                if not user_email and not user_name:
                    email_result = subprocess.run(
                        base_cmd + ["config", scope_flag, "user.email"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    name_result = subprocess.run(
                        base_cmd + ["config", scope_flag, "user.name"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    current_email = email_result.stdout.strip() or "(not set)"
                    current_name = name_result.stdout.strip() or "(not set)"
                    return f"Current git config ({scope}):\n  user.email: {current_email}\n  user.name: {current_name}"

                if user_email:
                    result = subprocess.run(
                        base_cmd + ["config", scope_flag, "user.email", user_email],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        results.append(f"Set user.email = {user_email} ({scope})")
                    else:
                        results.append(f"Failed to set user.email: {result.stderr.strip()}")

                if user_name:
                    result = subprocess.run(
                        base_cmd + ["config", scope_flag, "user.name", user_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        results.append(f"Set user.name = {user_name} ({scope})")
                    else:
                        results.append(f"Failed to set user.name: {result.stderr.strip()}")

                return "\n".join(results)
            except Exception as e:
                return t("git.config_error", error=str(e))

        @mcp.tool()
        def git_diff(repo_dir: str, staged: bool = False) -> str:
            """
            Show changes in the working directory or staged changes.

            Args:
                repo_dir: Local repository directory (relative to workspace or absolute)
                staged: Show staged changes instead of working directory changes

            Returns:
                Diff output
            """
            full_path = _resolve_repo_path(repo_dir)

            if not os.path.exists(full_path):
                return t("git.repo_not_found", path=full_path)

            try:
                cmd = ["git", "-C", full_path, "diff"]
                if staged:
                    cmd.append("--staged")

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return result.stdout if result.stdout else "No changes"
            except Exception as e:
                return t("git.diff_error", error=str(e))
