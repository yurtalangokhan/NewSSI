"""git_tools must confine paths to the workspace, restrict repository URLs
to https, and reject option-like values that git would otherwise parse as
flags. Spec TS-3.

_resolve_repo_path used to contain an explicit escape:
    if os.path.isabs(repo_dir): return repo_dir
"""

from pathlib import Path

import pytest

from src.tools import git_tools
from src.tools.git_tools import GitArgumentError, validate_repo_url


class _Recorder:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *a, **k):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def tools(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(git_tools, "workspace_root", lambda: tmp_path)
    recorder = _Recorder()
    git_tools.GitTools().register_tools(recorder)
    return recorder.tools


def _assert_rejected(result: str) -> None:
    lowered = result.lower()
    assert any(
        word in lowered
        for word in (
            "not allowed",
            "are supported",
            "escapes",
            "workspace",
            "looks like a git option",
            "invalid git argument",
            "izin",
            "geçersiz",
        )
    )


# ---------------------------------------------------------------------
# validate_repo_url unit tests
# ---------------------------------------------------------------------


def test_https_url_is_accepted():
    validate_repo_url("https://example.com/org/repo.git")


@pytest.mark.parametrize(
    "url",
    [
        "ext::sh -c touch /tmp/pwn",
        "file:///etc/passwd",
        "git://example.com/repo.git",
        "ssh://git@example.com/repo.git",
        "http://example.com/repo.git",
    ],
)
def test_non_https_schemes_are_rejected(url):
    with pytest.raises(GitArgumentError):
        validate_repo_url(url)


def test_option_like_repo_url_is_rejected():
    with pytest.raises(GitArgumentError):
        validate_repo_url("--upload-pack=touch /tmp/pwn")


def test_url_without_host_is_rejected():
    with pytest.raises(GitArgumentError):
        validate_repo_url("https:///no-host")


# ---------------------------------------------------------------------
# git_clone
# ---------------------------------------------------------------------


def test_clone_rejects_traversal_target(tools):
    _assert_rejected(tools["git_clone"]("https://example.com/a/b.git", target_dir="../etc"))


def test_clone_rejects_absolute_target(tools):
    _assert_rejected(tools["git_clone"]("https://example.com/a/b.git", target_dir="/etc"))


def test_clone_rejects_option_like_branch(tools):
    _assert_rejected(tools["git_clone"]("https://example.com/a/b.git", branch="--upload-pack=x"))


def test_clone_rejects_ext_scheme(tools):
    _assert_rejected(tools["git_clone"]("ext::sh -c touch /tmp/pwn"))


def test_clone_rejects_option_like_repo_url(tools):
    _assert_rejected(tools["git_clone"]("--upload-pack=touch /tmp/pwn"))


# ---------------------------------------------------------------------
# Path confinement shared by every repo_dir-taking tool
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("git_pull", ("/etc",)),
        ("git_push", ("/etc",)),
        ("git_status", ("/etc",)),
        ("git_commit", ("/etc", "message")),
        ("git_branch", ("/etc",)),
        ("git_init", ("/etc",)),
        ("git_remote_add", ("/etc", "https://example.com/a.git")),
        ("git_log", ("/etc",)),
        ("git_diff", ("/etc",)),
    ],
)
def test_tool_rejects_absolute_repo_dir(tools, tool_name, args):
    _assert_rejected(tools[tool_name](*args))


@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("git_pull", ("../../etc",)),
        ("git_push", ("../../etc",)),
        ("git_commit", ("../../etc", "message")),
    ],
)
def test_tool_rejects_traversal_repo_dir(tools, tool_name, args):
    _assert_rejected(tools[tool_name](*args))


# ---------------------------------------------------------------------
# Option-injection guards on non-path arguments
# ---------------------------------------------------------------------


def test_pull_rejects_option_like_remote(tools, tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    _assert_rejected(tools["git_pull"]("repo", remote="--upload-pack=x"))


def test_pull_rejects_option_like_branch(tools, tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    _assert_rejected(tools["git_pull"]("repo", branch="--force"))


def test_push_rejects_option_like_remote(tools, tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    _assert_rejected(tools["git_push"]("repo", remote="--upload-pack=x"))


def test_remote_add_rejects_option_like_remote_name(tools, tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    _assert_rejected(
        tools["git_remote_add"]("repo", "https://example.com/a.git", remote_name="--force")
    )


def test_remote_add_rejects_non_https_remote_url(tools, tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    _assert_rejected(tools["git_remote_add"]("repo", "ext::sh -c id"))


def test_branch_rejects_option_like_branch_name(tools, tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    _assert_rejected(tools["git_branch"]("repo", branch_name="--force"))


def test_init_rejects_option_like_initial_branch(tools, tmp_path):
    _assert_rejected(tools["git_init"]("repo", initial_branch="--bare"))


def test_config_rejects_option_like_user_email(tools):
    _assert_rejected(tools["git_config"](user_email="--replace-all"))


# ---------------------------------------------------------------------
# Environment hardening: no credential prompts, no dangerous protocols
# ---------------------------------------------------------------------


def test_git_hardening_args_disable_ext_and_file_protocols():
    args = " ".join(git_tools.GIT_HARDENING_ARGS)
    assert "protocol.ext.allow=never" in args
    assert "protocol.file.allow=never" in args


def test_git_hardening_args_disable_terminal_credential_prompt():
    args = " ".join(git_tools.GIT_HARDENING_ARGS)
    assert "credential.helper=" in args
