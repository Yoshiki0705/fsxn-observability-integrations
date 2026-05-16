"""Data models for the Datadog E2E verification workflow.

Defines dataclasses representing verification steps, reports, environments,
bilingual comparison results, and Markdown structural elements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


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
