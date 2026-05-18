"""Property-based tests for report ID masking.

Uses Hypothesis to generate random AWS account IDs (12-digit strings)
and New Relic account IDs (numeric strings), then verifies that the
mask_account_id function and the full report renderer never expose
the full ID in the output.
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
from scripts.verification.new_relic_results_renderer import (
    mask_account_id,
    render_new_relic_report,
)


# --- Hypothesis strategies ---


@st.composite
def aws_account_id_strategy(draw: st.DrawFn) -> str:
    """Generate a random 12-digit AWS account ID string."""
    digits = draw(st.from_regex(r"[0-9]{12}", fullmatch=True))
    return digits


@st.composite
def new_relic_account_id_strategy(draw: st.DrawFn) -> str:
    """Generate a random numeric New Relic account ID (5-10 digits)."""
    length = draw(st.integers(min_value=5, max_value=10))
    digits = draw(
        st.text(
            alphabet="0123456789",
            min_size=length,
            max_size=length,
        )
    )
    return digits


# --- Property 2: Report ID masking ---

# Feature: new-relic-e2e-verification, Property 2: Report ID masking


@given(
    aws_account_id=aws_account_id_strategy(),
    nr_account_id=new_relic_account_id_strategy(),
)
@settings(max_examples=100)
def test_mask_account_id_hides_full_id(
    aws_account_id: str,
    nr_account_id: str,
) -> None:
    """mask_account_id shows only last 4 digits preceded by asterisks.

    For any AWS account ID (12-digit string) and New Relic account ID
    (numeric string), mask_account_id returns a string where:
    - The full ID never appears in the masked output
    - Only the last 4 digits are visible
    - The masked output starts with "****"

    **Validates: Requirements 9.3**
    """
    # Test AWS account ID masking
    masked_aws = mask_account_id(aws_account_id)
    assert aws_account_id not in masked_aws, (
        f"Full AWS account ID '{aws_account_id}' should not appear in "
        f"masked output '{masked_aws}'"
    )
    assert masked_aws == f"****{aws_account_id[-4:]}", (
        f"Expected '****{aws_account_id[-4:]}' but got '{masked_aws}'"
    )
    assert masked_aws.startswith("****"), (
        f"Masked ID should start with '****', got '{masked_aws}'"
    )

    # Test New Relic account ID masking
    masked_nr = mask_account_id(nr_account_id)
    assert nr_account_id not in masked_nr, (
        f"Full NR account ID '{nr_account_id}' should not appear in "
        f"masked output '{masked_nr}'"
    )
    assert masked_nr == f"****{nr_account_id[-4:]}", (
        f"Expected '****{nr_account_id[-4:]}' but got '{masked_nr}'"
    )
    assert masked_nr.startswith("****"), (
        f"Masked ID should start with '****', got '{masked_nr}'"
    )


@given(
    aws_account_id=aws_account_id_strategy(),
    nr_account_id=new_relic_account_id_strategy(),
)
@settings(max_examples=100)
def test_rendered_report_never_exposes_full_id(
    aws_account_id: str,
    nr_account_id: str,
) -> None:
    """Full unmasked IDs never appear in rendered report output.

    For any AWS account ID and New Relic account ID, when
    render_new_relic_report is called with an environment containing
    masked IDs, the full unmasked ID never appears in the output and
    only the last 4 digits preceded by asterisks are shown.

    **Validates: Requirements 9.3**
    """
    masked_aws = mask_account_id(aws_account_id)
    masked_nr = mask_account_id(nr_account_id)

    env = NewRelicVerificationEnvironment(
        aws_region="ap-northeast-1",
        stack_name="fsxn-new-relic-integration",
        lambda_function_name="fsxn-new-relic-integration-shipper",
        new_relic_region="US",
        new_relic_account_id_masked=masked_nr,
        aws_account_id_masked=masked_aws,
        fsx_file_system_id="fs-0123456789abcdef0",
    )

    report = VerificationReport(
        verification_date="2026-01-20T10:00:00+09:00",
        environment=None,  # type: ignore[arg-type]
        verifier=VerifierInfo(name="Test User", role="Engineer"),
        steps=[
            VerificationStep(
                step_number=1,
                step_name="Test Step",
                result="success",
                command="echo test",
                output="OK",
                timestamp="2026-01-20T10:00:00+09:00",
            ),
        ],
        issues=[],
    )

    nrql_results = [
        NRQLQueryResult(
            query="SELECT count(*) FROM Log WHERE source='fsxn-ontap'",
            result_summary="count: 10",
            row_count=1,
            first_rows=[{"count": "10"}],
            execution_timestamp="2026-01-20T10:30:00+09:00",
            status="pass",
            error_reason=None,
            retry_count=0,
        ),
    ]

    alert_config = AlertConditionConfig(
        nrql_query="SELECT count(*) FROM Log WHERE result='Failure'",
        threshold_value=1,
        evaluation_window_minutes=5,
        notification_channel="slack-alerts",
        test_trigger_timestamp=None,
        notification_receipt_timestamp=None,
    )

    demo_timeline = DemoScenarioTimeline(
        file_write_timestamp="2026-01-20T11:00:00+09:00",
        scenario_status="pass",
        last_successful_stage="new_relic_log_arrival",
    )

    rendered = render_new_relic_report(
        report=report,
        nrql_results=nrql_results,
        alert_config=alert_config,
        demo_timeline=demo_timeline,
        env=env,
    )

    # Full AWS account ID must NOT appear in rendered output
    assert aws_account_id not in rendered, (
        f"Full AWS account ID '{aws_account_id}' should never appear in "
        f"rendered report output"
    )

    # Full New Relic account ID must NOT appear in rendered output
    assert nr_account_id not in rendered, (
        f"Full NR account ID '{nr_account_id}' should never appear in "
        f"rendered report output"
    )

    # Masked versions SHOULD appear in rendered output
    assert masked_aws in rendered, (
        f"Masked AWS ID '{masked_aws}' should appear in rendered output"
    )
    assert masked_nr in rendered, (
        f"Masked NR ID '{masked_nr}' should appear in rendered output"
    )
