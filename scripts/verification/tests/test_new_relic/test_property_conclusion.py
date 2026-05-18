"""Property test for report conclusion correctness.

# Feature: new-relic-e2e-verification, Property 3: Report conclusion correctness

Validates that the conclusion section of the rendered New Relic verification
report correctly reflects the pass/fail status of all verification steps:
- All steps pass → conclusion contains "本番環境利用可能"
- At least one step fails → conclusion contains "本番環境利用不可" and lists
  the step number of each failed step

**Validates: Requirements 9.5, 9.6**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.verification.models import (
    AlertConditionConfig,
    DemoScenarioTimeline,
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
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def verification_step_strategy(
    draw: st.DrawFn,
    *,
    result: str | None = None,
) -> VerificationStep:
    """Generate a random VerificationStep with an optional fixed result."""
    step_number = draw(st.integers(min_value=1, max_value=20))
    step_name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z"),
                blacklist_characters="\n\r",
            ),
            min_size=3,
            max_size=30,
        ).map(lambda s: s.strip() or "Test Step")
    )
    step_result = result or draw(st.sampled_from(["success", "failure"]))
    command = draw(st.one_of(st.none(), st.just("aws lambda invoke --function-name test")))
    output = draw(st.one_of(st.none(), st.just("OK")))
    timestamp = draw(iso8601_timestamp_strategy())
    return VerificationStep(
        step_number=step_number,
        step_name=step_name,
        result=step_result,
        command=command,
        output=output,
        timestamp=timestamp,
    )


@st.composite
def all_pass_report_strategy(draw: st.DrawFn) -> tuple[
    VerificationReport,
    list[NRQLQueryResult],
    AlertConditionConfig,
    DemoScenarioTimeline,
    NewRelicVerificationEnvironment,
]:
    """Generate a report where ALL steps have result='success'."""
    num_steps = draw(st.integers(min_value=1, max_value=10))
    steps = [draw(verification_step_strategy(result="success")) for _ in range(num_steps)]

    report = VerificationReport(
        verification_date=draw(iso8601_timestamp_strategy()),
        environment=None,  # type: ignore[arg-type]
        verifier=VerifierInfo(
            name=draw(st.text(min_size=2, max_size=10).map(lambda s: s.strip() or "Tester")),
            role=draw(st.text(min_size=2, max_size=10).map(lambda s: s.strip() or "Engineer")),
        ),
        steps=steps,
        issues=[],
    )

    nrql_results = draw(st.lists(nrql_query_result_strategy(), min_size=0, max_size=3))
    alert_config = draw(alert_condition_config_strategy())
    demo_timeline = draw(demo_scenario_timeline_strategy())
    env = draw(new_relic_verification_environment_strategy())

    return report, nrql_results, alert_config, demo_timeline, env


@st.composite
def some_fail_report_strategy(draw: st.DrawFn) -> tuple[
    VerificationReport,
    list[NRQLQueryResult],
    AlertConditionConfig,
    DemoScenarioTimeline,
    NewRelicVerificationEnvironment,
]:
    """Generate a report where at least one step has result='failure'."""
    # Generate at least one failure step
    num_fail = draw(st.integers(min_value=1, max_value=5))
    num_pass = draw(st.integers(min_value=0, max_value=5))

    fail_steps = [draw(verification_step_strategy(result="failure")) for _ in range(num_fail)]
    pass_steps = [draw(verification_step_strategy(result="success")) for _ in range(num_pass)]

    # Combine and assign unique step numbers
    all_steps = fail_steps + pass_steps
    draw(st.randoms(use_true_random=False)).shuffle(all_steps)
    for i, step in enumerate(all_steps, start=1):
        step.step_number = i

    report = VerificationReport(
        verification_date=draw(iso8601_timestamp_strategy()),
        environment=None,  # type: ignore[arg-type]
        verifier=VerifierInfo(
            name=draw(st.text(min_size=2, max_size=10).map(lambda s: s.strip() or "Tester")),
            role=draw(st.text(min_size=2, max_size=10).map(lambda s: s.strip() or "Engineer")),
        ),
        steps=all_steps,
        issues=[],
    )

    nrql_results = draw(st.lists(nrql_query_result_strategy(), min_size=0, max_size=3))
    alert_config = draw(alert_condition_config_strategy())
    demo_timeline = draw(demo_scenario_timeline_strategy())
    env = draw(new_relic_verification_environment_strategy())

    return report, nrql_results, alert_config, demo_timeline, env


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(data=all_pass_report_strategy())
@settings(max_examples=100)
def test_all_pass_conclusion_contains_production_ready(
    data: tuple[
        VerificationReport,
        list[NRQLQueryResult],
        AlertConditionConfig,
        DemoScenarioTimeline,
        NewRelicVerificationEnvironment,
    ],
) -> None:
    """All steps pass → conclusion contains "本番環境利用可能".

    # Feature: new-relic-e2e-verification, Property 3: Report conclusion correctness
    **Validates: Requirements 9.5, 9.6**
    """
    report, nrql_results, alert_config, demo_timeline, env = data

    output = render_new_relic_report(report, nrql_results, alert_config, demo_timeline, env)

    assert "本番環境利用可能" in output
    # The conclusion section should NOT contain the not-production-ready text.
    # Extract the conclusion section (after "## 結論") to avoid false positives
    # from randomly generated step names containing "不可".
    conclusion_section = output.split("## 結論")[-1] if "## 結論" in output else output
    assert "本番環境利用不可" not in conclusion_section


@given(data=some_fail_report_strategy())
@settings(max_examples=100)
def test_some_fail_conclusion_contains_not_production_ready(
    data: tuple[
        VerificationReport,
        list[NRQLQueryResult],
        AlertConditionConfig,
        DemoScenarioTimeline,
        NewRelicVerificationEnvironment,
    ],
) -> None:
    """At least one fail → conclusion contains "本番環境利用不可" and lists failed step numbers.

    # Feature: new-relic-e2e-verification, Property 3: Report conclusion correctness
    **Validates: Requirements 9.5, 9.6**
    """
    report, nrql_results, alert_config, demo_timeline, env = data

    output = render_new_relic_report(report, nrql_results, alert_config, demo_timeline, env)

    # Must contain not-production-ready text
    assert "本番環境利用不可" in output

    # Must list each failed step number
    failed_steps = [s for s in report.steps if s.result == "failure"]
    assert len(failed_steps) >= 1

    for step in failed_steps:
        assert f"ステップ {step.step_number}" in output
