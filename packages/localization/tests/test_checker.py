import json
from pathlib import Path

import localization.checker as checker_module
from localization.checker import (
    _resolve_repo_root,
    check_missing_translations,
    extract_placeholders,
    find_placeholder_mismatches,
    find_unused_keys,
    scan_agent_service_rag_tool_keys,
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

    def test_finds_keys_passed_through_the_private_error_helper(self, tmp_path: Path):
        (tmp_path / "knowledge_tools.py").write_text(
            'return _error("knowledge.collection_required", "validation")\n'
            'return log_error("not.a.key")\n',
            encoding="utf-8",
        )
        assert scan_python_code_for_keys(tmp_path) == {"knowledge.collection_required"}

    def test_ignores_keys_that_only_tests_reference(self, tmp_path: Path):
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_route.py").write_text(
            'self._raise_bad_request("role.only_in_tests")', encoding="utf-8"
        )
        (tmp_path / "route.py").write_text('t("agent.not_found")', encoding="utf-8")
        assert scan_python_code_for_keys(tmp_path) == {"agent.not_found"}

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

    def test_tools_service_dynamic_tool_metadata_keys_are_counted_as_used(
        self, tmp_path: Path
    ):
        apps_dir = tmp_path / "apps"
        for name in ["agent-service", "rag-service", "user-service"]:
            self._make_service(
                apps_dir,
                name,
                en={"greeting": "Hello"},
                tr={"greeting": "Merhaba"},
                code='x = t("greeting")',
            )

        tools_dir = apps_dir / "tools-service"
        locales = tools_dir / "locales"
        tools_src = tools_dir / "src" / "tools"
        locales.mkdir(parents=True)
        tools_src.mkdir(parents=True)
        locale_data = {
            "categories": {
                "calculator": {
                    "label": "Calculator",
                    "description": "Safe math",
                }
            },
            "tools": {
                "calculator": {
                    "calculate": {
                        "name": "Calculate",
                        "description": "Evaluate math",
                    }
                }
            },
        }
        (locales / "en.json").write_text(json.dumps(locale_data), encoding="utf-8")
        (locales / "tr.json").write_text(json.dumps(locale_data), encoding="utf-8")
        (tools_src / "calculator_tools.py").write_text(
            """
class CalculatorTools(BaseToolCategory):
    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return t("categories.calculator.description", default="Safe math")

    @property
    def label(self) -> str:
        return t("categories.calculator.label", default="Calculator")

    def register_tools(self, mcp):
        @mcp.tool()
        def calculate(expression: str) -> str:
            return expression
""",
            encoding="utf-8",
        )

        assert check_missing_translations(tmp_path) is True

    def _make_tools_service(self, apps_dir: Path, source: str) -> None:
        """Real repo layout: only tools-service's keys are under test, the
        other three services are given one trivially-passing key each so
        they don't add noise to the assertion.
        """
        for name in ["agent-service", "rag-service", "user-service"]:
            self._make_service(
                apps_dir, name, en={"greeting": "Hello"}, tr={"greeting": "Merhaba"},
                code='x = t("greeting")',
            )

        tools_dir = apps_dir / "tools-service"
        locales = tools_dir / "locales"
        tools_src = tools_dir / "src" / "tools"
        locales.mkdir(parents=True)
        tools_src.mkdir(parents=True)
        locale_data = {
            "categories": {"git": {"label": "Git", "description": "Git ops"}},
            "tools": {"git": {"git_status": {"name": "Status", "description": "Show status"}}},
        }
        (locales / "en.json").write_text(json.dumps(locale_data), encoding="utf-8")
        (locales / "tr.json").write_text(json.dumps(locale_data), encoding="utf-8")
        (tools_src / "git_tools.py").write_text(source, encoding="utf-8")

    def test_tool_wrapped_by_an_extra_decorator_before_mcp_tool_is_still_counted_as_used(
        self, tmp_path: Path
    ):
        # git_tools.py's real tools are wrapped with @guard_workspace_escape
        # between @mcp.tool() and def -- the scanner must not require the
        # def to immediately follow @mcp.tool().
        self._make_tools_service(
            tmp_path / "apps",
            """
class GitTools(BaseToolCategory):
    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return t("categories.git.description", default="Git ops")

    @property
    def label(self) -> str:
        return t("categories.git.label", default="Git")

    def register_tools(self, mcp):
        @mcp.tool()
        @guard_workspace_escape
        def git_status(repo_path: str) -> str:
            return repo_path
""",
        )

        assert check_missing_translations(tmp_path) is True

    def test_tool_registered_via_a_direct_mcp_tool_call_is_still_counted_as_used(
        self, tmp_path: Path
    ):
        # connector_tools.py registers its tools as `mcp.tool()(fn)` rather
        # than the `@mcp.tool()` decorator spelling -- the scanner must
        # recognize this registration style too.
        self._make_tools_service(
            tmp_path / "apps",
            """
def git_status(repo_path: str) -> str:
    return repo_path


class GitTools(BaseToolCategory):
    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return t("categories.git.description", default="Git ops")

    @property
    def label(self) -> str:
        return t("categories.git.label", default="Git")

    def register_tools(self, mcp):
        mcp.tool()(git_status)
""",
        )

        assert check_missing_translations(tmp_path) is True


