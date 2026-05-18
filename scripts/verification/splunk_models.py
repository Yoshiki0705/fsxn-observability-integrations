"""Data models for the Splunk E2E verification workflow.

Defines dataclasses for verification steps and reports specific to
the Splunk serverless integration verification pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class VerificationStep:
    """A single verification step and its result.

    Represents one step in the E2E verification pipeline, capturing
    the command executed, its output, and the pass/fail/skip result.

    Attributes:
        step_number: Sequential step number in the verification pipeline.
        step_name: Human-readable name describing the verification step.
        result: Outcome of the step execution.
        command: Shell command or API call executed (None if manual step).
        output: Command output or observed result (None if not captured).
        screenshot: Path to screenshot evidence file (None if not applicable).
    """

    step_number: int
    step_name: str
    result: Literal["pass", "fail", "skip"]
    command: str | None = None
    output: str | None = None
    screenshot: str | None = None


@dataclass
class VerificationReport:
    """Complete Splunk E2E verification report.

    Aggregates all verification steps, environment details, timing
    measurements, and issues discovered during the verification run.

    Attributes:
        verification_date: ISO 8601 timestamp of the verification run.
        environment: AWS and Splunk environment configuration details.
        steps: Ordered list of verification steps executed.
        latency_seconds: Measured end-to-end latency from S3 object
            creation to Splunk searchability (None if not measured).
        issues: List of issues or observations found during verification.
    """

    verification_date: str
    environment: dict[str, Any]
    steps: list[VerificationStep] = field(default_factory=list)
    latency_seconds: float | None = None
    issues: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Generate a summary of the verification report.

        Returns:
            Dictionary with pass/fail/skip counts and overall status.
        """
        pass_count = sum(1 for s in self.steps if s.result == "pass")
        fail_count = sum(1 for s in self.steps if s.result == "fail")
        skip_count = sum(1 for s in self.steps if s.result == "skip")

        return {
            "verification_date": self.verification_date,
            "total_steps": len(self.steps),
            "passed": pass_count,
            "failed": fail_count,
            "skipped": skip_count,
            "overall_result": "pass" if fail_count == 0 else "fail",
            "latency_seconds": self.latency_seconds,
            "issue_count": len(self.issues),
        }
