import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class QuietValidationTests(unittest.TestCase):
    def run_script(
        self, script: str, *args: str
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as log_dir:
            env = os.environ | {"VALIDATION_LOG_DIR": log_dir}
            return subprocess.run(
                [str(ROOT / "scripts" / script), *args],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

    def run_merge_validation(
        self, quality_files: str, failing_service: str = ""
    ) -> tuple[subprocess.CompletedProcess[str], str, dict[str, str]]:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bin_dir = temp_path / "bin"
            log_dir = temp_path / "logs"
            calls_file = temp_path / "make-calls"
            bin_dir.mkdir()
            log_dir.mkdir()

            make_stub = bin_dir / "make"
            make_stub.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >>"$MAKE_CALLS_FILE"\n'
                'printf "very noisy ruff and pytest output\\n"\n'
                'if [[ -n "$FAILING_SERVICE" && "$*" == *"/$FAILING_SERVICE validate" ]]; then\n'
                '  printf "src/example.py:12: error: validation failed\\n"\n'
                "  exit 1\n"
                "fi\n"
            )
            make_stub.chmod(0o755)

            env = os.environ | {
                "FAILING_SERVICE": failing_service,
                "MAKE_CALLS_FILE": str(calls_file),
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "QUALITY_FILES": quality_files,
                "VALIDATION_LOG_DIR": str(log_dir),
            }
            result = subprocess.run(
                ["bash", "scripts/validate-merge.sh"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            calls = calls_file.read_text() if calls_file.exists() else ""
            logs = {path.name: path.read_text() for path in log_dir.glob("*.log")}
            return result, calls, logs

    def test_quiet_runner_prints_only_pass_marker_on_success(self) -> None:
        result = self.run_script(
            "validation/quiet-run.sh",
            "targeted test",
            "--",
            "bash",
            "-c",
            "printf 'noisy output\\n'",
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "[PASS] targeted test\n")
        self.assertEqual(result.stderr, "")

    def test_quiet_runner_limits_failure_diagnostics_to_15_lines(self) -> None:
        command = (
            "for i in $(seq 1 20); do "
            'echo "file.py:$i: error: issue $i"; '
            "done; exit 7"
        )
        result = self.run_script(
            "validation/quiet-run.sh",
            "targeted test",
            "--",
            "bash",
            "-c",
            command,
        )

        self.assertEqual(result.returncode, 7)
        lines = result.stderr.splitlines()
        self.assertEqual(lines[0], "[FAIL] targeted test")
        self.assertLessEqual(len(lines[1:]), 15)
        self.assertIn("file.py:20: error: issue 20", lines)

    def test_quiet_runner_keeps_full_log_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as log_dir:
            env = os.environ | {"VALIDATION_LOG_DIR": log_dir}
            result = subprocess.run(
                [
                    str(ROOT / "scripts/validation/quiet-run.sh"),
                    "targeted test",
                    "--",
                    "bash",
                    "-c",
                    "echo 'complete diagnostic'; exit 1",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            logs = list(Path(log_dir).glob("*.log"))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(logs), 1)
            self.assertIn("complete diagnostic", logs[0].read_text())

    def test_push_wrapper_rejects_unknown_service(self) -> None:
        result = self.run_script("validate-push.sh", "--service=unknown")

        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown service: unknown", result.stderr)

    def test_task_wrapper_runs_command_from_service_directory(self) -> None:
        result = self.run_script(
            "validate-task.sh",
            "--service=agent-service",
            "--",
            "bash",
            "-c",
            "test \"$(basename \"$PWD\")\" = agent-service",
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "[PASS] task:agent-service\n")

    def test_spec_wrapper_runs_affected_tests_from_service_directory(self) -> None:
        result = self.run_script(
            "validate-spec.sh",
            "--service=rag-service",
            "--",
            "bash",
            "-c",
            'test "$(basename "$PWD")" = rag-service',
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "[PASS] spec:rag-service\n")

    def test_spec_wrapper_supports_repository_root(self) -> None:
        result = self.run_script(
            "validate-spec.sh",
            "--service=root",
            "--",
            "bash",
            "-c",
            f'test "$PWD" = "{ROOT}"',
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "[PASS] spec:root\n")

    def test_full_service_validation_runs_only_in_push_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bin_dir = temp_path / "bin"
            bin_dir.mkdir()
            calls_file = temp_path / "make-calls"
            make_stub = bin_dir / "make"
            make_stub.write_text(
                '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >>"$MAKE_CALLS_FILE"\n'
            )
            make_stub.chmod(0o755)

            python_stub = bin_dir / "python3"
            python_stub.write_text("#!/usr/bin/env bash\nexit 0\n")
            python_stub.chmod(0o755)

            env = os.environ | {
                "MAKE_CALLS_FILE": str(calls_file),
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "QUALITY_FILES": "apps/agent-service/Makefile",
            }

            staged = subprocess.run(
                ["bash", "scripts/quality/check.sh", "staged"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            staged_calls = calls_file.read_text() if calls_file.exists() else ""

            calls_file.unlink(missing_ok=True)
            pushed = subprocess.run(
                ["bash", "scripts/quality/check.sh", "push"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            push_calls = calls_file.read_text() if calls_file.exists() else ""

        self.assertEqual(staged.returncode, 0, staged.stdout + staged.stderr)
        self.assertNotIn("apps/agent-service validate", staged_calls)
        self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
        self.assertIn("-C apps/agent-service validate", push_calls)

    def test_merge_validation_runs_only_affected_services_concisely(self) -> None:
        result, calls, _ = self.run_merge_validation(
            "\n".join(
                (
                    "apps/agent-service/src/service/example.py",
                    "apps/web/src/app/page.tsx",
                    "apps/rag-service/docs/operations.md",
                    "apps/user-service/AGENTS.md",
                )
            )
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("/agent-service validate", calls)
        self.assertIn("/web validate", calls)
        self.assertNotIn("/rag-service validate", calls)
        self.assertNotIn("/user-service validate", calls)
        self.assertEqual(
            result.stdout,
            "[PASS] validate:agent-service\n[PASS] validate:web\n",
        )
        self.assertNotIn("very noisy", result.stdout + result.stderr)

    def test_merge_validation_does_not_list_unchanged_services(self) -> None:
        result, calls, _ = self.run_merge_validation(
            "apps/tools-service/docs/tooling.md\nREADME.md"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls, "")
        self.assertEqual(result.stdout, "[PASS] merge:no-service-changes\n")

    def test_merge_validation_reports_all_affected_services_after_failure(self) -> None:
        result, calls, logs = self.run_merge_validation(
            "apps/agent-service/src/service/example.py\napps/web/src/app/page.tsx",
            failing_service="agent-service",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("/agent-service validate", calls)
        self.assertIn("/web validate", calls)
        self.assertIn("[FAIL] validate:agent-service", result.stderr)
        self.assertIn("[PASS] validate:web", result.stdout)
        self.assertTrue(logs)
        self.assertIn("very noisy ruff", "\n".join(logs.values()))

    def test_merge_validation_includes_deleted_code_files_in_revision_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            bin_dir = temp_path / "bin"
            log_dir = temp_path / "logs"
            calls_file = temp_path / "make-calls"
            bin_dir.mkdir()
            log_dir.mkdir()

            git_stub = bin_dir / "git"
            git_stub.write_text(
                "#!/usr/bin/env bash\n"
                'if [[ "$1 $2" == "rev-parse --show-toplevel" ]]; then\n'
                f'  printf "%s\\n" "{ROOT}"\n'
                "elif [[ \"$1\" == diff && \"$*\" == *\"--diff-filter=ACMRTD\"* ]]; then\n"
                '  printf "apps/tools-service/src/deleted.py\\n"\n'
                "fi\n"
            )
            git_stub.chmod(0o755)

            make_stub = bin_dir / "make"
            make_stub.write_text(
                "#!/usr/bin/env bash\n"
                'printf "%s\\n" "$*" >>"$MAKE_CALLS_FILE"\n'
            )
            make_stub.chmod(0o755)

            env = os.environ.copy()
            env.pop("QUALITY_FILES", None)
            env.update(
                {
                    "MAKE_CALLS_FILE": str(calls_file),
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "VALIDATION_LOG_DIR": str(log_dir),
                }
            )
            result = subprocess.run(
                ["bash", "scripts/validate-merge.sh", "base-sha", "head-sha"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            calls = calls_file.read_text() if calls_file.exists() else ""

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("/tools-service validate", calls)
        self.assertEqual(result.stdout, "[PASS] validate:tools-service\n")

    def test_merge_validation_fails_when_revision_diff_cannot_be_read(self) -> None:
        env = os.environ.copy()
        env.pop("QUALITY_FILES", None)

        result = subprocess.run(
            [
                "bash",
                "scripts/validate-merge.sh",
                "missing-base-revision",
                "missing-head-revision",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unable to determine changed files", result.stderr)

    def test_gitlab_pipeline_runs_merge_validation_and_keeps_failure_logs(self) -> None:
        config = (ROOT / ".gitlab-ci.yml").read_text()

        self.assertIn('CI_PIPELINE_SOURCE == "merge_request_event"', config)
        self.assertIn("scripts/validate-merge.sh", config)
        self.assertIn("CI_MERGE_REQUEST_DIFF_BASE_SHA", config)
        self.assertIn("CI_COMMIT_SHA", config)
        self.assertIn("when: on_failure", config)
        self.assertIn(".tmp/validation/", config)


if __name__ == "__main__":
    unittest.main()