class TestResolveRepoRoot:
    def test_prefers_an_explicit_argv_root_over_the_file_layout_guess(self, tmp_path):
        resolved = _resolve_repo_root(["prog", str(tmp_path)], Path(checker_module.__file__))
        assert resolved == tmp_path.resolve()

    def test_falls_back_to_the_checker_files_own_repo_layout_when_no_arg_given(self):
        # No CLI arg: must still land on the real repo root purely from
        # checker.py's own location, e.g. so `python -m localization.checker` keeps
        # working with no arguments the way it always has.
        resolved = _resolve_repo_root(["prog"], Path(checker_module.__file__))
        assert (resolved / "packages" / "localization" / "pyproject.toml").is_file()


class TestMessageKeysAndSharedCatalogs(TestCheckMissingTranslationsCatchesDeadKeys):
    def test_scans_literal_message_key_keywords_and_attributes(self, tmp_path):
        (tmp_path / "errors.py").write_text(
            'class Failure:\n    message_key = "common.failure"\n'
            '    other: str = "ignored.value"\n'
            'class Missing:\n    message_key: str = "common.missing"\n'
            'raise Failure(message_key="agent.failure")\n'
            '# message_key = "ignored.comment"\n'
            'text = \'message_key="ignored.string"\'\n', encoding="utf-8",
        )
        assert scan_python_code_for_keys(tmp_path) == {
            "common.failure", "common.missing", "agent.failure",
        }

    def _make_shared_repo(self, tmp_path, key="common.failure", en=None, tr=None):
        for name in ["agent-service", "rag-service", "tools-service", "user-service"]:
            self._make_service(
                tmp_path / "apps", name, {"greeting": "Hello"}, {"greeting": "Merhaba"},
                f'x = t("greeting")\nraise Failure(message_key="{key}")\n',
            )
        locales = tmp_path / "packages/error-contract/src/error_contract/locales"
        locales.mkdir(parents=True)
        data = {"common.failure": "Failure", "common.unused": "Unused"}
        (locales / "en.json").write_text(json.dumps(data if en is None else en))
        (locales / "tr.json").write_text(json.dumps(data if tr is None else tr))

    def test_accepts_shared_keys_without_requiring_all_shared_keys_used(self, tmp_path):
        self._make_shared_repo(tmp_path)
        assert check_missing_translations(tmp_path) is True

    def test_reports_message_key_missing_from_service_and_shared_catalogs(self, tmp_path, capsys):
        self._make_shared_repo(tmp_path, key="common.unknown")
        assert check_missing_translations(tmp_path) is False
        assert "common.unknown' used in Python code" in capsys.readouterr().out

    def test_requires_referenced_shared_key_in_both_locales(self, tmp_path, capsys):
        self._make_shared_repo(tmp_path, tr={"common.unused": "Unused"})
        assert check_missing_translations(tmp_path) is False
        assert "common.failure' used in Python code" in capsys.readouterr().out

    def test_counts_tool_decorators_with_intervening_comments(self, tmp_path):
        self._make_tools_service(tmp_path / "apps", '''
class GitTools:
    def name(self) -> str:
        return "git"
    def register_tools(self, mcp):
        t("categories.git.label")
        t("categories.git.description")
        @mcp.tool()
        # comment before another decorator
        @guard_workspace_escape
        # comment before def
        def git_status(repo_path: str) -> str:
            return repo_path
''')
        assert check_missing_translations(tmp_path) is True


class TestRagToolKeys:
    def _write_helpers(self, service_dir: Path, body: str) -> None:
        helpers = service_dir / "src" / "service" / "personas"
        helpers.mkdir(parents=True)
        (helpers / "persona_helpers.py").write_text(body, encoding="utf-8")

    def test_derives_name_and_description_keys_from_the_declared_tool_names(self, tmp_path: Path):
        service_dir = tmp_path / "agent-service"
        self._write_helpers(service_dir, 'RAG_TOOL_NAMES = ("database_search", "graph_search")\n')

        assert scan_agent_service_rag_tool_keys(service_dir) == {
            "rag_tool.database_search.name",
            "rag_tool.database_search.description",
            "rag_tool.graph_search.name",
            "rag_tool.graph_search.description",
        }

    def test_returns_nothing_without_the_declaration_or_for_other_services(self, tmp_path: Path):
        service_dir = tmp_path / "agent-service"
        self._write_helpers(service_dir, "x = 1\n")
        assert scan_agent_service_rag_tool_keys(service_dir) == set()
        assert scan_agent_service_rag_tool_keys(tmp_path / "rag-service") == set()
