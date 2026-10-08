"""Architecture tests ensuring Pydantic DTOs reside in src/schemas and not src/models."""

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
TESTS_DIR = BASE_DIR / "tests"


def test_schemas_directory_exists_and_models_directory_does_not():
    """Verify that src/schemas exists as canonical DTO directory and src/models does not exist."""
    assert (SRC_DIR / "schemas").is_dir(), "src/schemas must exist"
    assert (SRC_DIR / "schemas" / "__init__.py").exists(), "src/schemas/__init__.py must exist"
    assert not (SRC_DIR / "models").exists(), (
        "src/models should not exist (migrated to src/schemas)"
    )
    assert not (TESTS_DIR / "models").exists(), (
        "tests/models should not exist (migrated to tests/schemas)"
    )


def test_no_legacy_models_imports():
    """Verify no file in src/ or tests/ imports from the old models package."""
    forbidden = [
        re.compile(r"\bfrom\s+models\."),
        re.compile(r"\bimport\s+models\."),
        re.compile(r"\bfrom\s+models\s+import\b"),
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
    assert not violations, "Found legacy models imports:\n" + "\n".join(violations)


def test_schemas_exports_key_dtos():
    """Verify that common DTO schemas can be imported from schemas."""
    from schemas.chat import ChatMessage, StreamInput, UserInput
    from schemas.flows import FlowEdge, FlowNode, FlowSpec, FlowVersionResponse
    from schemas.personas import PersonaResponse, PersonaUpsertRequest

    assert ChatMessage is not None
    assert UserInput is not None
    assert StreamInput is not None
    assert PersonaUpsertRequest is not None
    assert PersonaResponse is not None
    assert FlowNode is not None
    assert FlowEdge is not None
    assert FlowSpec is not None
    assert FlowVersionResponse is not None


def test_no_legacy_minimal_backend_artifacts():
    """Verify that legacy minimal_backend files do not exist in schemas or tests."""
    assert not (SRC_DIR / "schemas" / "minimal_backend.py").exists(), (
        "src/schemas/minimal_backend.py should not exist (legacy prototype mock)"
    )
    assert not (TESTS_DIR / "service" / "minimal_backend_app.py").exists(), (
        "tests/service/minimal_backend_app.py should not exist (legacy prototype mock)"
    )
