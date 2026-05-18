"""Data models for the E2E verification workflow.

Defines dataclasses representing verification steps, reports, environments,
bilingual comparison results, Markdown structural elements, and
vendor-specific models for Datadog and New Relic integrations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Heading:
    """A Markdown heading with level and text content."""

    level: int  # 1-6
    text: str


@dataclass
class Table:
    """A parsed Markdown table."""

    rows: list[list[str]]  # Including header row
    column_count: int


@dataclass
class MarkdownStructure:
    """Parsed structural elements of a Markdown document."""

    headings: list[Heading] = field(default_factory=list)
    code_blocks: list[str] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)


@dataclass
class VerificationStep:
    """A single verification step and its result."""

    step_number: int
    step_name: str
    result: Literal["success", "failure", "skipped"]
    command: str | None = None
    output: str | None = None
    screenshot_path: str | None = None
    error_detail: str | None = None
    timestamp: str = ""  # ISO 8601 format


@dataclass
class VerificationEnvironment:
    """AWS environment details."""

    aws_region: str
    stack_name: str
    lambda_function_name: str
    datadog_site: str


@dataclass
class VerifierInfo:
    """Information about the person performing verification."""

    name: str
    role: str


@dataclass
class BilingualDifference:
    """A single difference found between ja/en documents."""

    file_path_ja: str
    file_path_en: str
    section: str
    diff_type: Literal["heading", "code_block", "table"]
    expected: str
    actual: str


@dataclass
class BilingualComparisonResult:
    """Result of bilingual document comparison."""

    status: Literal["pass", "fail"]
    files_compared: list[tuple[str, str]] = field(default_factory=list)
    heading_count: int = 0
    code_block_count: int = 0
    table_count: int = 0
    differences: list[BilingualDifference] = field(default_factory=list)


@dataclass
class Issue:
    """An issue found during verification."""

    title: str
    description: str
    resolution: str | None = None


@dataclass
class VerificationReport:
    """Complete E2E verification report."""

    verification_date: str  # ISO 8601 with timezone
    environment: VerificationEnvironment
    verifier: VerifierInfo
    steps: list[VerificationStep] = field(default_factory=list)
    bilingual_comparison: BilingualComparisonResult = field(
        default_factory=lambda: BilingualComparisonResult(status="pass")
    )
    issues: list[Issue] = field(default_factory=list)


# ---------------------------------------------------------------------------
# New Relic-specific data models
# ---------------------------------------------------------------------------


@dataclass
class NewRelicVerificationEnvironment:
    """New Relic-specific environment details for E2E verification.

    Captures AWS infrastructure identifiers and New Relic account
    information needed to document the verification environment.
    """

    aws_region: str  # e.g., "ap-northeast-1"
    stack_name: str  # e.g., "fsxn-new-relic-integration"
    lambda_function_name: str  # e.g., "fsxn-new-relic-integration-shipper"
    new_relic_region: Literal["US", "EU"]
    new_relic_account_id_masked: str  # e.g., "****5678"
    aws_account_id_masked: str  # e.g., "****9012"
    fsx_file_system_id: str  # e.g., "fs-0123456789abcdef0"


@dataclass
class NRQLQueryResult:
    """Result of a single NRQL query execution.

    Records the query text, its outcome, and metadata for inclusion
    in the verification report.
    """

    query: str  # NRQL query text
    result_summary: str  # Numeric or tabular summary
    row_count: int  # Number of rows returned
    first_rows: list[dict[str, Any]]  # First 5 rows if applicable
    execution_timestamp: str  # ISO 8601
    status: Literal["pass", "fail"]
    error_reason: str | None = None
    retry_count: int = 0


@dataclass
class AlertConditionConfig:
    """Alert Condition configuration details.

    Captures the NRQL-based alert condition parameters and test
    execution timestamps for verification evidence.
    """

    nrql_query: str
    threshold_value: int
    evaluation_window_minutes: int
    notification_channel: str
    test_trigger_timestamp: str | None = None  # ISO 8601
    notification_receipt_timestamp: str | None = None  # ISO 8601


@dataclass
class DemoScenarioTimeline:
    """Execution timeline for Demo Scenario 3 (quota threshold exceeded).

    Records ISO 8601 timestamps for each stage of the end-to-end
    pipeline and failure information if the scenario does not complete.
    """

    file_write_timestamp: str  # ISO 8601
    scenario_status: Literal["pass", "fail"]
    ems_event_timestamp: str | None = None
    s3_object_creation_timestamp: str | None = None
    lambda_invocation_timestamp: str | None = None
    new_relic_log_arrival_timestamp: str | None = None
    last_successful_stage: str | None = None
    failing_stage: str | None = None
    elapsed_at_failure: float | None = None  # seconds


@dataclass
class LogAttributeValidation:
    """Validation result for a single log entry's attributes.

    Checks that mandatory attributes are present and non-empty,
    reporting any missing or empty fields.
    """

    entry_id: str
    mandatory_attributes: dict[str, str] = field(
        default_factory=dict
    )  # attribute_name → value
    missing_attributes: list[str] = field(
        default_factory=list
    )  # Attributes with empty values
    status: Literal["pass", "fail"] = "pass"
