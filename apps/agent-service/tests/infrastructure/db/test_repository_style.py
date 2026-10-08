"""One repository style: ``BaseRepository`` subclasses, no static facades.

Three modules used to expose a *facade* — for personas, datasource mappings and
schedules — a class of ``@staticmethod`` wrappers delegating to the
real repository. So the same table had two call shapes (``PersonaRepository.get(x)`` vs
``PersonaRepository().get(x)``), a second place to look for the query, and no way
for the read/write session guard to see the facade at all (it inspects methods
that use ``self._session``/``self._read_session``, and a staticmethod has no
``self``).

These tests pin the single style so a facade cannot reappear.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[3] / "src"

#: Facade-shaped class names: a "DB", "Manager" or "Facade" class in a repository
#: module is always a wrapper around a real repository, never the repository.
_FACADE_NAME_RE = r"(DB|DBManager|Manager|Facade)$"

#: Repository modules by location, not by name: every directory that holds
#: persistence code today.
_REPOSITORY_DIR_PARTS = ("repositor",)


def _repository_modules() -> list[Path]:
    """Modules in a *repository directory* — not files merely named ``repository``.

    ``service/ollama/repository.py`` is an HTTP adapter for an external service
    and has neither a SQLAlchemy session nor any business being a
    ``BaseRepository`` subclass, so it is deliberately out of scope here.
    """
    modules = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if not any(part.startswith(_REPOSITORY_DIR_PARTS) for part in path.parts[:-1]):
            continue
        if path.name in {"base.py", "__init__.py"}:
            continue
        modules.append(path)
    return modules


def _code_without_docstrings(path: Path) -> list[tuple[int, str]]:
    """``(lineno, line)`` for every line that is code, prose dropped.

    Docstrings and comments legitimately *name* the facades this change removed
    ("the ``PersonaDB`` facade is gone"), so scanning raw text would make the
    documentation of the fix fail the fix. String literals that are not
    docstrings are kept: ``monkeypatch.setattr("…PersonaDB.get", …)`` in a test is
    a real leftover and must be caught.
    """
    source = path.read_text()
    lines = source.splitlines()
    tree = ast.parse(source)

    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_lines.update(range(first.value.lineno, (first.value.end_lineno or 0) + 1))

    out: list[tuple[int, str]] = []
    for i, line in enumerate(lines, 1):
        if i in docstring_lines:
            continue
        if line.lstrip().startswith("#"):
            continue
        out.append((i, line))
    return out


def test_there_are_repository_modules_to_check() -> None:
    """A guard that silently checks nothing is worse than no guard."""
    assert len(_repository_modules()) >= 20


def test_no_repository_module_defines_a_facade_class() -> None:
    import re

    offenders: list[str] = []
    pattern = re.compile(_FACADE_NAME_RE)

    for path in _repository_modules():
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and pattern.search(node.name):
                offenders.append(f"{path.name}:{node.lineno}:{node.name}")

    assert offenders == []


def test_every_repository_class_is_a_base_repository_subclass() -> None:
    """One inheritance style, so the session helpers are always in scope.

    There is no exception: every repository works on this service's own
    database through the SQLAlchemy session.
    """
    offenders: list[str] = []
    for path in _repository_modules():
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not node.name.endswith("Repository"):
                continue
            bases = {ast.unparse(base) for base in node.bases}
            if "BaseRepository" in bases:
                continue
            offenders.append(f"{path.name}:{node.lineno}:{node.name}")

    assert offenders == []


def test_repository_modules_expose_no_staticmethod_crud_wrappers() -> None:
    """CRUD must be instance methods, so ``self._read_session()`` is reachable.

    A staticmethod cannot call ``_read_session``; it can only call *another*
    repository. That is the structural reason facades kept bypassing the session
    split, so the shape itself is what gets asserted.
    """
    crud_prefixes = ("get", "list", "create", "update", "delete", "mark")
    offenders: list[str] = []

    for path in _repository_modules():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for member in node.body:
                if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not isinstance(member, ast.AsyncFunctionDef):
                    continue
                decorators = {ast.unparse(dec) for dec in member.decorator_list}
                if "staticmethod" not in decorators:
                    continue
                if member.name.startswith("_") or not member.name.startswith(crud_prefixes):
                    continue
                offenders.append(f"{path.name}:{member.lineno}:{node.name}.{member.name}")

    assert offenders == []


def _runtime_repository_imports(path: Path) -> list[str]:
    """Repository classes ``path`` imports *outside* a ``TYPE_CHECKING`` block.

    A ``TYPE_CHECKING`` import is a type reference, not an access path: the
    annotation is never evaluated at runtime. Everything else is a real import,
    and a real import is how a second access path starts.
    """
    tree = ast.parse(path.read_text())
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.ImportFrom)
                and sub.module
                and sub.module.startswith("infrastructure.db")
            ):
                for alias in sub.names:
                    if alias.name.endswith("Repository"):
                        offenders.append(f"{path.name}:{sub.lineno}:{alias.name}")
    return offenders


def test_no_service_module_imports_a_repository_at_runtime() -> None:
    """Services obtain a repository from the gateway, never by naming the class.

    Type annotations still work — that is what the ``TYPE_CHECKING`` block is
    for — but a runtime import would mean the query, the session choice and any
    future caching policy again have more than one owner.
    """
    offenders = [
        hit
        for path in sorted((SRC_ROOT / "service").rglob("*.py"))
        for hit in _runtime_repository_imports(path)
    ]

    assert offenders == []


def _gateway_accessors() -> dict[str, str]:
    """``{RepositoryClassName: accessor_name}`` read from the gateway's signatures.

    The accessor's *return annotation* is the source of truth. Deriving the name
    from the class name with a snake_case heuristic cannot split
    ``MCPOAuthSessionRepository`` (``mcp_oauth_session``, not
    ``mcpo_auth_session``), and parsing the import line misses an accessor that
    delegates to a module factory.
    """
    import inspect

    from infrastructure.db import persistence_gateway

    mapping: dict[str, str] = {}
    for name, obj in vars(persistence_gateway).items():
        if not name.endswith("_repository") or name.endswith("_repository_class"):
            continue
        if not inspect.isfunction(obj):
            continue
        annotation = inspect.get_annotations(obj).get("return")
        class_name = (
            annotation if isinstance(annotation, str) else getattr(annotation, "__name__", "")
        )
        if class_name.endswith("Repository"):
            mapping[class_name] = name
    return mapping


def test_the_gateway_has_an_accessor_for_every_repository() -> None:
    """Completeness is what keeps the gateway the *only* entry point.

    A repository with no accessor has to be imported directly by whoever needs
    it, which is the state this change ended.
    """
    from infrastructure.db import repositories

    exported = {
        name
        for name in repositories.__all__
        if name.endswith("Repository") and name != "BaseRepository"
    }
    assert len(exported) >= 20, sorted(exported)

    missing = sorted(name for name in exported if name not in _gateway_accessors())

    assert missing == []


def test_every_gateway_accessor_returns_the_class_it_advertises(monkeypatch) -> None:
    """A stale accessor is worse than a missing one: it silently returns another table."""
    import importlib

    from infrastructure.db import persistence_gateway

    for class_name, accessor_name in sorted(_gateway_accessors().items()):
        instance = getattr(persistence_gateway, accessor_name)()
        expected = getattr(importlib.import_module("infrastructure.db.repositories"), class_name)
        assert isinstance(instance, expected), f"{accessor_name} -> {type(instance).__name__}"


def test_repository_code_lives_in_exactly_one_location() -> None:
    """One package, so "where is the query for table X?" has one answer.

    Three locations existed at once — ``repository/``, ``infrastructure/db/repositories/``
    and ``service/providers/repository.py``. Each new repository picked whichever
    one its author was looking at, and the split is what let a whole second
    style (the facades) grow in the smaller package.
    """
    locations = {
        path.parent.relative_to(SRC_ROOT).as_posix()
        for path in SRC_ROOT.rglob("*.py")
        if any("repositor" in part for part in path.parts[:-1])
    }

    assert locations == {"infrastructure/db/repositories"}


def test_every_persisted_table_has_its_repository_in_that_package() -> None:
    """The three moved modules are reachable from the canonical package.

    The move is only useful if callers can import from the one location; this
    pins the re-exports so a future module cannot be added without them.
    """
    from infrastructure.db import repositories

    for name in (
        "AgentDefinitionRepository",
        "FlowVersionRepository",
        "ProviderRepository",
    ):
        assert hasattr(repositories, name), name


@pytest.mark.parametrize("facade", ["PersonaDB", "ScheduleDBManager"])
def test_the_deleted_facades_are_gone(facade: str) -> None:
    """Named explicitly: these three are the ones this change removed."""
    hits = [
        f"{path.relative_to(SRC_ROOT)}:{lineno}"
        for path in SRC_ROOT.rglob("*.py")
        for lineno, line in _code_without_docstrings(path)
        if facade in line
    ]

    assert hits == []


#: The one service-layer module allowed to name the shared-table repositories.
_STORE_DOOR = "StoreService.py"

#: Threads and assistants are touched from a dozen services; each table gets a
#: single access path so a change to it has a single home.
_SINGLE_DOOR_REPOS = ("ThreadRepository", "AssistantRepository")


@pytest.mark.parametrize("repo_class", _SINGLE_DOOR_REPOS)
def test_the_service_layer_keeps_one_door_per_shared_table(repo_class: str) -> None:
    """``StoreService`` is the only service module that names these classes.

    When every service constructed the repository itself, a change to how those
    tables are reached — a cache, an owner scope, a session split — had a dozen
    places to land, and one of them always got missed (that is exactly how
    ``PlaygroundRetentionService`` ended up pruning threads on its own path).
    """
    offenders = [
        f"{path.name}:{lineno}"
        for path in (SRC_ROOT / "service").glob("*.py")
        if path.name != _STORE_DOOR
        for lineno, line in _code_without_docstrings(path)
        if repo_class in line
    ]

    assert offenders == []


def test_the_store_door_carries_every_operation_its_callers_need() -> None:
    """An incomplete door is what pushes callers back to the repository.

    Retention needs a bulk delete; if ``StoreService`` did not expose it, the
    only way to prune threads would be to import the repository again — so the
    door's completeness is asserted, not just its exclusivity.
    """
    from service.runtime import store_service as StoreService

    assert callable(StoreService.delete_threads_older_than)
    assert callable(StoreService.add_thread)
    assert callable(StoreService.get_thread_from_store)
    assert callable(StoreService.delete_thread_from_store)
