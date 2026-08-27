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
    def test_calculate_score_penalizes_hard_and_warn_findings(self) -> None:
        findings = [
            Finding("HARD", "apps/service.py:1", "Layer leakage"),
            Finding("WARN", "apps/service.py", "Function is too long"),
            Finding("WARN", "apps/component.tsx", "Module is too large"),
        ]

        result = calculate_score(findings, ScorePolicy())

        self.assertEqual(65, result.score)
        self.assertEqual(1, result.hard_count)
        self.assertEqual(2, result.warn_count)
        self.assertEqual("D", result.grade)

    def test_calculate_score_never_drops_below_zero(self) -> None:
        findings = [
            Finding("HARD", f"apps/service.py:{line}", "Layer leakage")
            for line in range(10)
        ]

        result = calculate_score(findings, ScorePolicy())

        self.assertEqual(0, result.score)
        self.assertEqual("F", result.grade)

    def test_quality_status_fails_when_score_is_below_threshold(self) -> None:
        result = calculate_score(
            [Finding("WARN", "apps/service.py", "Complexity warning")],
            ScorePolicy(warn_penalty=25),
        )

        self.assertEqual("fail", quality_status(result, minimum_score=80))
        self.assertEqual("pass", quality_status(result, minimum_score=70))

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
