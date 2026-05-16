"""Unit tests for the verification results renderer.

Tests render_report and render_bilingual_summary functions for correct
Markdown output generation across various input scenarios.

Requirements: 8.2, 8.3, 8.4, 8.5, 8.6
"""

from __future__ import annotations

from scripts.verification.models import (
    BilingualComparisonResult,
    BilingualDifference,
    Issue,
    VerificationEnvironment,
    VerificationReport,
    VerificationStep,
    VerifierInfo,
)
from scripts.verification.results_renderer import render_bilingual_summary, render_report


def _make_environment() -> VerificationEnvironment:
    """Create a sample verification environment."""
    return VerificationEnvironment(
        aws_region="ap-northeast-1",
        stack_name="fsxn-datadog-integration",
        lambda_function_name="fsxn-datadog-integration-shipper",
        datadog_site="datadoghq.com",
    )


def _make_verifier() -> VerifierInfo:
    """Create a sample verifier."""
    return VerifierInfo(name="田中太郎", role="SRE Engineer")


def _make_full_report() -> VerificationReport:
    """Create a full report with all fields populated."""
    return VerificationReport(
        verification_date="2026-01-15T14:30:00+09:00",
        environment=_make_environment(),
        verifier=_make_verifier(),
        steps=[
            VerificationStep(
                step_number=1,
                step_name="Deploy CloudFormation Stack",
                result="success",
                command="aws cloudformation deploy --template-file template.yaml --stack-name fsxn-datadog-integration",
                output="Stack fsxn-datadog-integration created successfully.",
                screenshot_path=None,
                error_detail=None,
                timestamp="2026-01-15T14:30:00+09:00",
            ),
            VerificationStep(
                step_number=2,
                step_name="Verify Datadog Log Arrival",
                result="success",
                command=None,
                output="Found 5 logs matching source:fsxn within 5 minutes.",
                screenshot_path="docs/screenshots/datadog-logs-arrival.png",
                error_detail=None,
                timestamp="2026-01-15T14:35:00+09:00",
            ),
            VerificationStep(
                step_number=3,
                step_name="Configure Log Pipeline",
                result="failure",
                command="curl -X POST https://api.datadoghq.com/api/v1/logs/config/pipelines",
                output=None,
                screenshot_path="docs/screenshots/datadog-pipeline-config.png",
                error_detail="API returned 403 Forbidden",
                timestamp="2026-01-15T14:40:00+09:00",
            ),
        ],
        issues=[
            Issue(
                title="Datadog API 認証エラー",
                description="Pipeline 作成時に 403 エラーが発生",
                resolution="API キーの権限を確認し、logs_write_pipelines 権限を付与する",
            ),
        ],
    )


class TestRenderReportFullFields:
    """Test full report rendering with all fields populated."""

    def test_contains_verification_date(self) -> None:
        """Rendered report contains the ISO 8601 verification date."""
        report = _make_full_report()
        output = render_report(report)
        assert "2026-01-15T14:30:00+09:00" in output

    def test_contains_aws_region(self) -> None:
        """Rendered report contains the AWS region."""
        report = _make_full_report()
        output = render_report(report)
        assert "ap-northeast-1" in output

    def test_contains_stack_name(self) -> None:
        """Rendered report contains the CloudFormation stack name."""
        report = _make_full_report()
        output = render_report(report)
        assert "fsxn-datadog-integration" in output

    def test_contains_verifier_name(self) -> None:
        """Rendered report contains the verifier name."""
        report = _make_full_report()
        output = render_report(report)
        assert "田中太郎" in output

    def test_contains_verifier_role(self) -> None:
        """Rendered report contains the verifier role."""
        report = _make_full_report()
        output = render_report(report)
        assert "SRE Engineer" in output

    def test_contains_step_numbers_and_names(self) -> None:
        """Rendered report contains each step's number and name."""
        report = _make_full_report()
        output = render_report(report)
        assert "ステップ 1" in output
        assert "Deploy CloudFormation Stack" in output
        assert "ステップ 2" in output
        assert "Verify Datadog Log Arrival" in output
        assert "ステップ 3" in output
        assert "Configure Log Pipeline" in output

    def test_contains_issue_title_and_description(self) -> None:
        """Rendered report contains issue title and description."""
        report = _make_full_report()
        output = render_report(report)
        assert "Datadog API 認証エラー" in output
        assert "Pipeline 作成時に 403 エラーが発生" in output

    def test_contains_issue_resolution(self) -> None:
        """Rendered report contains issue resolution."""
        report = _make_full_report()
        output = render_report(report)
        assert "logs_write_pipelines 権限を付与する" in output


