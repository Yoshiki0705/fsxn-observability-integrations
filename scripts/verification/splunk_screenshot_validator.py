"""Screenshot validation for the Splunk E2E verification workflow.

Validates that required screenshots exist in the expected directory,
meet file size constraints, are valid PNG files, and follow the
naming convention: splunk-<description>-<YYYYMMDD>.png.

Also runnable as CLI:
    python splunk_screenshot_validator.py <directory>
"""

from __future__ import annotations

import os
import re
import sys

# Support both package import and direct CLI execution
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.verification.splunk_models import VerificationStep  # noqa: E402

PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"

MAX_FILE_SIZE_BYTES = 512000  # 500KB

NAMING_PATTERN = re.compile(r"^splunk-[a-z0-9-]{3,40}-\d{8}\.png$")

# Required screenshot categories: each tuple is (category_name, keywords)
# A file matches a category if any keyword appears in the filename.
REQUIRED_CATEGORIES = [
    ("CloudWatch/Lambda logs", ("cloudwatch", "lambda")),
    ("Splunk Search results", ("search",)),
    ("Splunk Dashboard", ("dashboard",)),
]


def validate_screenshots(screenshot_dir: str) -> list[VerificationStep]:
    """Validate Splunk screenshot evidence.

    Checks:
    - 3 required PNG files exist (one per category)
    - Each file ≤ 500KB
    - Each file starts with PNG magic bytes
    - Naming convention: splunk-<description>-<YYYYMMDD>.png

    Args:
        screenshot_dir: Path to the directory containing screenshot files.

    Returns:
        A list of VerificationStep instances, one per validation check.
    """
    results: list[VerificationStep] = []
    step_number = 0

    # Check directory exists
    if not os.path.isdir(screenshot_dir):
        step_number += 1
        results.append(VerificationStep(
            step_number=step_number,
            step_name="Screenshot directory exists",
            result="fail",
            command=f"ls {screenshot_dir}",
            output=f"Directory not found: {screenshot_dir}",
        ))
        return results

    # List PNG files in directory
    try:
        all_files = os.listdir(screenshot_dir)
    except OSError as e:
        step_number += 1
        results.append(VerificationStep(
            step_number=step_number,
            step_name="List screenshot directory",
            result="fail",
            command=f"ls {screenshot_dir}",
            output=f"Failed to list directory: {e}",
        ))
        return results

    png_files = [f for f in all_files if f.endswith(".png")]

    # Check required categories exist
    for category_name, keywords in REQUIRED_CATEGORIES:
        step_number += 1
        matching = [
            f for f in png_files
            if any(kw in f for kw in keywords)
        ]
        if matching:
            results.append(VerificationStep(
                step_number=step_number,
                step_name=f"Required screenshot exists: {category_name}",
                result="pass",
                command=f"find {screenshot_dir} -name '*{keywords[0]}*'",
                output=f"Found: {', '.join(matching)}",
                screenshot=os.path.join(screenshot_dir, matching[0]),
            ))
        else:
            results.append(VerificationStep(
                step_number=step_number,
                step_name=f"Required screenshot exists: {category_name}",
                result="fail",
                command=f"find {screenshot_dir} -name '*{keywords[0]}*'",
                output=(
                    f"No file matching keywords {keywords} found. "
                    f"Available files: {png_files}"
                ),
            ))

    # Validate each PNG file individually
    for filename in png_files:
        filepath = os.path.join(screenshot_dir, filename)

        # Validate naming convention
        step_number += 1
        if NAMING_PATTERN.match(filename):
            results.append(VerificationStep(
                step_number=step_number,
                step_name=f"Naming convention: {filename}",
                result="pass",
                command=f"echo '{filename}' | grep -P '{NAMING_PATTERN.pattern}'",
                output=f"Filename matches pattern: {NAMING_PATTERN.pattern}",
                screenshot=filepath,
            ))
        else:
            results.append(VerificationStep(
                step_number=step_number,
                step_name=f"Naming convention: {filename}",
                result="fail",
                command=f"echo '{filename}' | grep -P '{NAMING_PATTERN.pattern}'",
                output=(
                    f"Filename '{filename}' does not match required pattern: "
                    f"{NAMING_PATTERN.pattern}"
                ),
                screenshot=filepath,
            ))

        # Validate file size
        step_number += 1
        try:
            file_size = os.path.getsize(filepath)
        except OSError as e:
            results.append(VerificationStep(
                step_number=step_number,
                step_name=f"File size check: {filename}",
                result="fail",
                command=f"stat {filepath}",
                output=f"Failed to get file size: {e}",
                screenshot=filepath,
            ))
            continue

        if file_size <= MAX_FILE_SIZE_BYTES:
            results.append(VerificationStep(
                step_number=step_number,
                step_name=f"File size check: {filename}",
                result="pass",
                command=f"stat {filepath}",
                output=f"Size: {file_size} bytes (max: {MAX_FILE_SIZE_BYTES})",
                screenshot=filepath,
            ))
        else:
            results.append(VerificationStep(
                step_number=step_number,
                step_name=f"File size check: {filename}",
                result="fail",
                command=f"stat {filepath}",
                output=(
                    f"File too large: {file_size} bytes "
                    f"(max: {MAX_FILE_SIZE_BYTES} bytes)"
                ),
                screenshot=filepath,
            ))

        # Validate PNG magic bytes
        step_number += 1
        try:
            with open(filepath, "rb") as f:
                header = f.read(8)
        except OSError as e:
            results.append(VerificationStep(
                step_number=step_number,
                step_name=f"PNG format check: {filename}",
                result="fail",
                command=f"xxd -l 8 {filepath}",
                output=f"Failed to read file: {e}",
                screenshot=filepath,
            ))
            continue

        if header[:8] == PNG_MAGIC_BYTES:
            results.append(VerificationStep(
                step_number=step_number,
                step_name=f"PNG format check: {filename}",
                result="pass",
                command=f"xxd -l 8 {filepath}",
                output="File starts with valid PNG magic bytes",
                screenshot=filepath,
            ))
        else:
            results.append(VerificationStep(
                step_number=step_number,
                step_name=f"PNG format check: {filename}",
                result="fail",
                command=f"xxd -l 8 {filepath}",
                output="File does not start with PNG magic bytes (\\x89PNG\\r\\n\\x1a\\n)",
                screenshot=filepath,
            ))

    return results


def main() -> None:
    """CLI entry point for screenshot validation.

    Usage:
        python splunk_screenshot_validator.py <directory>
    """
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <screenshot_directory>", file=sys.stderr)
        sys.exit(1)

    screenshot_dir = sys.argv[1]
    steps = validate_screenshots(screenshot_dir)

    # Print results
    pass_count = 0
    fail_count = 0

    for step in steps:
        icon = "✅" if step.result == "pass" else "❌"
        print(f"{icon} Step {step.step_number}: {step.step_name}")
        if step.output:
            print(f"   {step.output}")
        if step.result == "pass":
            pass_count += 1
        else:
            fail_count += 1

    print(f"\nSummary: {pass_count} passed, {fail_count} failed")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
