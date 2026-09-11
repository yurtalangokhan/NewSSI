#!/usr/bin/env python3
"""Architecture & code-quality gate for the Agentic AI monorepo.

This is a deterministic, blocking gate that enforces the architecture
principles documented in ``docs/oop-solid-architecture.md`` and
``docs/coding-standards.md`` (section "Architecture & code-quality gate").

It runs on commit and push via ``scripts/quality/check.sh`` (which is wired
into the pre-commit and pre-push git hooks). Committed and pushed code MUST
obey the objective rules below.

Modes
-----
--changed   Only check files in the current diff (default). The file list is
            taken from the QUALITY_FILES env var (set by check.sh) or computed
            from git (staged for the commit hook, upstream range for the push
            hook). This keeps pre-existing hotspots from blocking new work.
            HARD findings FAIL the gate (non-zero exit).
--all       Scan the whole tracked tree. Used by ``make architecture-check``.
            Report-only: never fails (exit 0). Use for trend/baseline reports.

Findings
--------
HARD   Objective architectural violation -> non-zero exit code in --changed.
WARN   Size / complexity heuristic -> reported, never fails the gate.

The script is deliberately stdlib-only so it has no install requirements and
runs fast inside the git hooks.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- Service path matchers -------------------------------------------------
PY_SERVICE_RE = re.compile(
    r"^apps/(agent-service|rag-service|user-service|tools-service)/(src|tests|alembic|migrations)/.*\.py$"
)
WEB_RE = re.compile(r"^apps/web/(src|tests)/.*\.(ts|tsx|js|jsx)$")

# --- Objective (hard) rule patterns ----------------------------------------
# Bare name imports that are almost always HTTP-framework leakage.
HTTP_IMPORT_RE = re.compile(
    r"^\s*(from\s+(fastapi|starlette)(\.\w+)*\s+import|import\s+(fastapi|starlette))\b"
)
# fastapi.status / starlette.status usage in service/domain layers.
HTTP_STATUS_USE_RE = re.compile(r"\b(fastapi|starlette)\.status\b")
# A signature typed with a delivery type in a service/domain module.
DELIVERY_TYPE_PARAM_RE = re.compile(r"\)\s*->\s*.*\b(UploadFile|HTTPException)\b")

# Wrong-layer class placement.
REPOSITORY_CLASS_RE = re.compile(r"^\s*class\s+\w*Repository\b")
CLIENT_CLASS_RE = re.compile(r"^\s*class\s+\w*(Client|Gateway)\b")
CONTROLLER_RE = re.compile(r"/controller/")
# HTTP-framework leakage is forbidden only in the inner layers (service/domain).
LEAKAGE_LAYER_RE = re.compile(r"/(service|domain)/")
# Repositories must not live in the business service or controller folders.
REPOSITORY_BAD_LAYER_RE = re.compile(r"/(service|controller)/")
# Client/Gateway infrastructure classes must not live in service/api folders.
CLIENT_BAD_LAYER_RE = re.compile(r"/(service|api)/")
INTEGRATIONS_RE = re.compile(r"/integrations/")
RAG_DATABASE_RE = re.compile(r"langconnect/database/")

# Dependency inversion (domain must not import concrete outer layers).
# Persistence-layer modules (repository/storage/migrations) legitimately import
# core.db, so they are excluded from this check. `*.base` modules are
# abstractions (Base / BaseRepository), not concrete infrastructure, so they are
# also excluded.
DOMAIN_LAYER_RE = re.compile(r"/(domain|agents)/")
PERSISTENCE_LAYER_RE = re.compile(r"/(repository|storage|migrations)(/|\.py)")
DOMAIN_IMPORTS_OUTER_RE = re.compile(
    r"^\s*from\s+(integrations|core\.db\.(repositories|models)(?!\.base)|repository)(\.\w+)*\s+import\b"
)
RAG_DATABASE_IMPORTS_SERVICES_RE = re.compile(
    r"^\s*from\s+langconnect\.services(\.\w+)*\s+import\b"
)

# Banned bucket module names (only the truly generic ones; models/schemas are
# conventional and allowed). Shims with a removal note are exempt.
BANNED_BUCKET_RE = re.compile(r"(^|/)(utils|Utils|Helpers|helpers)(\.py)?$")

# Keycloak admin API usage is owned by user-service only. Other services may
# verify tokens (JWKS/issuer) but must not call the Keycloak admin REST API or
# instantiate an admin client. Documented compatibility shims are exempt.
KEYCLOAK_ADMIN_API_RE = re.compile(r"/admin/realms/")
KEYCLOAK_ADMIN_CLIENT_RE = re.compile(r"\bKeycloakAdmin\b")

# --- Web (TypeScript/React) hard rules ------------------------------------
RAW_UI_PRIMITIVE_RE = re.compile(
    r"<\s*(p|h[1-6]|input|textarea|button|img)\b(\s|>|/)"
)
# The design system itself has to reach for the primitives it wraps: these are
# the modules feature code is told to use instead ("use @/refresh-components or
# @opal"), plus the layout/`components/ui` primitive libraries they build on.
WEB_PRIMITIVE_LIB_RE = re.compile(
    r"^apps/web/src/(refresh-components/|components/ui/|layouts/[\w-]*layouts\.tsx$)"
)
# A primitive named in a doc comment is documentation, not markup: JSDoc usage
# examples and prose like "a plain `<input>`" are not violations.
COMMENT_LINE_RE = re.compile(r"^\s*(//|/\*|\*|\{/\*)")
BANNED_ICON_IMPORT_RE = re.compile(
    r"^\s*import\s+.*\b(from\s+['\"](lucide-react|react-icons|@phosphor-icons/react|phosphor-icons)['\"])\b"
)
TEST_FILE_RE = re.compile(r"\.(test|spec)\.(ts|tsx)$|\.stories\.tsx$")

# --- Soft (warn) thresholds ------------------------------------------------
PY_HARD_LOC = 500
WEB_HARD_LOC = 1000
FUNC_LEN_LIMIT = 50
CC_LIMIT = 10

# Simple cyclomatic-complexity counter (decision points).
DECISION_RE = re.compile(
    r"\b(if|elif|for|while|except|with|assert|and|or|case|match)\b"
)
# py_compile-free function-length scanner.
PY_FUNC_DEF_RE = re.compile(r"^\s*(async\s+def|def)\s+\w+\s*\(")
TS_FUNC_DEF_RE = re.compile(
    r"^\s*(export\s+)?(async\s+)?(function|const)\s+\w+|\b\w+\s*:\s*\([^)]*\)\s*=>"
)


def changed_files() -> list[str]:
    """Resolve the file list, mirroring check.sh logic."""
    env = os.environ.get("QUALITY_FILES")
    if env:
        return [f for f in env.splitlines() if f.strip()]
    mode = os.environ.get("QUALITY_MODE", "staged")
    if mode == "all":
        cmd = ["git", "ls-files"]
    elif mode == "push" and (
        subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    ):
        cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR", "@{upstream}...HEAD"]
    elif mode == "push":
        cmd = ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD~1...HEAD"]
    else:
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    try:
        out = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except subprocess.CalledProcessError:
        return []
    return [f for f in out.splitlines() if f.strip()]


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def count_loc(lines: list[str]) -> int:
    return sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("#"))


def py_func_lengths(lines: list[str]) -> list[int]:
    lengths: list[int] = []
    in_func = False
    start_indent = 0
    count = 0
    for ln in lines:
        if PY_FUNC_DEF_RE.match(ln):
            if in_func:
                lengths.append(count)
            in_func = True
            start_indent = len(ln) - len(ln.lstrip())
            count = 1
            continue
        if in_func:
            if ln.strip() == "":
                count += 1
                continue
            indent = len(ln) - len(ln.lstrip())
            if indent <= start_indent and ln.strip():
                lengths.append(count)
                in_func = False
            else:
                count += 1
    if in_func:
        lengths.append(count)
    return lengths


def py_cyclomatic(lines: list[str]) -> int:
    return sum(len(DECISION_RE.findall(ln)) for ln in lines)


def ts_func_lengths(lines: list[str]) -> list[int]:
    lengths: list[int] = []
    in_func = False
    start_indent = 0
    count = 0
    for ln in lines:
        if TS_FUNC_DEF_RE.search(ln):
            if in_func:
                lengths.append(count)
            in_func = True
            start_indent = len(ln) - len(ln.lstrip())
            count = 1
            continue
        if in_func:
            if ln.strip() == "":
                count += 1
                continue
            indent = len(ln) - len(ln.lstrip())
            if indent <= start_indent and ln.strip():
                lengths.append(count)
                in_func = False
            else:
                count += 1
    if in_func:
        lengths.append(count)
    return lengths


def is_shim(path: Path, lines: list[str]) -> bool:
    blob = "\n".join(lines).lower()
    return "compatibility shim" in blob or "removal note" in blob or "deprecated" in blob


def check_python(path: str, lines: list[str], hard_enabled: bool) -> list[tuple[str, str, str]]:
    """Return (severity, location, message) findings for one Python file."""
    findings: list[tuple[str, str, str]] = []

    is_leakage_layer = bool(LEAKAGE_LAYER_RE.search(path))
    is_controller = bool(CONTROLLER_RE.search(path))
    is_domain = bool(DOMAIN_LAYER_RE.search(path))
    is_rag_db = bool(RAG_DATABASE_RE.search(path))
    is_persistence = bool(PERSISTENCE_LAYER_RE.search(path))
    is_test = "/tests/" in path
    is_shim_file = is_shim(Path(path), lines)

    for i, ln in enumerate(lines, 1):
        loc = f"{path}:{i}"

        # Rule 1: HTTP framework leakage in service/domain layers (skip tests).
        if is_leakage_layer and not is_test and HTTP_IMPORT_RE.search(ln):
            findings.append(
                ("HARD", loc, "Layer leakage: service/domain imports HTTP framework (fastapi/starlette).")
            )
        if is_leakage_layer and not is_test and HTTP_STATUS_USE_RE.search(ln):
            findings.append(
                ("HARD", loc, "Layer leakage: fastapi/starlette.status used in service/domain layer.")
            )
        if is_leakage_layer and not is_test and DELIVERY_TYPE_PARAM_RE.search(ln):
            findings.append(
                ("HARD", loc, "Delivery type (UploadFile/HTTPException) on a service/domain signature.")
            )

        # Rule 2: repository class outside repository layer (service/controller only).
        if REPOSITORY_CLASS_RE.search(ln) and REPOSITORY_BAD_LAYER_RE.search(path):
            findings.append(
                ("HARD", loc, "Repository class defined outside the repository layer.")
            )
        # Client/Gateway infrastructure class in service/api (not domain/integrations).
        if (
            CLIENT_CLASS_RE.search(ln)
            and CLIENT_BAD_LAYER_RE.search(path)
            and not is_rag_db
            and not is_domain
            and not INTEGRATIONS_RE.search(path)
        ):
            findings.append(
                ("HARD", loc, "Client/Gateway infrastructure class defined in service/api layer.")
            )

        # Rule 3: dependency inversion (domain imports concrete outer layers).
        # Persistence-layer modules (repository/storage/migrations) are exempt.
        if is_domain and not is_test and not is_persistence and DOMAIN_IMPORTS_OUTER_RE.search(ln):
            findings.append(
                ("HARD", loc, "Dependency direction: domain imports concrete integrations/core.db/repository.")
            )
        if is_rag_db and not is_test and RAG_DATABASE_IMPORTS_SERVICES_RE.search(ln):
            findings.append(
                ("HARD", loc, "Dependency direction: rag database layer imports services.")
            )

        # Rule 5: Keycloak admin API usage outside user-service (skip tests and
        # documented compatibility shims).
        if (
            not path.startswith("apps/user-service/")
            and not is_test
            and not is_shim_file
            and (KEYCLOAK_ADMIN_API_RE.search(ln) or KEYCLOAK_ADMIN_CLIENT_RE.search(ln))
        ):
            findings.append(
                ("HARD", loc, "Keycloak admin API usage outside user-service; resolve identity via user-service.")
            )

    # Rule 4: banned bucket module names (unless shim).
    fname = Path(path).name
    if BANNED_BUCKET_RE.search(path):
        if not is_shim(Path(path), lines) and not is_test:
            findings.append(
                ("HARD", path, f"Generic bucket module name '{fname}' is not allowed (rename to a domain name).")
            )

    # Warnings: size / complexity.
    loc_count = count_loc(lines)
    if loc_count > PY_HARD_LOC:
        findings.append(
            ("WARN", path, f"Module is {loc_count} LOC (threshold {PY_HARD_LOC}); consider splitting.")
        )
    for length in py_func_lengths(lines):
        if length > FUNC_LEN_LIMIT:
            findings.append(
                ("WARN", path, f"Function/method is ~{length} lines (threshold {FUNC_LEN_LIMIT}).")
            )
    cc = py_cyclomatic(lines)
    if cc > CC_LIMIT:
        findings.append(
            ("WARN", path, f"Approx cyclomatic complexity {cc} (threshold {CC_LIMIT}); simplify.")
        )

    if not hard_enabled:
        findings = [("WARN" if s == "HARD" else s, l, m) for s, l, m in findings]
    return findings


def check_web(path: str, lines: list[str], hard_enabled: bool) -> list[tuple[str, str, str]]:
    findings: list[tuple[str, str, str]] = []
    is_test = bool(TEST_FILE_RE.search(path))
    shim = is_shim(Path(path), lines)
    is_primitive_lib = bool(WEB_PRIMITIVE_LIB_RE.search(path))
    for i, ln in enumerate(lines, 1):
        # Rule 6/7: raw UI primitives and banned icons. Skipped for test and
        # snapshot files, for the primitive libraries themselves, and for
        # comment lines.
        if not is_test and not is_primitive_lib and not COMMENT_LINE_RE.match(ln):
            if RAW_UI_PRIMITIVE_RE.search(ln):
                findings.append(
                    ("HARD", f"{path}:{i}", "Raw HTML/UI primitive not allowed; use @/refresh-components or @opal.")
                )
            if BANNED_ICON_IMPORT_RE.search(ln):
                findings.append(
                    ("HARD", f"{path}:{i}", "Banned icon import; use @/icons only.")
                )

    loc_count = count_loc(lines)
    if loc_count > WEB_HARD_LOC and not shim:
        findings.append(
            ("WARN", path, f"Module is {loc_count} LOC (threshold {WEB_HARD_LOC}); consider splitting.")
        )
    for length in ts_func_lengths(lines):
        if length > FUNC_LEN_LIMIT:
            findings.append(
                ("WARN", path, f"Function is ~{length} lines (threshold {FUNC_LEN_LIMIT}).")
            )
    cc = py_cyclomatic(lines)
    if cc > CC_LIMIT:
        findings.append(
            ("WARN", path, f"Approx cyclomatic complexity {cc} (threshold {CC_LIMIT}); simplify.")
        )

    if not hard_enabled:
        findings = [("WARN" if s == "HARD" else s, l, m) for s, l, m in findings]
    return findings


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--changed"
    if mode == "--all":
        os.environ["QUALITY_MODE"] = "all"
    elif mode == "--changed":
        if "QUALITY_MODE" not in os.environ:
            os.environ["QUALITY_MODE"] = os.environ.get("HOOK_MODE", "staged")
    else:
        print(f"Unknown mode: {mode}", file=sys.stderr)
        return 2

    # HARD findings only block in --changed mode.
    hard_enabled = mode == "--changed"

    files = changed_files()
    hard: list[tuple[str, str, str]] = []
    warn: list[tuple[str, str, str]] = []

    for path in files:
        if PY_SERVICE_RE.match(path):
            findings = check_python(path, read_lines(ROOT / path), hard_enabled)
        elif WEB_RE.match(path):
            findings = check_web(path, read_lines(ROOT / path), hard_enabled)
        else:
            continue
        for sev, loc, msg in findings:
            (hard if sev == "HARD" else warn).append((sev, loc, msg))

    print("\n=== Architecture & code-quality gate ===")
    print(f"Mode: {mode}  Files scanned: {len(files)}  HARD enforcement: {hard_enabled}")
    if warn:
        print(f"\nWARN ({len(warn)}) - non-blocking:")
        for sev, loc, msg in warn:
            print(f"  [{sev}] {loc}: {msg}")
    if hard:
        print(f"\nHARD ({len(hard)}) - {'BLOCKING' if hard_enabled else 'report-only (--all)'}:")
        for sev, loc, msg in hard:
            print(f"  [{sev}] {loc}: {msg}")

    if not hard_enabled:
        print("\nArchitecture gate report complete (--all is non-blocking).")
        return 0

    if hard:
        print("\nArchitecture gate FAILED: committed/pushed code violates architecture rules.")
        return 1

    print("\nArchitecture gate PASSED.")
    if warn:
        print(f"({len(warn)} warning(s) reported; see above.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