class TestRenderReportEmptyIssues:
    """Test that empty issues list renders '問題なし'."""

    def test_empty_issues_renders_mondainashi(self) -> None:
        """Empty issues list produces '問題なし' in output."""
        report = VerificationReport(
            verification_date="2026-01-15T14:30:00+09:00",
            environment=_make_environment(),
            verifier=_make_verifier(),
            steps=[
                VerificationStep(
                    step_number=1,
                    step_name="Deploy Stack",
                    result="success",
                    timestamp="2026-01-15T14:30:00+09:00",
                ),
            ],
            issues=[],
        )
        output = render_report(report)
        assert "問題なし" in output

    def test_non_empty_issues_does_not_render_mondainashi(self) -> None:
        """Non-empty issues list does NOT produce '問題なし'."""
        report = _make_full_report()
        output = render_report(report)
        assert "問題なし" not in output


class TestRenderReportScreenshots:
    """Test steps with/without screenshots produce correct image links."""

    def test_step_with_screenshot_has_image_link(self) -> None:
        """Step with screenshot_path produces a Markdown image link."""
        report = VerificationReport(
            verification_date="2026-01-15T14:30:00+09:00",
            environment=_make_environment(),
            verifier=_make_verifier(),
            steps=[
                VerificationStep(
                    step_number=1,
                    step_name="Verify Logs",
                    result="success",
                    screenshot_path="docs/screenshots/datadog-logs-arrival.png",
                    timestamp="2026-01-15T14:35:00+09:00",
                ),
            ],
            issues=[],
        )
        output = render_report(report)
        assert "![Verify Logs](docs/screenshots/datadog-logs-arrival.png)" in output

    def test_step_without_screenshot_has_no_image_link(self) -> None:
        """Step without screenshot_path does not produce an image link."""
        report = VerificationReport(
            verification_date="2026-01-15T14:30:00+09:00",
            environment=_make_environment(),
            verifier=_make_verifier(),
            steps=[
                VerificationStep(
                    step_number=1,
                    step_name="Deploy Stack",
                    result="success",
                    screenshot_path=None,
                    timestamp="2026-01-15T14:30:00+09:00",
                ),
            ],
            issues=[],
        )
        output = render_report(report)
        assert "![" not in output


class TestRenderReportCommands:
    """Test steps with/without commands produce correct code blocks."""

    def test_step_with_command_has_code_block(self) -> None:
        """Step with command produces a bash code block."""
        report = VerificationReport(
            verification_date="2026-01-15T14:30:00+09:00",
            environment=_make_environment(),
            verifier=_make_verifier(),
            steps=[
                VerificationStep(
                    step_number=1,
                    step_name="Deploy Stack",
                    result="success",
                    command="aws cloudformation deploy --template-file template.yaml",
                    timestamp="2026-01-15T14:30:00+09:00",
                ),
            ],
            issues=[],
        )
        output = render_report(report)
        assert "```bash" in output
        assert "aws cloudformation deploy --template-file template.yaml" in output

    def test_step_without_command_has_no_bash_code_block(self) -> None:
        """Step without command does not produce a bash code block."""
        report = VerificationReport(
            verification_date="2026-01-15T14:30:00+09:00",
            environment=_make_environment(),
            verifier=_make_verifier(),
            steps=[
                VerificationStep(
                    step_number=1,
                    step_name="Verify Logs",
                    result="success",
                    command=None,
                    output=None,
                    timestamp="2026-01-15T14:35:00+09:00",
                ),
            ],
            issues=[],
        )
        output = render_report(report)
        assert "```bash" not in output


class TestRenderReportOutput:
    """Test steps with/without output produce correct code blocks."""

    def test_step_with_output_has_output_code_block(self) -> None:
        """Step with output produces an output code block."""
        report = VerificationReport(
            verification_date="2026-01-15T14:30:00+09:00",
            environment=_make_environment(),
            verifier=_make_verifier(),
            steps=[
                VerificationStep(
                    step_number=1,
                    step_name="Deploy Stack",
                    result="success",
                    command=None,
                    output="Stack created successfully.",
                    timestamp="2026-01-15T14:30:00+09:00",
                ),
            ],
            issues=[],
        )
        output = render_report(report)
        assert "Stack created successfully." in output
        # Output is wrapped in a generic code block (```)
        assert "```\nStack created successfully.\n```" in output

    def test_step_without_output_has_no_output_block(self) -> None:
        """Step without output does not produce an output code block."""
        report = VerificationReport(
            verification_date="2026-01-15T14:30:00+09:00",
            environment=_make_environment(),
            verifier=_make_verifier(),
            steps=[
                VerificationStep(
                    step_number=1,
                    step_name="Deploy Stack",
                    result="success",
                    command=None,
                    output=None,
                    timestamp="2026-01-15T14:30:00+09:00",
                ),
            ],
            issues=[],
        )
        output = render_report(report)
        # No code blocks at all when no command and no output
        assert "```" not in output


class TestRenderReportErrorDetail:
    """Test steps with error_detail show the error information."""

    def test_step_with_error_detail_shows_error(self) -> None:
        """Step with error_detail includes the error in output."""
        report = VerificationReport(
            verification_date="2026-01-15T14:30:00+09:00",
            environment=_make_environment(),
            verifier=_make_verifier(),
            steps=[
                VerificationStep(
                    step_number=1,
                    step_name="Configure Pipeline",
                    result="failure",
                    error_detail="API returned 403 Forbidden",
                    timestamp="2026-01-15T14:40:00+09:00",
                ),
            ],
            issues=[],
        )
        output = render_report(report)
        assert "API returned 403 Forbidden" in output


