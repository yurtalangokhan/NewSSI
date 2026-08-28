import unittest
from contextlib import redirect_stdout
from io import StringIO

from scripts.quality.score import (
    Finding,
    ScorePolicy,
    calculate_score,
    print_report,
    quality_status,
)


class QualityScoreTests(unittest.TestCase):
    def test_calculate_score_weights_hard_and_warn_findings(self) -> None:
        findings = [
            Finding("HARD", "apps/service.py:1", "Layer leakage"),
            Finding("WARN", "apps/service.py", "Function is too long"),
            Finding("WARN", "apps/component.tsx", "Module is too large"),
        ]

        result = calculate_score(findings, ScorePolicy())

        self.assertEqual(72, result.score)
        self.assertEqual(1, result.hard_count)
        self.assertEqual(2, result.warn_count)
        self.assertEqual("C", result.grade)

    def test_calculate_score_never_drops_below_zero_for_hard_findings(self) -> None:
        findings = [
            Finding("HARD", f"apps/service.py:{line}", "Layer leakage")
            for line in range(10)
        ]

        result = calculate_score(findings, ScorePolicy())

        self.assertEqual(0, result.score)
        self.assertEqual("F", result.grade)

    def test_warn_findings_are_capped_so_existing_debt_does_not_zero_score(self) -> None:
        findings = [
            Finding("WARN", f"apps/service.py:{line}", "Approximate cyclomatic complexity")
            for line in range(100)
        ]

        result = calculate_score(findings, ScorePolicy())

        self.assertEqual(82, result.score)
        self.assertEqual(100, result.warn_count)
        self.assertEqual("B", result.grade)

    def test_test_file_warnings_have_lower_weight(self) -> None:
        findings = [
            Finding("WARN", "apps/service.py:1", "Function is too long"),
            Finding("WARN", "apps/service.py:2", "Module is too large"),
            Finding("WARN", "apps/tests/test_service.py:3", "Function is too long"),
        ]

        result = calculate_score(findings, ScorePolicy())

        self.assertEqual(96, result.score)

    def test_quality_status_fails_when_score_is_below_threshold(self) -> None:
        result = calculate_score(
            [Finding("WARN", "apps/service.py", "Layer leakage")],
            ScorePolicy(warn_penalty_cap=40),
        )

        self.assertEqual("fail", quality_status(result, minimum_score=98))
        self.assertEqual("pass", quality_status(result, minimum_score=95))

    def test_quality_status_fails_hard_findings_under_threshold_mode(self) -> None:
        result = calculate_score(
            [Finding("HARD", "apps/service.py:1", "Layer leakage")],
            ScorePolicy(),
        )

        self.assertEqual("fail", quality_status(result, minimum_score=1))
        self.assertEqual("pass", quality_status(result, minimum_score=None))

    def test_print_report_summarizes_findings_beyond_display_limit(self) -> None:
        findings = [
            Finding("WARN", f"apps/service.py:{line}", "Complexity warning")
            for line in range(3)
        ]
        result = calculate_score(findings, ScorePolicy())
        buffer = StringIO()

        with redirect_stdout(buffer):
            print_report(result, findings, minimum_score=None, max_findings=2)

        output = buffer.getvalue()
        self.assertIn("apps/service.py:0", output)
        self.assertIn("apps/service.py:1", output)
        self.assertNotIn("apps/service.py:2", output)
        self.assertIn("... and 1 more finding(s).", output)


if __name__ == "__main__":
    unittest.main()
