"""Property-based tests for results renderer.

Uses Hypothesis to generate random VerificationReport and
BilingualComparisonResult instances and verify that the renderer
produces complete Markdown output containing all required fields.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

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


# --- Hypothesis strategies for data model generation ---


@st.composite
def verification_environment_strategy(draw: st.DrawFn) -> VerificationEnvironment:
    """Generate a random VerificationEnvironment."""
    region = draw(
        st.sampled_from([
            "ap-northeast-1",
            "us-east-1",
            "eu-west-1",
            "us-west-2",
            "ap-southeast-1",
        ])
    )
    stack_name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=30,
        ).map(lambda s: f"fsxn-{s.strip() or 'stack'}")
    )
    function_name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=30,
        ).map(lambda s: f"fsxn-{s.strip() or 'func'}-shipper")
    )
    site = draw(
        st.sampled_from([
            "datadoghq.com",
            "datadoghq.eu",
            "us3.datadoghq.com",
            "us5.datadoghq.com",
        ])
    )
    return VerificationEnvironment(
        aws_region=region,
        stack_name=stack_name,
        lambda_function_name=function_name,
        datadog_site=site,
    )


@st.composite
def verifier_info_strategy(draw: st.DrawFn) -> VerifierInfo:
    """Generate a random VerifierInfo."""
    name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=2,
            max_size=20,
        ).map(lambda s: s.strip() or "Tester")
    )
    role = draw(
        st.sampled_from([
            "DevOps Engineer",
            "SRE",
            "Cloud Architect",
            "Platform Engineer",
            "Security Engineer",
        ])
    )
    return VerifierInfo(name=name, role=role)


@st.composite
def verification_step_strategy(draw: st.DrawFn) -> VerificationStep:
    """Generate a random VerificationStep."""
    step_number = draw(st.integers(min_value=1, max_value=20))
    step_name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=40,
        ).map(lambda s: s.strip() or "Step")
    )
    result = draw(st.sampled_from(["success", "failure", "skipped"]))
    command = draw(
        st.one_of(
            st.none(),
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "Z"),
                    blacklist_characters="\n\r`",
                ),
                min_size=5,
                max_size=80,
            ).map(lambda s: s.strip() or "echo test"),
        )
    )
    output = draw(
        st.one_of(
            st.none(),
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "Z"),
                    blacklist_characters="`",
                ),
                min_size=3,
                max_size=100,
            ).map(lambda s: s.strip() or "output"),
        )
    )
    screenshot_path = draw(
        st.one_of(
            st.none(),
            st.sampled_from([
                "docs/screenshots/datadog-logs-arrival.png",
                "docs/screenshots/datadog-pipeline-config.png",
                "docs/screenshots/datadog-facets-config.png",
                "docs/screenshots/datadog-dashboard.png",
                "docs/screenshots/datadog-unauthorized-access.png",
            ]),
        )
    )
    error_detail = draw(
        st.one_of(
            st.none(),
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "Z"),
                    blacklist_characters="\n\r",
                ),
                min_size=5,
                max_size=50,
            ).map(lambda s: s.strip() or "error"),
        )
    )
    return VerificationStep(
        step_number=step_number,
        step_name=step_name,
        result=result,
        command=command,
        output=output,
        screenshot_path=screenshot_path,
        error_detail=error_detail,
    )


@st.composite
def issue_strategy(draw: st.DrawFn) -> Issue:
    """Generate a random Issue."""
    title = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=40,
        ).map(lambda s: s.strip() or "Issue")
    )
    description = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=5,
            max_size=80,
        ).map(lambda s: s.strip() or "Description")
    )
    resolution = draw(
        st.one_of(
            st.none(),
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "Z"),
                    blacklist_characters="\n\r",
                ),
                min_size=5,
                max_size=60,
            ).map(lambda s: s.strip() or "Resolution"),
        )
    )
    return Issue(title=title, description=description, resolution=resolution)


@st.composite
def iso8601_date_strategy(draw: st.DrawFn) -> str:
    """Generate a valid ISO 8601 date string with timezone."""
    year = draw(st.integers(min_value=2024, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    day = draw(st.integers(min_value=1, max_value=28))
    hour = draw(st.integers(min_value=0, max_value=23))
    minute = draw(st.integers(min_value=0, max_value=59))
    second = draw(st.integers(min_value=0, max_value=59))
    tz_offset = draw(st.sampled_from(["+09:00", "+00:00", "-05:00", "+01:00"]))
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}{tz_offset}"


@st.composite
def verification_report_strategy(draw: st.DrawFn) -> VerificationReport:
    """Generate a random VerificationReport with all fields."""
    date = draw(iso8601_date_strategy())
    environment = draw(verification_environment_strategy())
    verifier = draw(verifier_info_strategy())
    steps = draw(st.lists(verification_step_strategy(), min_size=1, max_size=8))
    issues = draw(st.lists(issue_strategy(), min_size=0, max_size=5))
    return VerificationReport(
        verification_date=date,
        environment=environment,
        verifier=verifier,
        steps=steps,
        issues=issues,
    )


@st.composite
def verification_report_no_issues_strategy(draw: st.DrawFn) -> VerificationReport:
    """Generate a random VerificationReport with empty issues list."""
    date = draw(iso8601_date_strategy())
    environment = draw(verification_environment_strategy())
    verifier = draw(verifier_info_strategy())
    steps = draw(st.lists(verification_step_strategy(), min_size=1, max_size=8))
    return VerificationReport(
        verification_date=date,
        environment=environment,
        verifier=verifier,
        steps=steps,
        issues=[],
    )


@st.composite
def bilingual_difference_strategy(draw: st.DrawFn) -> BilingualDifference:
    """Generate a random BilingualDifference."""
    file_path_ja = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=30,
        ).map(lambda s: f"docs/ja/{s.strip() or 'file'}.md")
    )
    file_path_en = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=30,
        ).map(lambda s: f"docs/en/{s.strip() or 'file'}.md")
    )
    section = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=30,
        ).map(lambda s: s.strip() or "Section")
    )
    diff_type = draw(st.sampled_from(["heading", "code_block", "table"]))
    expected = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=1,
            max_size=30,
        ).map(lambda s: s.strip() or "expected")
    )
    actual = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=1,
            max_size=30,
        ).map(lambda s: s.strip() or "actual")
    )
    return BilingualDifference(
        file_path_ja=file_path_ja,
        file_path_en=file_path_en,
        section=section,
        diff_type=diff_type,
        expected=expected,
        actual=actual,
    )


@st.composite
def file_pair_strategy(draw: st.DrawFn) -> tuple[str, str]:
    """Generate a random file pair (ja_path, en_path)."""
    name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=20,
        ).map(lambda s: s.strip() or "guide")
    )
    return (f"docs/ja/{name}.md", f"docs/en/{name}.md")


@st.composite
def bilingual_comparison_result_strategy(
    draw: st.DrawFn,
) -> BilingualComparisonResult:
    """Generate a random BilingualComparisonResult."""
    status = draw(st.sampled_from(["pass", "fail"]))
    files_compared = draw(st.lists(file_pair_strategy(), min_size=0, max_size=5))
    heading_count = draw(st.integers(min_value=0, max_value=50))
    code_block_count = draw(st.integers(min_value=0, max_value=30))
    table_count = draw(st.integers(min_value=0, max_value=20))
    differences = draw(
        st.lists(bilingual_difference_strategy(), min_size=0, max_size=5)
    )
    return BilingualComparisonResult(
        status=status,
        files_compared=files_compared,
        heading_count=heading_count,
        code_block_count=code_block_count,
        table_count=table_count,
        differences=differences,
    )


# --- Property 1: Verification report rendering completeness ---

# Feature: datadog-e2e-verification, Property 1: Verification report rendering completeness


@given(report=verification_report_strategy())
@settings(max_examples=100)
def test_verification_report_rendering_completeness(
    report: VerificationReport,
) -> None:
    """Rendered report contains all required fields from the input data.

    For any valid VerificationReport, rendering to Markdown produces a document
    that contains: (a) the verification date in ISO 8601 format, (b) the AWS
    region and stack name, (c) the verifier name, (d) for each step: its number,
    name, and result badge, command in a code block (if present), and output
    (if present), (e) for each step with a screenshot_path: a Markdown image
    link, and (f) an issues section that is always present.

    **Validates: Requirements 8.2, 8.3, 8.4, 8.5**
    """
    rendered = render_report(report)

    # (a) Verification date in ISO 8601 format
    assert report.verification_date in rendered, (
        f"Verification date '{report.verification_date}' not found in rendered output"
    )

    # (b) AWS region and stack name
    assert report.environment.aws_region in rendered, (
        f"AWS region '{report.environment.aws_region}' not found in rendered output"
    )
    assert report.environment.stack_name in rendered, (
        f"Stack name '{report.environment.stack_name}' not found in rendered output"
    )

    # (c) Verifier name
    assert report.verifier.name in rendered, (
        f"Verifier name '{report.verifier.name}' not found in rendered output"
    )

    # (d) Each step: number, name, result badge
    for step in report.steps:
        assert str(step.step_number) in rendered, (
            f"Step number {step.step_number} not found in rendered output"
        )
        assert step.step_name in rendered, (
            f"Step name '{step.step_name}' not found in rendered output"
        )
        # Result badge should be present (one of ✅ 成功, ❌ 失敗, ⏭️ スキップ)
        result_badges = {
            "success": "✅ 成功",
            "failure": "❌ 失敗",
            "skipped": "⏭️ スキップ",
        }
        expected_badge = result_badges[step.result]
        assert expected_badge in rendered, (
            f"Result badge '{expected_badge}' for step {step.step_number} "
            f"not found in rendered output"
        )

        # Command in code block (if present)
        if step.command:
            assert step.command in rendered, (
                f"Command '{step.command}' for step {step.step_number} "
                f"not found in rendered output"
            )
            assert "```" in rendered, (
                "Code block markers not found in rendered output"
            )

        # Output (if present)
        if step.output:
            # Output may be truncated, but at least part of it should be present
            # Check first 50 chars of output are in rendered
            output_prefix = step.output[:50]
            assert output_prefix in rendered, (
                f"Output prefix '{output_prefix}' for step {step.step_number} "
                f"not found in rendered output"
            )

        # (e) Screenshot image link (if present)
        if step.screenshot_path:
            assert step.screenshot_path in rendered, (
                f"Screenshot path '{step.screenshot_path}' for step "
                f"{step.step_number} not found in rendered output"
            )
            # Check Markdown image link format ![...](path)
            assert f"]({step.screenshot_path})" in rendered, (
                f"Markdown image link for '{step.screenshot_path}' "
                f"not found in rendered output"
            )

    # (f) Issues section always present
    assert "問題" in rendered, (
        "Issues section header not found in rendered output"
    )


# --- Property 2: Empty issues list renders "問題なし" ---

# Feature: datadog-e2e-verification, Property 2: Empty issues list renders "問題なし"


@given(report=verification_report_no_issues_strategy())
@settings(max_examples=100)
def test_empty_issues_renders_mondainashi(report: VerificationReport) -> None:
    """Reports with empty issues list always contain "問題なし".

    For any valid VerificationReport where the issues list is empty,
    rendering to Markdown produces a document where the issues section
    contains the text "問題なし".

    **Validates: Requirements 8.6**
    """
    rendered = render_report(report)

    assert "問題なし" in rendered, (
        "Expected '問題なし' in rendered output for report with empty issues list"
    )


# --- Property 5: Bilingual comparison result summary completeness ---

# Feature: datadog-e2e-verification, Property 5: Bilingual comparison result summary completeness


@given(result=bilingual_comparison_result_strategy())
@settings(max_examples=100)
def test_bilingual_comparison_summary_completeness(
    result: BilingualComparisonResult,
) -> None:
    """Rendered bilingual summary contains all required fields.

    For any valid BilingualComparisonResult, rendering the summary to Markdown
    produces text that contains: the status ("pass" or "fail"), all compared
    file paths, the heading count, code block count, table count, and the
    number of differences found.

    **Validates: Requirements 9.5**
    """
    rendered = render_bilingual_summary(result)

    # Status
    assert result.status in rendered, (
        f"Status '{result.status}' not found in rendered summary"
    )

    # All file paths
    for ja_path, en_path in result.files_compared:
        assert ja_path in rendered, (
            f"Japanese file path '{ja_path}' not found in rendered summary"
        )
        assert en_path in rendered, (
            f"English file path '{en_path}' not found in rendered summary"
        )

    # Heading count
    assert str(result.heading_count) in rendered, (
        f"Heading count '{result.heading_count}' not found in rendered summary"
    )

    # Code block count
    assert str(result.code_block_count) in rendered, (
        f"Code block count '{result.code_block_count}' not found in rendered summary"
    )

    # Table count
    assert str(result.table_count) in rendered, (
        f"Table count '{result.table_count}' not found in rendered summary"
    )

    # Number of differences
    assert str(len(result.differences)) in rendered, (
        f"Difference count '{len(result.differences)}' not found in rendered summary"
    )
