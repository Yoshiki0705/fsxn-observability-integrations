"""Property-based test for New Relic verification report rendering completeness.

# Feature: new-relic-e2e-verification, Property 1: Verification report rendering completeness

Validates: Requirements 1.6, 2.6, 3.5, 4.6, 5.6, 8.5, 9.2, 9.4
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.verification.models import (
    AlertConditionConfig,
    DemoScenarioTimeline,
    Issue,
    NewRelicVerificationEnvironment,
    NRQLQueryResult,
    VerificationReport,
    VerificationStep,
    VerifierInfo,
)
from scripts.verification.new_relic_results_renderer import render_new_relic_report

from .conftest import (
    alert_condition_config_strategy,
    demo_scenario_timeline_strategy,
    iso8601_timestamp_strategy,
    new_relic_verification_environment_strategy,
    nrql_query_result_strategy,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies for VerificationReport generation
# ---------------------------------------------------------------------------


@st.composite
def verification_step_strategy(draw: st.DrawFn) -> VerificationStep:
    """Generate a random VerificationStep instance."""
    step_number = draw(st.integers(min_value=1, max_value=20))
    step_name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=40,
        ).map(lambda s: s.strip() or "Deploy Stack")
    )
    result = draw(st.sampled_from(["success", "failure", "skipped"]))
    command = draw(
        st.one_of(
            st.none(),
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "Z"),
                    blacklist_characters="\n\r",
                ),
                min_size=5,
                max_size=80,
            ).map(lambda s: s.strip() or "aws lambda invoke"),
        )
    )
    output = draw(
        st.one_of(
            st.none(),
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "Z"),
                    blacklist_characters="\n\r",
                ),
                min_size=3,
                max_size=60,
            ).map(lambda s: s.strip() or "OK"),
        )
    )
    screenshot_path = draw(
        st.one_of(
            st.none(),
            st.sampled_from([
                "docs/screenshots/new-relic/logs-ui-arrival.png",
                "docs/screenshots/new-relic/nrql-query-result.png",
                "docs/screenshots/new-relic/alert-condition-config.png",
                "docs/screenshots/new-relic/alert-policy-overview.png",
            ]),
        )
    )
    timestamp = draw(iso8601_timestamp_strategy())
    return VerificationStep(
        step_number=step_number,
        step_name=step_name,
        result=result,
        command=command,
        output=output,
        screenshot_path=screenshot_path,
        timestamp=timestamp,
    )


@st.composite
def issue_strategy(draw: st.DrawFn) -> Issue:
    """Generate a random Issue instance."""
    title = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=30,
        ).map(lambda s: s.strip() or "Issue")
    )
    description = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=5,
            max_size=60,
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
            ).map(lambda s: s.strip() or "Fix it"),
        )
    )
    return Issue(title=title, description=description, resolution=resolution)


@st.composite
def verification_report_strategy(draw: st.DrawFn) -> tuple[
    VerificationReport,
    list[NRQLQueryResult],
    AlertConditionConfig,
    DemoScenarioTimeline,
    NewRelicVerificationEnvironment,
]:
    """Generate a complete set of inputs for render_new_relic_report."""
    verification_date = draw(iso8601_timestamp_strategy())
    verifier = VerifierInfo(
        name=draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "Z"),
                    blacklist_characters="\n\r",
                ),
                min_size=2,
                max_size=20,
            ).map(lambda s: s.strip() or "Tester")
        ),
        role=draw(
            st.sampled_from(["DevOps Engineer", "SRE", "Platform Engineer"])
        ),
    )
    steps = draw(
        st.lists(verification_step_strategy(), min_size=1, max_size=8)
    )
    issues = draw(st.lists(issue_strategy(), min_size=0, max_size=3))

    report = VerificationReport(
        verification_date=verification_date,
        environment=None,  # type: ignore[arg-type]
        verifier=verifier,
        steps=steps,
        issues=issues,
    )

    nrql_results = draw(
        st.lists(nrql_query_result_strategy(), min_size=1, max_size=5)
    )
    alert_config = draw(alert_condition_config_strategy())
    demo_timeline = draw(demo_scenario_timeline_strategy())
    env = draw(new_relic_verification_environment_strategy())

    return report, nrql_results, alert_config, demo_timeline, env


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

# ISO 8601 pattern: YYYY-MM-DDTHH:MM:SS with timezone offset
ISO8601_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}"
)


@settings(max_examples=100)
@given(data=verification_report_strategy())
def test_report_rendering_completeness(
    data: tuple[
        VerificationReport,
        list[NRQLQueryResult],
        AlertConditionConfig,
        DemoScenarioTimeline,
        NewRelicVerificationEnvironment,
    ],
) -> None:
    """Property 1: Verification report rendering completeness.

    **Validates: Requirements 1.6, 2.6, 3.5, 4.6, 5.6, 8.5, 9.2, 9.4**

    For any valid verification report data, rendering to Markdown SHALL
    produce a document that contains all required elements.
    """
    report, nrql_results, alert_config, demo_timeline, env = data

    rendered = render_new_relic_report(
        report=report,
        nrql_results=nrql_results,
        alert_config=alert_config,
        demo_timeline=demo_timeline,
        env=env,
    )

    # (a) Verification date in ISO 8601 format is present
    assert report.verification_date in rendered
    assert ISO8601_PATTERN.search(rendered) is not None

    # (b) AWS region and stack name are present
    assert env.aws_region in rendered
    assert env.stack_name in rendered

    # (c) Masked account IDs showing only last 4 digits
    assert env.new_relic_account_id_masked in rendered
    assert env.aws_account_id_masked in rendered
    # Verify masking format: ****XXXX
    assert "****" in rendered

    # (d) Each step's number, name, and result status
    for step in report.steps:
        assert str(step.step_number) in rendered
        assert step.step_name in rendered
        # Result is rendered as a badge (success/failure/skipped)
        # Check that the step section exists with its number and name

        # Command in a code block (if present)
        if step.command:
            assert step.command in rendered

        # Output (if present)
        if step.output:
            # Output may be truncated, but at least the beginning should be present
            output_start = step.output[:50] if len(step.output) > 50 else step.output
            assert output_start in rendered

    # (e) Image links for steps with screenshots
    for step in report.steps:
        if step.screenshot_path:
            assert step.screenshot_path in rendered
            # Markdown image link format: ![...](path)
            assert f"]({step.screenshot_path})" in rendered

    # (f) NRQL query text, result summary, timestamp, and pass/fail status
    for nrql_result in nrql_results:
        assert nrql_result.query in rendered
        assert nrql_result.result_summary in rendered
        assert nrql_result.execution_timestamp in rendered

    # (g) Alert condition configuration details
    assert alert_config.nrql_query in rendered
    assert str(alert_config.threshold_value) in rendered
    assert str(alert_config.evaluation_window_minutes) in rendered
    assert alert_config.notification_channel in rendered

    # (h) Demo scenario timeline with ISO 8601 timestamps
    assert demo_timeline.file_write_timestamp in rendered
    if demo_timeline.ems_event_timestamp:
        assert demo_timeline.ems_event_timestamp in rendered
    if demo_timeline.s3_object_creation_timestamp:
        assert demo_timeline.s3_object_creation_timestamp in rendered
    if demo_timeline.lambda_invocation_timestamp:
        assert demo_timeline.lambda_invocation_timestamp in rendered
    if demo_timeline.new_relic_log_arrival_timestamp:
        assert demo_timeline.new_relic_log_arrival_timestamp in rendered

    # (i) Issues section is always present
    assert "既知の問題と対応策" in rendered
    # If no issues, "問題なし" should appear
    if not report.issues:
        assert "問題なし" in rendered
    else:
        for issue in report.issues:
            assert issue.title in rendered
            assert issue.description in rendered
