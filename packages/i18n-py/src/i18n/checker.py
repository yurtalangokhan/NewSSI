import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([a-zA-Z0-9_]+)\}(?!\})")


def extract_placeholders(template: str) -> Set[str]:
    """Extract `{name}`-style format placeholders from a translation string."""
    return set(_PLACEHOLDER_RE.findall(template))


def find_placeholder_mismatches(
    en_data: Dict[str, str], tr_data: Dict[str, str], service_name: str
) -> List[str]:
    """Report keys whose interpolation placeholders differ between en and tr."""
    errors: List[str] = []
    for key in sorted(set(en_data) & set(tr_data)):
        en_placeholders = extract_placeholders(en_data[key])
        tr_placeholders = extract_placeholders(tr_data[key])
        if en_placeholders != tr_placeholders:
            missing = en_placeholders - tr_placeholders
            extra = tr_placeholders - en_placeholders
            detail_parts = []
            if missing:
                detail_parts.append(f"missing in tr: {sorted(missing)}")
            if extra:
                detail_parts.append(f"unexpected in tr: {sorted(extra)}")
            errors.append(
                f"[{service_name}] Placeholder mismatch for key '{key}': {'; '.join(detail_parts)}"
            )
    return errors


def find_unused_keys(defined_keys: Set[str], used_keys: Set[str], service_name: str) -> List[str]:
    """Report keys defined in locale files but never referenced by a literal t(...) call."""
    errors: List[str] = []
    for key in sorted(defined_keys - used_keys):
        errors.append(
            f"[{service_name}] Key '{key}' is defined in locales but never referenced in code"
        )
    return errors


def flatten_json(d: dict, parent_key: str = "", sep: str = ".") -> dict[str, str]:
    items: dict[str, str] = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_json(v, new_key, sep=sep))
        else:
            items[new_key] = str(v)
    return items


def scan_service_locales(locales_dir: Path) -> Tuple[Dict[str, Set[str]], List[str]]:
    """Scan locale JSON files in a service and check key parity."""
    errors: List[str] = []
    keys_by_locale: Dict[str, Set[str]] = {}

    en_file = locales_dir / "en.json"
    tr_file = locales_dir / "tr.json"

    if not en_file.exists():
        errors.append(f"Missing locale file: {en_file}")
        return keys_by_locale, errors
    if not tr_file.exists():
        errors.append(f"Missing locale file: {tr_file}")
        return keys_by_locale, errors

    en_data: Dict[str, str] = {}
    tr_data: Dict[str, str] = {}

    try:
        with open(en_file, "r", encoding="utf-8") as f:
            en_data = flatten_json(json.load(f))
            keys_by_locale["en"] = set(en_data.keys())
            # Check empty strings
            for k, v in en_data.items():
                if not v.strip():
                    errors.append(f"Empty translation in {en_file}: '{k}'")
    except Exception as e:
        errors.append(f"Failed to parse {en_file}: {e}")

    try:
        with open(tr_file, "r", encoding="utf-8") as f:
            tr_data = flatten_json(json.load(f))
            keys_by_locale["tr"] = set(tr_data.keys())
            # Check empty strings
            for k, v in tr_data.items():
                if not v.strip():
                    errors.append(f"Empty translation in {tr_file}: '{k}'")
    except Exception as e:
        errors.append(f"Failed to parse {tr_file}: {e}")

    if "en" in keys_by_locale and "tr" in keys_by_locale:
        missing_in_tr = keys_by_locale["en"] - keys_by_locale["tr"]
        missing_in_en = keys_by_locale["tr"] - keys_by_locale["en"]

        for k in missing_in_tr:
            errors.append(
                f"[{locales_dir.parent.name}] Key '{k}' exists in en.json but missing in tr.json"
            )
        for k in missing_in_en:
            errors.append(
                f"[{locales_dir.parent.name}] Key '{k}' exists in tr.json but missing in en.json"
            )

        errors.extend(find_placeholder_mismatches(en_data, tr_data, locales_dir.parent.name))

    return keys_by_locale, errors


def scan_python_code_for_keys(src_dir: Path) -> Set[str]:
    """Scan python source files for calls that resolve a translation key.

    Recognizes the direct `t("key")` / `i18n.t("key")` / `_("key")` calls, as
    well as calls through the project's translated-response wrapper methods
    (e.g. `self._raise_not_found("key")`, `self.error_response("key")`) whose
    key argument is then forwarded internally to `t(...)`.
    """
    found_keys: Set[str] = set()
    call_pattern = re.compile(
        r"(?:\bt|i18n\.t|_"
        r"|_raise_not_found|_raise_bad_request|_raise_unauthorized"
        r"|_raise_forbidden|_raise_conflict|_raise_internal_error"
        r"|error_response"
        r")\(\s*[\"']([a-zA-Z0-9_\-\.]+)[\"']"
    )
    # A translation key used only as a typed default parameter value on one of
    # the project's translated-response wrapper methods (e.g.
    # `def _raise_not_found(self, detail: str = "common.not_found")`) is
    # still reachable code even though no call site names it literally. This
    # is scoped to those specific def names rather than any `str = "a.b"`
    # default, since an arbitrary hostname/filename default is syntactically
    # identical and must not be mistaken for a translation key.
    default_param_pattern = re.compile(
        r"def\s+(?:_raise_not_found|_raise_bad_request|_raise_unauthorized"
        r"|_raise_forbidden|_raise_conflict|_raise_internal_error|error_response)"
        r"\s*\([^)]*\bstr\s*=\s*[\"']([a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-.]+)[\"']",
        re.DOTALL,
    )

    for py_file in src_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts or ".venv" in py_file.parts:
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
            for match in call_pattern.finditer(content):
                key = match.group(1)
                # Ignore short or non-dotted dynamic strings if desired, but keep valid keys
                if "." in key or len(key) > 3:
                    found_keys.add(key)
            for match in default_param_pattern.finditer(content):
                found_keys.add(match.group(1))
        except Exception:
            pass

    found_keys.update(scan_tools_service_metadata_keys(src_dir))
    found_keys.update(scan_agent_service_rag_tool_keys(src_dir))
    return found_keys


