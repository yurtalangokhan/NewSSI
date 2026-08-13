import json
from pathlib import Path

from i18n.checker import (
    check_missing_translations,
    extract_placeholders,
    find_placeholder_mismatches,
    find_unused_keys,
    scan_python_code_for_keys,
    scan_service_locales,
)


class TestExtractPlaceholders:
    def test_extracts_single_placeholder(self):
        assert extract_placeholders("Hello {name}") == {"name"}

    def test_extracts_multiple_placeholders(self):
        assert extract_placeholders("{greeting}, {name}!") == {"greeting", "name"}

    def test_no_placeholders_returns_empty_set(self):
        assert extract_placeholders("Hello world") == set()

    def test_ignores_doubled_braces_used_for_escaping(self):
        assert extract_placeholders("Use {{literal braces}} here") == set()


class TestFindPlaceholderMismatches:
    def test_no_errors_when_placeholders_match(self):
        en = {"greeting": "Hello {name}"}
        tr = {"greeting": "Merhaba {name}"}
        assert find_placeholder_mismatches(en, tr, "svc") == []

    def test_reports_placeholder_missing_in_translation(self):
        en = {"greeting": "Hello {name}"}
        tr = {"greeting": "Merhaba"}
        errors = find_placeholder_mismatches(en, tr, "svc")
        assert len(errors) == 1
        assert "greeting" in errors[0]
        assert "name" in errors[0]

    def test_reports_extra_placeholder_in_translation(self):
        en = {"greeting": "Hello"}
        tr = {"greeting": "Merhaba {name}"}
        errors = find_placeholder_mismatches(en, tr, "svc")
        assert len(errors) == 1
        assert "greeting" in errors[0]

    def test_skips_keys_missing_from_one_side(self):
        en = {"a": "Hello {x}"}
        tr = {"b": "Merhaba"}
        assert find_placeholder_mismatches(en, tr, "svc") == []


class TestFindUnusedKeys:
    def test_key_defined_but_never_referenced_is_reported(self):
        defined = {"agent.not_found", "agent.deleted"}
        used = {"agent.deleted"}
        errors = find_unused_keys(defined, used, "svc")
        assert len(errors) == 1
        assert "agent.not_found" in errors[0]

    def test_no_errors_when_all_keys_used(self):
        defined = {"agent.not_found"}
        used = {"agent.not_found"}
        assert find_unused_keys(defined, used, "svc") == []


class TestScanPythonCodeForKeysStillWorks:
    def test_finds_literal_t_calls(self, tmp_path: Path):
        (tmp_path / "route.py").write_text(
            'raise Exception(t("agent.not_found"))', encoding="utf-8"
        )
        assert scan_python_code_for_keys(tmp_path) == {"agent.not_found"}

    def test_finds_keys_passed_through_raise_helper_wrappers(self, tmp_path: Path):
        (tmp_path / "controller.py").write_text(
            'self._raise_not_found("role.not_found", name=name)', encoding="utf-8"
        )
        assert scan_python_code_for_keys(tmp_path) == {"role.not_found"}

    def test_finds_keys_passed_through_error_response_wrapper(self, tmp_path: Path):
        (tmp_path / "tool.py").write_text(
            'return self.error_response("pdf.file_not_found", file_path=file_path)',
            encoding="utf-8",
        )
        assert scan_python_code_for_keys(tmp_path) == {"pdf.file_not_found"}

    def test_finds_keys_used_as_function_default_parameter_values(self, tmp_path: Path):
        (tmp_path / "base.py").write_text(
            'def _raise_not_found(self, detail: str = "common.not_found"):\n'
            "    raise HTTPException(status_code=404, detail=t(detail))\n",
            encoding="utf-8",
        )
        assert scan_python_code_for_keys(tmp_path) == {"common.not_found"}

    def test_does_not_mistake_unrelated_dotted_string_assignments_for_keys(self, tmp_path: Path):
        (tmp_path / "settings.py").write_text(
            'version = "1.0.0"\n'
            'filename = "report.txt"\n'
            'CONFIG = {"model": "llama-3.3-70b"}\n'
            "def connect(host: str = \"smtp.example.com\"): ...\n"
            'call(model="gemini-2.5-pro")\n',
            encoding="utf-8",
        )
        assert scan_python_code_for_keys(tmp_path) == set()


class TestScanServiceLocalesStillWorks:
    def test_flags_missing_key_in_tr(self, tmp_path: Path):
        locales = tmp_path / "locales"
        locales.mkdir()
        (locales / "en.json").write_text(json.dumps({"a": "A"}), encoding="utf-8")
        (locales / "tr.json").write_text(json.dumps({}), encoding="utf-8")
        _, errors = scan_service_locales(locales)
        assert any("missing in tr.json" in e for e in errors)


class TestCheckMissingTranslationsCatchesDeadKeys:
    def _make_service(self, apps_dir: Path, name: str, en: dict, tr: dict, code: str) -> None:
        service_dir = apps_dir / name
        locales = service_dir / "locales"
        locales.mkdir(parents=True)
        (locales / "en.json").write_text(json.dumps(en), encoding="utf-8")
        (locales / "tr.json").write_text(json.dumps(tr), encoding="utf-8")
        (service_dir / "main.py").write_text(code, encoding="utf-8")

    def test_fails_when_locale_key_is_never_referenced_in_code(self, tmp_path: Path):
        apps_dir = tmp_path / "apps"
        for name in ["agent-service", "rag-service", "tools-service", "user-service"]:
            self._make_service(
                apps_dir,
                name,
                en={"greeting": "Hello"},
                tr={"greeting": "Merhaba"},
                code='x = t("greeting")' if name != "tools-service" else "x = 1",
            )

        assert check_missing_translations(tmp_path) is False

    def test_passes_when_everything_lines_up(self, tmp_path: Path):
        apps_dir = tmp_path / "apps"
        for name in ["agent-service", "rag-service", "tools-service", "user-service"]:
            self._make_service(
                apps_dir,
                name,
                en={"greeting": "Hello {name}"},
                tr={"greeting": "Merhaba {name}"},
                code='x = t("greeting", name="Ali")',
            )

        assert check_missing_translations(tmp_path) is True
