#!/usr/bin/env python3
"""Generate the Datadog E2E verification results document.

Collects results from the orchestrator output JSON, bilingual comparison,
and screenshot validation, then renders the final Markdown results document.

Usage:
    python scripts/generate-results.py \
        --verifier-name "Yoshiki Fujiwara" \
        --output docs/ja/verification-results-datadog.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure project root is on sys.path for package imports
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from scripts.verification.bilingual_comparator import compare_setup_guides
from scripts.verification.screenshot_validator import validate_screenshots
from scripts.verification.results_renderer import render_report, render_bilingual_summary
from scripts.verification.models import (
    VerificationReport,
    VerificationStep,
    VerificationEnvironment,
    VerifierInfo,
    Issue,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional argument list for testing. Defaults to sys.argv[1:].

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Generate Datadog E2E verification results document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        default="docs/ja/verification-results-datadog.md",
        help="Output path for the results document (default: docs/ja/verification-results-datadog.md)",
    )
    parser.add_argument(
        "--orchestrator-results",
        default=None,
        help="Path to JSON output from verify-datadog-e2e.sh (optional)",
    )
    parser.add_argument(
        "--ja",
        default="integrations/datadog/docs/ja/setup-guide.md",
        help="Path to the Japanese setup guide (default: integrations/datadog/docs/ja/setup-guide.md)",
    )
    parser.add_argument(
        "--en",
        default="integrations/datadog/docs/en/setup-guide.md",
        help="Path to the English setup guide (default: integrations/datadog/docs/en/setup-guide.md)",
    )
    parser.add_argument(
        "--screenshots-dir",
        default="docs/screenshots",
        help="Path to the screenshots directory (default: docs/screenshots)",
    )
    parser.add_argument(
        "--verifier-name",
        required=True,
        help="Name of the person performing verification (required)",
    )
    parser.add_argument(
        "--verifier-role",
        default="DevOps Engineer",
        help="Role of the verifier (default: DevOps Engineer)",
    )
    parser.add_argument(
        "--region",
        default="ap-northeast-1",
        help="AWS region (default: ap-northeast-1)",
    )
    parser.add_argument(
        "--stack-name",
        default="fsxn-datadog-integration",
        help="CloudFormation stack name (default: fsxn-datadog-integration)",
    )

    return parser.parse_args(argv)


def load_orchestrator_results(path: str) -> list[VerificationStep]:
    """Load verification steps from orchestrator JSON output.

    The JSON file is expected to contain a list of step objects with
    fields matching the VerificationStep dataclass.

    Args:
        path: Path to the orchestrator results JSON file.

    Returns:
        A list of VerificationStep instances parsed from the JSON.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    steps: list[VerificationStep] = []
    for item in data.get("steps", []):
        steps.append(
            VerificationStep(
                step_number=item.get("step_number", 0),
                step_name=item.get("step_name", ""),
                result=item.get("result", "skipped"),
                command=item.get("command"),
                output=item.get("output"),
                screenshot_path=item.get("screenshot_path"),
                error_detail=item.get("error_detail"),
                timestamp=item.get("timestamp", ""),
            )
        )

    return steps


def build_report(args: argparse.Namespace) -> VerificationReport:
    """Build a VerificationReport from all collected data sources.

    Collects orchestrator results (if available), runs bilingual
    comparison, runs screenshot validation, and assembles the
    complete report.

    Args:
        args: Parsed command-line arguments.

    Returns:
        A fully populated VerificationReport instance.
    """
    # Determine verification timestamp (JST = UTC+9)
    jst = timezone(timedelta(hours=9))
    verification_date = datetime.now(jst).strftime("%Y-%m-%dT%H:%M:%S+09:00")

    # Build environment info
    environment = VerificationEnvironment(
        aws_region=args.region,
        stack_name=args.stack_name,
        lambda_function_name=f"{args.stack_name}-shipper",
        datadog_site="datadoghq.com",
    )

    # Build verifier info
    verifier = VerifierInfo(
        name=args.verifier_name,
        role=args.verifier_role,
    )

    # Collect orchestrator steps (if JSON provided)
    steps: list[VerificationStep] = []
    if args.orchestrator_results and os.path.exists(args.orchestrator_results):
        steps = load_orchestrator_results(args.orchestrator_results)

    # Run bilingual comparison
    bilingual_result = compare_setup_guides(args.ja, args.en)

    # Run screenshot validation
    screenshot_steps = validate_screenshots(args.screenshots_dir)

    # Append screenshot validation steps (renumber after orchestrator steps)
    base_step_number = max((s.step_number for s in steps), default=0)
    for i, ss in enumerate(screenshot_steps, start=1):
        ss.step_number = base_step_number + i
        steps.append(ss)

    # Collect issues from failures
    issues: list[Issue] = []
    for step in steps:
        if step.result == "failure" and step.error_detail:
            issues.append(
                Issue(
                    title=f"ステップ {step.step_number}: {step.step_name}",
                    description=step.error_detail,
                )
            )

    if bilingual_result.status == "fail":
        for diff in bilingual_result.differences:
            issues.append(
                Issue(
                    title=f"バイリンガル差異: {diff.diff_type} ({diff.section})",
                    description=(
                        f"ファイル: {diff.file_path_ja} / {diff.file_path_en}\n"
                        f"期待値: {diff.expected}\n"
                        f"実際値: {diff.actual}"
                    ),
                )
            )

    return VerificationReport(
        verification_date=verification_date,
        environment=environment,
        verifier=verifier,
        steps=steps,
        bilingual_comparison=bilingual_result,
        issues=issues,
    )


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the results generator.

    Args:
        argv: Optional argument list for testing. Defaults to sys.argv[1:].

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    args = parse_args(argv)

    # Build the report
    report = build_report(args)

    # Render the report
    report_md = render_report(report)
    bilingual_md = render_bilingual_summary(report.bilingual_comparison)

    # Combine into final document
    final_document = report_md + "\n" + bilingual_md

    # Ensure output directory exists
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Write to output file
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(final_document)

    # Print summary to stdout
    total_steps = len(report.steps)
    passed_steps = sum(1 for s in report.steps if s.result == "success")
    failed_steps = sum(1 for s in report.steps if s.result == "failure")
    skipped_steps = sum(1 for s in report.steps if s.result == "skipped")

    print("=" * 60)
    print("Datadog E2E 検証結果サマリ")
    print("=" * 60)
    print(f"  検証日時: {report.verification_date}")
    print(f"  検証者: {report.verifier.name} ({report.verifier.role})")
    print(f"  リージョン: {report.environment.aws_region}")
    print(f"  スタック名: {report.environment.stack_name}")
    print("-" * 60)
    print(f"  ステップ合計: {total_steps}")
    print(f"    ✅ 成功: {passed_steps}")
    print(f"    ❌ 失敗: {failed_steps}")
    print(f"    ⏭️  スキップ: {skipped_steps}")
    print("-" * 60)
    print(f"  バイリンガル対応: {report.bilingual_comparison.status}")
    print(f"  検出された問題: {len(report.issues)} 件")
    print("-" * 60)
    print(f"  出力ファイル: {args.output}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
