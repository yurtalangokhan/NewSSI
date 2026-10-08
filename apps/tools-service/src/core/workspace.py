"""Single workspace boundary for every filesystem-touching tool.

Every tool that accepts a caller-supplied path must route it through
``resolve_in_workspace``. The check is intentionally implemented once: a
per-tool copy is how boundaries drift apart (see spec TS-2 — file_tools.py
never imported WORKSPACE_DIR at all, and git_tools.py's own copy of this
check explicitly returned an absolute path unchecked).
"""

from __future__ import annotations

from functools import wraps
import hashlib
import inspect
import os
from pathlib import Path
import re
from typing import Annotated, Any

from config_manager import env
from error_contract import WorkspaceEscapeError
from localization import t
from pydantic import Field

from .trusted_context import get_current_trusted_context

# Rejects a leading '/' (absolute path) and NUL bytes at the schema layer,
# so the model cannot even express the most obvious escape. This is a
# coarse first line of defence only, not the boundary itself: pydantic-core
# compiles Field patterns with Rust's `regex` crate, which does not support
# look-around, so a full "no '..' as any path component" pattern cannot be
# expressed here. That check — together with symlink resolution, which no
# regex on the raw string can do at all — is resolve_in_workspace()'s job,
# and every tool using this type still calls it.
WorkspacePath = Annotated[
    str,
    Field(
        min_length=1,
        max_length=512,
        pattern=r"^[^/\x00][^\x00]*$",
        description=(
            "Path relative to the workspace root. Absolute paths are "
            "rejected here; '..' traversal and symlink escapes are "
            "rejected by resolve_in_workspace()."
        ),
    ),
]


# A path segment is kept verbatim only when it is already unmistakably safe:
# no separators, no traversal, no leading dot, bounded length. Anything else
# is hashed rather than rewritten, because rewriting collapses distinct
# identities together ("../a" and "..a" would both become "a") and a
# collision here means two users sharing a workspace.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: Used when no tenant is known, so the layout stays a fixed
#: ``<base>/<tenant>/<principal>`` two levels deep for every caller.
NO_TENANT_SEGMENT = "_"

#: Callers this service cannot identify at all (no trusted context, no access
#: token -- in practice only direct in-process calls, since the MCP transport
#: authenticates every request) share this one bucket.
SHARED_SEGMENT = "_shared"


def workspace_base_dir() -> Path:
    """The configured WORKSPACE_DIR: the parent of every per-caller root."""
    return Path(env.WORKSPACE_DIR)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()[:32]


def _path_segment(raw: str | None, *, always_hash: bool = False) -> str | None:
    """Return a safe directory name for ``raw``, or None if there is no value."""
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if always_hash or not _SAFE_SEGMENT.match(value):
        return _digest(value)
    return value


def _current_access_token() -> Any | None:
    """The verified token of the current MCP request, if there is one.

    Wrapped so the workspace layer keeps working off-transport (direct calls
    in tests, background work) where there is no request to read.
    """
    try:
        from fastmcp.server.dependencies import get_access_token

        return get_access_token()
    except Exception:
        return None


def workspace_identity() -> tuple[str, str]:
    """Return the ``(tenant, principal)`` segments for the current caller.

    Preference order matters. The trusted context is the only source that
    names the *end user* a call is being made for -- agent-service sets it,
    and only a caller holding the internal service token can (see
    trusted_middleware). The access token identifies the *connection*, which
    for a direct Keycloak client is that user and for a machine caller is the
    machine; it is the right answer when there is no delegated user, and it
    is always hashed because on the API-key tier ``client_id`` is the API key
    itself and must not become a directory name.
    """
    context = get_current_trusted_context()
    if context is not None:
        principal = _path_segment(context.user_id)
        if principal:
            return _path_segment(context.tenant_id) or NO_TENANT_SEGMENT, principal

    token = _current_access_token()
    client_id = getattr(token, "client_id", None) if token is not None else None
    principal = _path_segment(client_id, always_hash=True)
    if principal:
        return NO_TENANT_SEGMENT, f"tok-{principal}"

    return NO_TENANT_SEGMENT, SHARED_SEGMENT


def workspace_root() -> Path:
    """The current caller's own workspace, created if it does not exist.

    Creating it here rather than in each tool is deliberate: this is the one
    function every filesystem-touching tool already goes through for its
    root, including command_tools, which hands it to run_sandboxed as the
    subprocess cwd and therefore needs it to exist on disk.
    """
    tenant, principal = workspace_identity()
    root = workspace_base_dir() / tenant / principal
    root.mkdir(parents=True, exist_ok=True)
    # mkdir's mode is masked by umask, so set it explicitly. Same-uid
    # processes are not kept out by this (every tool runs as uid 10001);
    # containment is what resolve_in_workspace enforces. This only keeps
    # other uids on the host out of a user's files.
    os.chmod(root, 0o700)
    return root


def resolve_in_workspace(value: str, *, root: Path | None = None) -> Path:
    """Resolve `value` beneath `root`, rejecting every escape.

    Rejects: absolute paths, '..' traversal, symlinks pointing outside the
    root, and NUL bytes. Symlink resolution happens before the containment
    check (via Path.resolve()), so a symlink inside the workspace that
    points outside it is caught, not just a textual '..'.
    """
    base = (root if root is not None else workspace_root()).resolve()

    if "\x00" in value:
        raise WorkspaceEscapeError("Path contains a NUL byte")
    if os.path.isabs(value):
        raise WorkspaceEscapeError("Absolute paths are not allowed")

    candidate = (base / value).resolve(strict=False)
    if candidate != base and not candidate.is_relative_to(base):
        raise WorkspaceEscapeError("Path escapes the workspace")
    return candidate


def guard_workspace_escape(fn):
    """Turn a WorkspaceEscapeError raised anywhere in fn into the same kind
    of translated error string every other failure in a tool module
    returns, rather than letting a raw exception surface to the MCP
    client. Every tool using this decorator follows the same contract:
    always return a str.

    Shared by every tool module that touches the filesystem (file, code,
    git, java, pdf) instead of each defining its own copy. Wraps both sync
    and async tools: calling an ``async def`` only builds its coroutine,
    it does not run the body, so a plain (sync) try/except here would
    never observe an exception raised inside an async fn — it has to
    await the coroutine from inside its own try block instead.
    """

    if inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def async_wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except WorkspaceEscapeError as e:
                return t("workspace.path_escape_error", error=str(e))

        return async_wrapper

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except WorkspaceEscapeError as e:
            return t("workspace.path_escape_error", error=str(e))

    return wrapper