class TestRenderReportMultipleIssues:
    """Test that multiple issues are all listed in the output."""

    def test_multiple_issues_all_listed(self) -> None:
        """All issues appear in the rendered output."""
        report = VerificationReport(
            verification_date="2026-01-15T14:30:00+09:00",
            environment=_make_environment(),
            verifier=_make_verifier(),
            steps=[],
            issues=[
                Issue(
                    title="認証エラー",
                    description="API キーが無効",
                    resolution="キーを再生成する",
                ),
                Issue(
                    title="タイムアウト",
                    description="ログ到着が5分以内に確認できず",
                    resolution=None,
                ),
                Issue(
                    title="スクリーンショット不足",
                    description="dashboard.png が見つからない",
                    resolution="手動で再撮影する",
                ),
            ],
        )
        output = render_report(report)
        assert "認証エラー" in output
        assert "API キーが無効" in output
        assert "キーを再生成する" in output
        assert "タイムアウト" in output
        assert "ログ到着が5分以内に確認できず" in output
        assert "スクリーンショット不足" in output
        assert "dashboard.png が見つからない" in output
        assert "手動で再撮影する" in output


class TestRenderBilingualSummaryWithDifferences:
    """Test render_bilingual_summary with differences shows all diffs."""

    def test_shows_all_differences(self) -> None:
        """Summary includes all difference details."""
        result = BilingualComparisonResult(
            status="fail",
            files_compared=[
                ("integrations/datadog/docs/ja/setup-guide.md", "integrations/datadog/docs/en/setup-guide.md"),
            ],
            heading_count=5,
            code_block_count=3,
            table_count=2,
            differences=[
                BilingualDifference(
                    file_path_ja="integrations/datadog/docs/ja/setup-guide.md",
                    file_path_en="integrations/datadog/docs/en/setup-guide.md",
                    section="デプロイ手順",
                    diff_type="heading",
                    expected="5 headings",
                    actual="4 headings",
                ),
                BilingualDifference(
                    file_path_ja="integrations/datadog/docs/ja/setup-guide.md",
                    file_path_en="integrations/datadog/docs/en/setup-guide.md",
                    section="コードブロック",
                    diff_type="code_block",
                    expected="aws deploy --region ap-northeast-1",
                    actual="aws deploy --region us-east-1",
                ),
            ],
        )
        output = render_bilingual_summary(result)
        assert "fail" in output
        assert "integrations/datadog/docs/ja/setup-guide.md" in output
        assert "integrations/datadog/docs/en/setup-guide.md" in output
        assert "5" in output  # heading_count
        assert "3" in output  # code_block_count
        assert "2" in output  # table_count or differences count
        assert "heading" in output
        assert "code_block" in output
        assert "デプロイ手順" in output
        assert "5 headings" in output
        assert "4 headings" in output
        assert "aws deploy --region ap-northeast-1" in output
        assert "aws deploy --region us-east-1" in output

    def test_shows_file_pairs(self) -> None:
        """Summary lists all compared file pairs."""
        result = BilingualComparisonResult(
            status="pass",
            files_compared=[
                ("docs/ja/setup-guide.md", "docs/en/setup-guide.md"),
                ("docs/ja/architecture.md", "docs/en/architecture.md"),
            ],
            heading_count=10,
            code_block_count=5,
            table_count=3,
            differences=[],
        )
        output = render_bilingual_summary(result)
        assert "docs/ja/setup-guide.md" in output
        assert "docs/en/setup-guide.md" in output
        assert "docs/ja/architecture.md" in output
        assert "docs/en/architecture.md" in output


class TestRenderBilingualSummaryPass:
    """Test render_bilingual_summary with pass status shows counts."""

    def test_pass_status_shown(self) -> None:
        """Summary shows pass status."""
        result = BilingualComparisonResult(
            status="pass",
            files_compared=[
                ("docs/ja/setup-guide.md", "docs/en/setup-guide.md"),
            ],
            heading_count=8,
            code_block_count=4,
            table_count=2,
            differences=[],
        )
        output = render_bilingual_summary(result)
        assert "pass" in output

    def test_counts_shown(self) -> None:
        """Summary shows heading, code block, and table counts."""
        result = BilingualComparisonResult(
            status="pass",
            files_compared=[
                ("docs/ja/setup-guide.md", "docs/en/setup-guide.md"),
            ],
            heading_count=8,
            code_block_count=4,
            table_count=2,
            differences=[],
        )
        output = render_bilingual_summary(result)
        assert "8" in output
        assert "4" in output
        assert "2" in output

    def test_zero_differences_count(self) -> None:
        """Summary shows 0 differences when none exist."""
        result = BilingualComparisonResult(
            status="pass",
            files_compared=[],
            heading_count=0,
            code_block_count=0,
            table_count=0,
            differences=[],
        )
        output = render_bilingual_summary(result)
        assert "0" in output
