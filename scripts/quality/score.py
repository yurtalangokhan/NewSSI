#!/usr/bin/env python3
"""Quality score reporter for the Agentic AI monorepo.

The architecture gate remains the source of truth for objective HARD findings.
This module turns those findings into a compact 0-100 score that can be used in
local reports and hook thresholds.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quality import check_architecture


@dataclass(frozen=True)
class Finding:
    severity: str
    location: str
    message: str


@dataclass(frozen=True)
class ScorePolicy:
    hard_penalty: int = 25
    warn_penalty: int = 5


@dataclass(frozen=True)
class ScoreResult:
    score: int
    grade: str
    hard_count: int
    warn_count: int


def grade_for_score(score: int) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def calculate_score(findings: list[Finding], policy: ScorePolicy) -> ScoreResult:
    hard_count = sum(1 for finding in findings if finding.severity == "HARD")
    warn_count = sum(1 for finding in findings if finding.severity == "WARN")
    penalty = hard_count * policy.hard_penalty + warn_count * policy.warn_penalty
    score = max(0, 100 - penalty)
    return ScoreResult(
        score=score,
        grade=grade_for_score(score),
        hard_count=hard_count,
        warn_count=warn_count,
    )


def quality_status(result: ScoreResult, minimum_score: int | None) -> str:
    if minimum_score is None:
        return "pass"
    return "pass" if result.score >= minimum_score else "fail"


def collect_findings(mode: str) -> list[Finding]:
    if mode == "--all":
        os.environ["QUALITY_MODE"] = "all"
    elif mode == "--changed" and "QUALITY_MODE" not in os.environ:
        os.environ["QUALITY_MODE"] = os.environ.get("HOOK_MODE", "staged")

    findings: list[Finding] = []
    hard_enabled = mode == "--changed"
    for path in check_architecture.changed_files():
        absolute_path = ROOT / path
        if check_architecture.PY_SERVICE_RE.match(path):
            raw_findings = check_architecture.check_python(
                path,
                check_architecture.read_lines(absolute_path),
                hard_enabled,
            )
        elif check_architecture.WEB_RE.match(path):
            raw_findings = check_architecture.check_web(
                path,
                check_architecture.read_lines(absolute_path),
                hard_enabled,
            )
        else:
            continue

        findings.extend(
            Finding(severity=severity, location=location, message=message)
            for severity, location, message in raw_findings
        )
    return findings


def print_report(
    result: ScoreResult,
    findings: list[Finding],
    minimum_score: int | None,
    max_findings: int,
) -> None:
    print("\n=== Quality score ===")
    print(f"Score: {result.score}/100  Grade: {result.grade}")
    print(f"HARD findings: {result.hard_count}")
    print(f"WARN findings: {result.warn_count}")
    if minimum_score is None:
        print("Threshold: report-only")
    else:
        print(f"Threshold: {minimum_score}/100")
    print(f"Status: {quality_status(result, minimum_score)}")

    if findings:
        print("\nFindings included in score:")
        for finding in findings[:max_findings]:
            print(f"  [{finding.severity}] {finding.location}: {finding.message}")
        remaining = len(findings) - max_findings
        if remaining > 0:
            print(f"  ... and {remaining} more finding(s).")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report the monorepo quality score.")
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Score the changed file set used by hooks.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Score the full tracked tree.",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=None,
        help="Fail when the score is below this threshold.",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=50,
        help="Maximum number of scored findings to print.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.changed and args.all:
        print("Use only one of --changed or --all.", file=sys.stderr)
        return 2
    mode = "--all" if args.all else "--changed"
    findings = collect_findings(mode)
    result = calculate_score(findings, ScorePolicy())
    print_report(result, findings, args.min_score, args.max_findings)
    return 0 if quality_status(result, args.min_score) == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
