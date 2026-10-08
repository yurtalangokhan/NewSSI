"""Architecture tests for modularized flow builder components."""

import importlib
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
TESTS_DIR = BASE_DIR / "tests"
FLOW_DIR = SRC_DIR / "agents" / "graphs" / "flow"


def test_flow_package_structure():
    """Verify that src/agents/graphs/flow/ package and all submodules exist."""
    assert FLOW_DIR.is_dir(), "src/agents/graphs/flow directory must exist"
    assert (FLOW_DIR / "__init__.py").exists(), "flow/__init__.py must exist"
    assert (FLOW_DIR / "state.py").exists(), "flow/state.py must exist"
    assert (FLOW_DIR / "message_flow.py").exists(), "flow/message_flow.py must exist"
    assert (FLOW_DIR / "builder.py").exists(), "flow/builder.py must exist"

    nodes_dir = FLOW_DIR / "nodes"
    assert nodes_dir.is_dir(), "flow/nodes directory must exist"
    assert (nodes_dir / "__init__.py").exists(), "flow/nodes/__init__.py must exist"
    assert (nodes_dir / "inputs.py").exists(), "flow/nodes/inputs.py must exist"
    assert (nodes_dir / "retrieval.py").exists(), "flow/nodes/retrieval.py must exist"
    assert (nodes_dir / "web.py").exists(), "flow/nodes/web.py must exist"
    assert (nodes_dir / "routing.py").exists(), "flow/nodes/routing.py must exist"
    assert (nodes_dir / "processing.py").exists(), "flow/nodes/processing.py must exist"


def test_flow_package_exports():
    """Verify that flow package exports key interfaces."""
    flow = importlib.import_module("agents.graphs.flow")
    assert hasattr(flow, "FlowGraphBuilder")
    assert hasattr(flow, "FlowState")
    assert hasattr(flow, "ResolvedResources")
    assert hasattr(flow, "partition_nodes")
    assert hasattr(flow, "resolve_resources")
    assert hasattr(flow, "evaluate_condition")
    assert hasattr(flow, "make_component_tool")


def test_no_legacy_flow_builder_file_or_imports():
    """Verify that monolithic flow_builder.py was removed (no shims) and no file imports from it."""
    assert not (SRC_DIR / "agents" / "graphs" / "flow_builder.py").exists(), (
        "src/agents/graphs/flow_builder.py should not exist (zero shims policy)"
    )

    forbidden = [
        re.compile(r"\bfrom\s+agents\.graphs\.flow_builder\s+import\b"),
        re.compile(r"\bimport\s+agents\.graphs\.flow_builder\b"),
    ]
    violations = []
    for check_dir in [SRC_DIR, TESTS_DIR]:
        for p in check_dir.rglob("*.py"):
            if ".venv" in p.parts or "__pycache__" in p.parts:
                continue
            text = p.read_text(encoding="utf-8")
            for pat in forbidden:
                for line_idx, line in enumerate(text.splitlines(), start=1):
                    if pat.search(line):
                        violations.append(f"{p.relative_to(BASE_DIR)}:{line_idx} - {line.strip()}")
    assert not violations, "Found legacy flow_builder imports:\n" + "\n".join(violations)
