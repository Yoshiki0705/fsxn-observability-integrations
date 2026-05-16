"""Screenshot validation for the Datadog E2E verification workflow.

Validates that all required screenshots exist in the expected directory,
meet minimum file size requirements, and are valid PNG files.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from scripts.verification.models import VerificationStep

REQUIRED_SCREENSHOTS = [
    "datadog-logs-arrival.png",
    "datadog-pipeline-config.png",
    "datadog-facets-config.png",
    "datadog-dashboard.png",
    "datadog-unauthorized-access.png",
]

PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"

MIN_FILE_SIZE_BYTES = 1024  # 1KB


def validate_screenshots(screenshot_dir: str) -> list[VerificationStep]:
    """Validate all required screenshots exist and are valid PNG files.

    Checks each required screenshot file for:
    1. Existence in the specified directory
    2. Minimum file size (>= 1KB)
    3. Valid PNG magic bytes in the file header

    Args:
        screenshot_dir: Path to the directory containing screenshot files.

    Returns:
        A list of VerificationStep instances, one per required screenshot,
        with result="success" if all checks pass or result="failure" with
        error details if any check fails.
    """
    results: list[VerificationStep] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    for step_number, filename in enumerate(REQUIRED_SCREENSHOTS, start=1):
        filepath = os.path.join(screenshot_dir, filename)
        step = _validate_single_screenshot(step_number, filename, filepath, timestamp)
        results.append(step)

    return results


def _validate_single_screenshot(
    step_number: int,
    filename: str,
    filepath: str,
    timestamp: str,
) -> VerificationStep:
    """Validate a single screenshot file.

    Args:
        step_number: The step number for this validation.
        filename: The expected filename of the screenshot.
        filepath: The full path to the screenshot file.
        timestamp: ISO 8601 timestamp for the verification step.

    Returns:
        A VerificationStep with the validation result.
    """
    step_name = f"Screenshot validation: {filename}"

    # Check existence
    if not os.path.exists(filepath):
        return VerificationStep(
            step_number=step_number,
            step_name=step_name,
            result="failure",
            screenshot_path=filepath,
            error_detail=f"File not found: {filepath}",
            timestamp=timestamp,
        )

    # Check file size
    file_size = os.path.getsize(filepath)
    if file_size < MIN_FILE_SIZE_BYTES:
        return VerificationStep(
            step_number=step_number,
            step_name=step_name,
            result="failure",
            screenshot_path=filepath,
            error_detail=(
                f"File too small: {file_size} bytes "
                f"(minimum {MIN_FILE_SIZE_BYTES} bytes)"
            ),
            timestamp=timestamp,
        )

    # Check PNG magic bytes
    try:
        with open(filepath, "rb") as f:
            header = f.read(8)
    except OSError as e:
        return VerificationStep(
            step_number=step_number,
            step_name=step_name,
            result="failure",
            screenshot_path=filepath,
            error_detail=f"Failed to read file: {e}",
            timestamp=timestamp,
        )

    if header != PNG_MAGIC_BYTES:
        return VerificationStep(
            step_number=step_number,
            step_name=step_name,
            result="failure",
            screenshot_path=filepath,
            error_detail=(
                f"Invalid PNG format: file does not start with PNG magic bytes"
            ),
            timestamp=timestamp,
        )

    # All checks passed
    return VerificationStep(
        step_number=step_number,
        step_name=step_name,
        result="success",
        screenshot_path=filepath,
        timestamp=timestamp,
    )