def scan_tools_service_metadata_keys(service_dir: Path) -> Set[str]:
    """Find tool name/description keys resolved dynamically by tools-service.

    The tools-service registry builds metadata keys as
    `tools.{category}.{tool}.name` and `tools.{category}.{tool}.description`
    when wrapping FastMCP tools. Those keys are intentionally dynamic, so the
    generic literal-call scanner cannot see them.
    """
    tools_dir = service_dir / "src" / "tools"
    if service_dir.name != "tools-service" or not tools_dir.exists():
        return set()

    found_keys: Set[str] = set()
    category_pattern = re.compile(
        r"def\s+name\s*\([^)]*\)\s*->\s*str\s*:\s*return\s*[\"']([a-zA-Z0-9_]+)[\"']",
        re.MULTILINE,
    )
    tool_pattern = re.compile(
        r"@mcp\.tool\([^)]*\)\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
        re.MULTILINE,
    )

    for py_file in tools_dir.rglob("*_tools.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        category_match = category_pattern.search(content)
        if not category_match:
            continue

        category = category_match.group(1)
        for tool_match in tool_pattern.finditer(content):
            tool_name = tool_match.group(1)
            found_keys.add(f"tools.{category}.{tool_name}.name")
            found_keys.add(f"tools.{category}.{tool_name}.description")

    return found_keys


def scan_agent_service_rag_tool_keys(service_dir: Path) -> Set[str]:
    """Find rag_tool name/description keys resolved dynamically by agent-service.

    ``_rag_tool_metadata`` in persona_controller.py builds keys as
    ``rag_tool.{tool_name}.name`` / ``rag_tool.{tool_name}.description`` for
    tool names appended by ``_extract_rag_tool_names``. Those keys are
    intentionally dynamic, so the generic literal-call scanner cannot see them.
    """
    if service_dir.name != "agent-service":
        return set()

    controller_file = service_dir / "src" / "controller" / "persona_controller.py"
    if not controller_file.exists():
        return set()

    try:
        content = controller_file.read_text(encoding="utf-8")
    except Exception:
        return set()

    tool_name_pattern = re.compile(r"tool_names\.append\(\s*[\"']([a-zA-Z0-9_]+)[\"']\s*\)")
    found_keys: Set[str] = set()
    for tool_name in tool_name_pattern.findall(content):
        found_keys.add(f"rag_tool.{tool_name}.name")
        found_keys.add(f"rag_tool.{tool_name}.description")

    return found_keys


def check_missing_translations(repo_root: Path) -> bool:
    """Run full check across all services in repo_root/apps."""
    apps_dir = repo_root / "apps"
    all_passed = True
    total_errors: List[str] = []

    services = ["agent-service", "rag-service", "tools-service", "user-service"]

    for service_name in services:
        service_dir = apps_dir / service_name
        locales_dir = service_dir / "locales"

        print(f"\nScanning service: {service_name}...")
        keys_by_locale, errors = scan_service_locales(locales_dir)

        if errors:
            all_passed = False
            total_errors.extend(errors)

        # Scan python code
        used_keys = scan_python_code_for_keys(service_dir)
        defined_keys = keys_by_locale.get("en", set())

        missing_code_keys = [k for k in used_keys if k not in defined_keys and "." in k]
        if missing_code_keys:
            all_passed = False
            for mk in missing_code_keys:
                err = f"[{service_name}] Key '{mk}' used in Python code but not defined in locales"
                total_errors.append(err)

        unused_errors = find_unused_keys(defined_keys, used_keys, service_name)
        if unused_errors:
            all_passed = False
            total_errors.extend(unused_errors)

        if not errors and not missing_code_keys and not unused_errors:
            print(f"  ✓ {service_name} passed all i18n checks ({len(defined_keys)} keys).")

    if not all_passed:
        print("\n❌ i18n missing translations check failed!")
        for err in total_errors:
            print(f"  - {err}")
        return False

    print("\n✅ All backend services passed i18n translation checks!")
    return True


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[4]
    success = check_missing_translations(root)
    sys.exit(0 if success else 1)
