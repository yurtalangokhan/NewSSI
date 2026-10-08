"""Architectural test: Verify Elimination of Hidden Circular Dependencies.

Enterprise Architecture Rule:
Circular dependencies create tightly-coupled code and runtime fragility.
Deferred / in-function imports used solely to avoid startup circular import errors
mask architectural flaws.
The following 5 key clusters must have zero cycles:
1. agent_composition.application.compose_agent <-> agents.implementations.dynamic_agent
2. agents.graphs.strategies.pipeline <-> agents.graphs.strategies.supervisor
3. service.flow_model.migrations <-> service.flow_model.registry
4. service.documents <-> renderers (docx_renderer, pdf_renderer, text_renderer)
5. agents.graphs.flow.nodes.processing <-> agents.graphs.flow.builder
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"


def _get_all_imports(file_path: Path) -> list[tuple[str, int]]:
    """Extract all imports (both module-level and in-function) from a python file."""
    imports: list[tuple[str, int]] = []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except Exception:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.append((a.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports.append((mod, node.lineno))
    return imports


def test_no_cycle_between_agent_composition_and_dynamic_agent():
    """compose_agent must not import dynamic_agent (DIP)."""
    compose_file = SRC_DIR / "agent_composition" / "application" / "compose_agent.py"
    imports = _get_all_imports(compose_file)
    violations = [
        f"{compose_file.name}:{lineno} imports '{mod}'"
        for mod, lineno in imports
        if "dynamic_agent" in mod or mod.startswith("agents.implementations")
    ]
    assert not violations, "compose_agent must not import dynamic_agent:\n" + "\n".join(violations)


def test_no_cycle_between_pipeline_and_supervisor_strategies():
    """Pipeline and Supervisor strategies must not cross-import each other."""
    pipe_file = SRC_DIR / "agents" / "graphs" / "strategies" / "pipeline.py"
    sup_file = SRC_DIR / "agents" / "graphs" / "strategies" / "supervisor.py"

    pipe_imports = _get_all_imports(pipe_file)
    sup_imports = _get_all_imports(sup_file)

    pipe_violations = [
        f"pipeline.py:{lineno} imports supervisor '{mod}'"
        for mod, lineno in pipe_imports
        if "supervisor" in mod and mod != "langgraph_supervisor"
    ]
    sup_violations = [
        f"supervisor.py:{lineno} imports pipeline '{mod}'"
        for mod, lineno in sup_imports
        if "pipeline" in mod
    ]
    all_violations = pipe_violations + sup_violations
    assert not all_violations, (
        "Pipeline and Supervisor strategies must not cross-import:\n" + "\n".join(all_violations)
    )


def test_no_cycle_between_flows_migrations_and_registry():
    """service.flow_model.migrations must not import service.flow_model.registry."""
    mig_file = SRC_DIR / "service" / "flows" / "migrations.py"
    imports = _get_all_imports(mig_file)
    violations = [
        f"migrations.py:{lineno} imports '{mod}'"
        for mod, lineno in imports
        if "service.flow_model.registry" in mod
    ]
    assert not violations, "migrations.py must not import registry.py:\n" + "\n".join(violations)


def test_no_cycle_between_documents_and_renderers():
    """Renderers must not import service.documents package directly (use explicit submodules)."""
    renderers = ["docx_renderer.py", "pdf_renderer.py", "text_renderer.py"]
    violations = []
    for r in renderers:
        r_file = SRC_DIR / "service" / "documents" / r
        imports = _get_all_imports(r_file)
        for mod, lineno in imports:
            if mod == "service.documents":
                violations.append(f"{r}:{lineno} imports 'service.documents' directly")
    assert not violations, (
        "Renderers must not import 'service.documents' package directly (use explicit submodules):\n"
        + "\n".join(violations)
    )


def test_no_cycle_between_processing_nodes_and_flow_builder():
    """agents.graphs.flow.nodes.processing must not import agents.graphs.flow.builder."""
    proc_file = SRC_DIR / "agents" / "graphs" / "flow" / "nodes" / "processing.py"
    imports = _get_all_imports(proc_file)
    violations = [
        f"processing.py:{lineno} imports '{mod}'"
        for mod, lineno in imports
        if "agents.graphs.flow.builder" in mod
    ]
    assert not violations, "nodes/processing.py must not import flow/builder.py:\n" + "\n".join(
        violations
    )


# ---------------------------------------------------------------------------
# Whole-graph guard
# ---------------------------------------------------------------------------
# The named checks above each pin one cycle that was removed by hand, which
# only ever catches that cycle coming back. This one holds the property those
# fixes were after: no import cycle anywhere, counting the in-function imports
# that hide them from a plain module-level analysis.


def _module_name(path: Path) -> str:
    parts = path.relative_to(SRC_DIR).with_suffix("").parts
    name = ".".join(parts)
    return name[: -len(".__init__")] if name.endswith(".__init__") else name


def _build_import_graph() -> dict[str, set[str]]:
    """Map each src module to the src modules it imports, runtime imports only."""
    modules = {_module_name(p): p for p in SRC_DIR.rglob("*.py") if "__pycache__" not in str(p)}
    roots = {name.split(".")[0] for name in modules}

    def resolve(target: str) -> str | None:
        parts = target.split(".")
        while parts:
            candidate = ".".join(parts)
            if candidate in modules:
                return candidate
            parts.pop()
        return None

    graph: dict[str, set[str]] = {name: set() for name in modules}
    for name, path in modules.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:
            continue

        # A TYPE_CHECKING import never executes, so it cannot close a cycle.
        type_checking_lines = {
            sub.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test)
            for sub in ast.walk(node)
            if isinstance(sub, (ast.Import, ast.ImportFrom))
        }

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if node.lineno in type_checking_lines:
                continue
            candidates: list[str] = []
            if isinstance(node, ast.ImportFrom):
                if node.level or not node.module or node.module.split(".")[0] not in roots:
                    continue
                candidates = [f"{node.module}.{a.name}" for a in node.names] + [node.module]
            elif isinstance(node, ast.Import):
                candidates = [a.name for a in node.names if a.name.split(".")[0] in roots]

            for candidate in candidates:
                resolved = resolve(candidate)
                if resolved and resolved != name:
                    graph[name].add(resolved)
                    break
    return graph


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Return every strongly connected component larger than one module."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    counter = [0]
    cycles: list[list[str]] = []

    def strongconnect(start: str) -> None:
        # Iterative Tarjan: this graph is deep enough to blow the interpreter's
        # recursion limit on a recursive one.
        work: list[tuple[str, list[str]]] = [(start, list(graph.get(start, ())))]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on_stack.add(start)

        while work:
            node, successors = work[-1]
            progressed = False
            while successors:
                successor = successors.pop()
                if successor not in index:
                    index[successor] = low[successor] = counter[0]
                    counter[0] += 1
                    stack.append(successor)
                    on_stack.add(successor)
                    work.append((successor, list(graph.get(successor, ()))))
                    progressed = True
                    break
                if successor in on_stack:
                    low[node] = min(low[node], index[successor])
            if progressed:
                continue

            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    cycles.append(sorted(component))

    for node in graph:
        if node not in index:
            strongconnect(node)
    return cycles


def _is_package_and_submodule(component: list[str]) -> bool:
    """A package __init__ re-exporting its own submodule is ordinary Python."""
    first, second = component
    return first.startswith(f"{second}.") or second.startswith(f"{first}.")


def test_src_has_no_import_cycles():
    graph = _build_import_graph()
    cycles = [
        component
        for component in _find_cycles(graph)
        if not (len(component) == 2 and _is_package_and_submodule(component))
    ]
    rendered = "\n".join(
        f"  ({len(component)} modules) " + " -> ".join(component) for component in cycles
    )
    assert not cycles, (
        "Import cycles found. In-function imports keep these from breaking startup, "
        "but the coupling is real — break the loop instead of deferring it:\n" + rendered
    )


def test_the_cycle_detector_actually_detects_a_cycle():
    """Guard the guard: a test that cannot fail protects nothing."""
    planted = {"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}}
    assert _find_cycles(planted) == [["a", "b", "c"]]
