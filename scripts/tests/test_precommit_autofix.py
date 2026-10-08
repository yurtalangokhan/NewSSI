"""Autofix contract: pre-commit only fixes formatting; push scope is complete."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

COPIED_SCRIPTS = (
    "scripts/git-hooks/pre-commit",
    "scripts/quality/fix.sh",
    "scripts/quality/lib/changed_files.sh",
    "scripts/validation/quiet-run.sh",
)

UV_STUB = """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >>"$TOOL_CALLS_FILE"
if [[ "$1 $2 $3" == "run ruff format" ]]; then
  shift 3
  for arg in "$@"; do
    [[ -f "$arg" ]] && printf 'formatted = True\\n' >"$arg"
  done
fi
exit 0
"""

NPM_STUB = """#!/usr/bin/env bash
printf 'npm %s\\n' "$*" >>"$TOOL_CALLS_FILE"
if [[ "$3" == "eslint" ]]; then
  exit "${ESLINT_EXIT:-0}"
fi
exit 0
"""

# Anything from the full quality gate must stay out of the commit path.
FORBIDDEN_STUB = """#!/usr/bin/env bash
printf 'forbidden %s\\n' "$0 $*" >>"$TOOL_CALLS_FILE"
exit 1
"""


class PrecommitAutofixTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        temp_path = Path(self._temp.name)
        self.repo = temp_path / "repo"
        self.calls_file = temp_path / "tool-calls"
        bin_dir = temp_path / "bin"
        bin_dir.mkdir()

        for relative in COPIED_SCRIPTS:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        for relative in ("scripts/quality/check.sh", "scripts/validate-commit.sh"):
            self._write_executable(self.repo / relative, FORBIDDEN_STUB)

        self._write_executable(bin_dir / "uv", UV_STUB)
        self._write_executable(bin_dir / "npm", NPM_STUB)
        self._write_executable(bin_dir / "make", FORBIDDEN_STUB)

        self.env = os.environ | {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TOOL_CALLS_FILE": str(self.calls_file),
            "VALIDATION_LOG_DIR": str(temp_path / "logs"),
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
        self.env.pop("QUALITY_FILES", None)
        self.env.pop("QUALITY_BASE_REF", None)

        self.git("init", "-q")
        self.git("config", "core.hooksPath", "scripts/git-hooks")
        self.git("add", "scripts")
        self.git("commit", "-q", "--no-verify", "-m", "scripts")

    def tearDown(self) -> None:
        self._temp.cleanup()

    @staticmethod
    def _write_executable(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755)

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )

    def stage(self, relative: str, content: str) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.git("add", relative)

    def tool_calls(self) -> str:
        return self.calls_file.read_text() if self.calls_file.exists() else ""

    def commit_file(self, relative: str, content: str) -> None:
        self.stage(relative, content)
        self.git("commit", "-q", "--no-verify", "-m", relative)

    def push_changed_files(self) -> list[str]:
        result = subprocess.run(
            [
                "bash",
                "-c",
                "source scripts/quality/lib/changed_files.sh"
                " && quality_changed_files push",
            ],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.split()

    def run_fix(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "scripts/quality/fix.sh", *args],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_commit_formats_and_restages_python_without_quality_gate(self) -> None:
        self.stage("apps/rag-service/src/api.py", "formatted=False\n")
        self.stage("apps/agent-service/src/app.py", "x=1\n")

        result = self.git("commit", "-m", "change")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # git forwards hook stdout to stderr.
        self.assertIn("[PASS] pre-commit:autofix", result.stderr)
        calls = self.tool_calls()
        self.assertNotIn("forbidden", calls)
        self.assertIn(
            "uv run ruff check --config ruff.toml --fix --exit-zero src/app.py", calls
        )
        self.assertIn(
            "uv run ruff check --config ruff.toml --fix --exit-zero src/api.py", calls
        )
        for relative in (
            "apps/rag-service/src/api.py",
            "apps/agent-service/src/app.py",
        ):
            committed = self.git("show", f"HEAD:{relative}").stdout
            self.assertEqual(committed, "formatted = True\n", relative)
        self.assertEqual(self.git("status", "--porcelain").stdout, "")

    def test_leftover_eslint_findings_do_not_block_commit(self) -> None:
        self.stage("apps/web/src/page.tsx", "export default 1\n")
        self.env["ESLINT_EXIT"] = "1"

        result = self.git("commit", "-m", "web change")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.tool_calls()
        self.assertIn("npm exec -- prettier --write src/page.tsx", calls)
        # The web config disables unused-import rules; the commit fix enables it.
        self.assertIn(
            "npm exec -- eslint --fix --quiet"
            " --rule unused-imports/no-unused-imports: error src/page.tsx",
            calls,
        )

    def test_eslint_crash_blocks_commit(self) -> None:
        self.stage("apps/web/src/page.tsx", "export default 1\n")
        self.env["ESLINT_EXIT"] = "2"

        result = self.git("commit", "-m", "web change")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[FAIL] pre-commit:autofix", result.stderr)

    def test_partially_staged_file_blocks_commit(self) -> None:
        self.stage("apps/user-service/src/users.py", "a = 1\n")
        (self.repo / "apps/user-service/src/users.py").write_text("a = 2\n")

        result = self.git("commit", "-m", "partial")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("apps/user-service/src/users.py", result.stderr)
        self.assertEqual(self.tool_calls(), "")

    def test_commit_without_fixable_files_skips_tools(self) -> None:
        self.stage("README.md", "docs\n")

        result = self.git("commit", "-m", "docs")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tool_calls(), "")

    def test_strict_mode_fails_on_leftover_lint(self) -> None:
        self.stage("apps/web/src/page.tsx", "export default 1\n")
        self.stage("apps/tools-service/src/tool.py", "y=2\n")
        self.env["ESLINT_EXIT"] = "1"

        result = self.run_fix("staged", "--strict")

        self.assertNotEqual(result.returncode, 0)
        calls = self.tool_calls()
        self.assertIn("uv run ruff check --config ruff.toml --fix src/tool.py", calls)
        self.assertNotIn("--exit-zero", calls)

    def test_push_without_upstream_covers_every_commit_since_base(self) -> None:
        self.git("branch", "-M", "dev")
        self.git("switch", "-q", "-c", "feature")
        self.commit_file("apps/agent-service/src/first.py", "a = 1\n")
        self.commit_file("apps/agent-service/src/second.py", "b = 1\n")

        self.assertEqual(
            self.push_changed_files(),
            [
                "apps/agent-service/src/first.py",
                "apps/agent-service/src/second.py",
            ],
        )

    def test_push_without_upstream_on_base_branch_uses_last_commit(self) -> None:
        self.git("branch", "-M", "dev")
        self.commit_file("apps/agent-service/src/first.py", "a = 1\n")
        self.commit_file("apps/agent-service/src/second.py", "b = 1\n")

        self.assertEqual(
            self.push_changed_files(), ["apps/agent-service/src/second.py"]
        )

    def test_push_base_ref_override_wins(self) -> None:
        self.git("branch", "-M", "dev")
        self.git("switch", "-q", "-c", "feature")
        self.commit_file("apps/agent-service/src/first.py", "a = 1\n")
        self.commit_file("apps/agent-service/src/second.py", "b = 1\n")
        self.env["QUALITY_BASE_REF"] = "HEAD~1"

        self.assertEqual(
            self.push_changed_files(), ["apps/agent-service/src/second.py"]
        )

    def test_push_fails_when_autofix_changes_pushed_files(self) -> None:
        self.git("branch", "-M", "dev")
        self.git("switch", "-q", "-c", "feature")
        self.commit_file("apps/agent-service/src/app.py", "x=1\n")

        result = self.run_fix("push", "--strict")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("commit the fixes", result.stderr)
        self.assertIn(" - apps/agent-service/src/app.py", result.stderr)

    def test_push_passes_when_pushed_files_are_already_formatted(self) -> None:
        self.git("branch", "-M", "dev")
        self.git("switch", "-q", "-c", "feature")
        self.commit_file("apps/agent-service/src/app.py", "formatted = True\n")

        result = self.run_fix("push", "--strict")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("uv run ruff format", self.tool_calls())


if __name__ == "__main__":
    unittest.main()
