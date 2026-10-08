"""Reads must not pay a write transaction.

``BaseRepository._session()`` commits on exit. Every read path used it, so a
SELECT was wrapped in BEGIN/COMMIT and the connection could not be returned to
the pool until that round trip finished — on top of needlessly making a reader
participate in the write path.

``_read_session()`` wraps a read in a plain (non-committing) transaction: the
statements still run in one consistent snapshot, and there is no COMMIT.
"""

from __future__ import annotations

import pytest

from infrastructure.db.repositories.base import BaseRepository


class _RecordingSession:
    """Minimal AsyncSession stand-in that records transaction bookkeeping."""

    def __init__(self, *, connection_error: Exception | None = None) -> None:
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0
        self.entered = 0
        self.connection_calls: list[dict] = []
        self._connection_error = connection_error

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, *exc_info):
        self.closed += 1
        return False

    async def connection(self, **kwargs):
        self.connection_calls.append(kwargs)
        if self._connection_error is not None:
            raise self._connection_error
        return self

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1


def _patch_factory(monkeypatch, *, connection_error: Exception | None = None) -> _RecordingSession:
    import infrastructure.db.repositories.base as base_module

    session = _RecordingSession(connection_error=connection_error)
    monkeypatch.setattr(base_module, "get_session_factory", lambda: (lambda: session))
    return session


@pytest.mark.asyncio
async def test_read_session_does_not_commit(monkeypatch) -> None:
    session = _patch_factory(monkeypatch)

    async with BaseRepository()._read_session() as yielded:
        assert yielded is session

    assert session.committed == 0
    assert session.rolled_back == 0
    assert session.closed == 1, "the session must still be released"


@pytest.mark.asyncio
async def test_read_session_asks_for_an_autocommit_connection(monkeypatch) -> None:
    """AUTOCOMMIT is what removes BEGIN/COMMIT, not merely "not committing".

    Leaving the session to open an implicit transaction and then skipping the
    COMMIT costs a ROLLBACK on pool return instead — same round trips, no gain.
    """
    session = _patch_factory(monkeypatch)

    async with BaseRepository()._read_session():
        pass

    assert session.connection_calls == [{"execution_options": {"isolation_level": "AUTOCOMMIT"}}]


@pytest.mark.asyncio
async def test_read_session_degrades_when_the_dialect_rejects_autocommit(monkeypatch) -> None:
    """A driver without AUTOCOMMIT must not break every read.

    It falls back to a plain session — still without a COMMIT, so the read
    stays correct, it just keeps the extra round trip.
    """
    from sqlalchemy.exc import ArgumentError

    session = _patch_factory(monkeypatch, connection_error=ArgumentError("nope"))

    async with BaseRepository()._read_session() as yielded:
        assert yielded is session

    assert session.committed == 0
    assert session.closed == 1


@pytest.mark.asyncio
async def test_read_session_is_usable_after_a_rejected_autocommit(monkeypatch) -> None:
    """The fallback must leave a session the caller can still execute on."""
    from sqlalchemy.exc import ArgumentError

    session = _patch_factory(monkeypatch, connection_error=ArgumentError("nope"))
    executed = []

    async with BaseRepository()._read_session() as yielded:
        executed.append(yielded is session)

    assert executed == [True]


@pytest.mark.asyncio
async def test_write_session_commits(monkeypatch) -> None:
    """The write path keeps its old behaviour, byte for byte."""
    session = _patch_factory(monkeypatch)

    async with BaseRepository()._session():
        pass

    assert session.committed == 1
    assert session.rolled_back == 0


@pytest.mark.asyncio
async def test_write_session_rolls_back_on_error(monkeypatch) -> None:
    session = _patch_factory(monkeypatch)

    with pytest.raises(RuntimeError):
        async with BaseRepository()._session():
            raise RuntimeError("boom")

    assert session.committed == 0
    assert session.rolled_back == 1


@pytest.mark.asyncio
async def test_read_session_propagates_errors_without_committing(monkeypatch) -> None:
    session = _patch_factory(monkeypatch)

    with pytest.raises(RuntimeError):
        async with BaseRepository()._read_session():
            raise RuntimeError("boom")

    assert session.committed == 0
    assert session.closed == 1


