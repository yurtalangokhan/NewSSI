"""One WORKSPACE_DIR shared by every caller is one caller's scratch space.

Every filesystem-touching tool resolves its path argument against
``workspace_root()``. That root used to be the bare ``WORKSPACE_DIR`` for
everyone, so "contained inside the workspace" meant contained inside a
single directory shared by every user of the platform: whatever one user
wrote -- a cloned private repo, a generated report, an extracted archive --
the next user could read, overwrite or delete by simply guessing a
filename, with no traversal or escape involved at all. Spec TS-2 closed the
escape; this closes the sharing.

The root is now derived per principal, so containment means contained in
*your own* subtree. The identity comes from the trusted context when
agent-service is calling on a user's behalf, and otherwise from the
verified access token of the direct MCP connection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.core.trusted import TrustedToolContext
from src.core.trusted_context import set_current_trusted_context
from src.core.workspace import resolve_in_workspace, workspace_root


@pytest.fixture(autouse=True)
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from src.core import workspace as workspace_module

    base = tmp_path / "workspace"
    base.mkdir()
    monkeypatch.setattr(workspace_module, "workspace_base_dir", lambda: base)
    set_current_trusted_context(None)
    try:
        yield base
    finally:
        set_current_trusted_context(None)


def _as_user(user_id: str | None, tenant_id: str | None = None) -> None:
    set_current_trusted_context(
        TrustedToolContext(user_id=user_id, tenant_id=tenant_id) if user_id else None
    )


def test_two_users_get_different_roots(workspace_dir: Path) -> None:
    _as_user("alice")
    alice = workspace_root()
    _as_user("bob")
    bob = workspace_root()

    assert alice != bob
    assert alice.is_relative_to(workspace_dir)
    assert bob.is_relative_to(workspace_dir)


def test_the_same_user_gets_a_stable_root(workspace_dir: Path) -> None:
    _as_user("alice")
    first = workspace_root()
    _as_user("bob")
    workspace_root()
    _as_user("alice")

    assert workspace_root() == first


def test_the_same_user_id_in_two_tenants_is_two_workspaces(workspace_dir: Path) -> None:
    _as_user("alice", "tenant-a")
    first = workspace_root()
    _as_user("alice", "tenant-b")

    assert workspace_root() != first


def test_the_root_exists_and_is_private(workspace_dir: Path) -> None:
    _as_user("alice")
    root = workspace_root()

    assert root.is_dir()
    assert root.stat().st_mode & 0o077 == 0, "another uid on the host can read this workspace"


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc",
        "..",
        ".",
        "/etc/passwd",
        "a/b",
        "alice\x00",
        "\\..\\..",
        "  ",
    ],
)
def test_a_hostile_identity_cannot_escape_the_workspace(workspace_dir: Path, hostile: str) -> None:
    """user_id arrives in a header; a bug upstream must not become a traversal."""
    _as_user(hostile)
    root = workspace_root()

    assert root.resolve().is_relative_to(workspace_dir.resolve())
    assert root.resolve() != workspace_dir.resolve()


def test_identities_that_differ_only_after_sanitising_stay_separate(workspace_dir: Path) -> None:
    _as_user("../alice")
    first = workspace_root()
    _as_user("../bob")

    assert workspace_root() != first


def test_a_direct_connection_falls_back_to_its_access_token(
    workspace_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from src.core import workspace as workspace_module

    _as_user(None)
    monkeypatch.setattr(
        workspace_module,
        "_current_access_token",
        lambda: SimpleNamespace(client_id="a-real-api-key-value"),
    )
    root = workspace_root()

    assert root.is_relative_to(workspace_dir)
    assert "a-real-api-key-value" not in str(root), (
        "the access token's client_id can be an API key; it must not become a "
        "directory name, a log line or an error message"
    )
    assert hashlib.sha256(b"a-real-api-key-value").hexdigest()[:32] in str(root)


def test_an_unidentified_caller_gets_one_shared_bucket(workspace_dir: Path) -> None:
    _as_user(None)
    first = workspace_root()
    _as_user(None)

    assert workspace_root() == first
    assert first.is_relative_to(workspace_dir)
    assert first != workspace_dir


def test_one_users_file_is_invisible_to_another(workspace_dir: Path) -> None:
    """The property the whole change exists for."""
    _as_user("alice")
    alice_secret = resolve_in_workspace("secret.txt")
    alice_secret.write_text("alice's private notes", encoding="utf-8")

    _as_user("bob")
    bob_view = resolve_in_workspace("secret.txt")

    assert not bob_view.exists()
    assert bob_view != alice_secret


def test_a_user_cannot_reach_into_another_users_workspace(workspace_dir: Path) -> None:
    from src.core.workspace import WorkspaceEscapeError

    _as_user("alice")
    alice_root = workspace_root()

    _as_user("bob")
    bob_root = workspace_root()
    hop = Path("..") / alice_root.name / "secret.txt"

    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace(str(hop))
    assert bob_root != alice_root