@pytest.mark.asyncio
async def test_read_session_releases_the_connection_even_on_error(monkeypatch) -> None:
    """A failing read must not pin a pool connection."""
    session = _patch_factory(monkeypatch)

    with pytest.raises(ValueError):
        async with BaseRepository()._read_session():
            raise ValueError("bad query")

    assert session.closed == 1


def test_read_only_repository_methods_use_the_read_session() -> None:
    """Every SELECT-only repository method must be on ``_read_session``.

    A new read method that reaches for ``_session()`` silently reintroduces the
    COMMIT round trip, so this asserts the split rather than trusting review.
    """
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[3] / "src"
    offenders: list[str] = []

    for path in sorted(src_root.rglob("*.py")):
        # Every repository module, whichever directory it lives in
        # (`infrastructure/db/repositories/`, `repository/`, `domain/*/repository.py`).
        if not any(part.startswith("repositor") for part in path.parts):
            continue
        if path.name in {"base.py", "__init__.py"}:
            continue
        offenders.extend(_select_only_methods_using_write_session(path))

    assert offenders == []


def test_no_mutating_method_uses_the_read_session() -> None:
    """The mirror invariant: a write must never run outside a transaction.

    On the AUTOCOMMIT read session a write would be its own transaction — a
    partial write on failure, with no rollback. This is the failure mode that
    would make the read-session change dangerous, so it is asserted, not
    reviewed.
    """
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[3] / "src"
    offenders: list[str] = []

    for path in sorted(src_root.rglob("*.py")):
        if not any(part.startswith("repositor") for part in path.parts):
            continue
        if path.name in {"base.py", "__init__.py"}:
            continue
        offenders.extend(_mutating_methods_using_read_session(path))

    assert offenders == []


def _mutating_methods_using_read_session(path) -> list[str]:
    import ast

    tree = ast.parse(path.read_text())
    found: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls = {
            ast.unparse(call.func)
            for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
        }
        if "self._read_session" not in calls:
            continue
        if _mutates(node):
            found.append(f"{path.name}:{node.lineno}:{node.name}")

    return found


def _select_only_methods_using_write_session(path) -> list[str]:
    import ast

    tree = ast.parse(path.read_text())
    found: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls = {
            ast.unparse(call.func)
            for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
        }
        if "self._session" not in calls:
            continue
        if _mutates(node):
            continue
        found.append(f"{path.name}:{node.lineno}:{node.name}")

    return found


#: SQLAlchemy DML builders, matched as bare names used as a call
#: (``update(Model)``, ``delete(Model)``, ``pg_insert(Model)``). Matched as
#: names rather than attributes so a read method's ``some_dict.update(...)`` is
#: not mistaken for a write.
_WRITE_BUILDERS = {"update", "delete", "insert", "pg_insert"}

#: Session methods that only exist on the write path.
_WRITE_SESSION_METHODS = {
    "add",
    "add_all",
    "flush",
    "refresh",
    "merge",
    "commit",
    "rollback",
    "delete",
}


def _mutates(node) -> bool:
    """True when the method writes: a DML builder, a write-path session call, or
    an attribute assignment on a loaded ORM object.

    That last case matters: ``update_thread_id`` and friends load a row and then
    assign to it (``doc.thread_id = ...``), which SQLAlchemy flushes on COMMIT.
    Nothing in the call graph says "update", so without this check those reads
    would be converted to a non-committing session and silently stop persisting.
    """
    import ast

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name) and func.id in _WRITE_BUILDERS:
                return True
            if isinstance(func, ast.Attribute) and func.attr in _WRITE_SESSION_METHODS:
                return True
        targets: list[ast.expr] = []
        if isinstance(child, ast.Assign):
            targets = list(child.targets)
        elif isinstance(child, (ast.AugAssign, ast.AnnAssign)):
            targets = [child.target]
        if any(isinstance(target, ast.Attribute) for target in targets):
            return True
    return False
