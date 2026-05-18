"""Unit tests for the New Relic screenshot validator.

Tests validate_new_relic_screenshots function for correct detection of
missing files, oversized files, undersized files, invalid PNG format,
and successful validation of valid files.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
"""

from __future__ import annotations

from pathlib import Path

from scripts.verification.screenshot_validator import (
    MAX_FILE_SIZE_BYTES,
    MIN_FILE_SIZE_BYTES,
    NEW_RELIC_REQUIRED_SCREENSHOTS,
    PNG_MAGIC_BYTES,
    validate_new_relic_screenshots,
)


def _create_valid_png(path: Path) -> None:
    """Create a valid PNG file that exceeds MIN_FILE_SIZE_BYTES."""
    padding = b"\x00" * (MIN_FILE_SIZE_BYTES - len(PNG_MAGIC_BYTES))
    path.write_bytes(PNG_MAGIC_BYTES + padding)


class TestAllFilesValidPass:
    """Test that all 4 valid PNG files produce success results."""

    def test_all_results_are_success(self, tmp_path: Path) -> None:
        """All required screenshots present and valid → all results success."""
        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        assert len(results) == len(NEW_RELIC_REQUIRED_SCREENSHOTS)
        for step in results:
            assert step.result == "success"

    def test_returns_correct_number_of_steps(self, tmp_path: Path) -> None:
        """Returns exactly one VerificationStep per required screenshot."""
        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        assert len(results) == 4

    def test_step_numbers_are_sequential(self, tmp_path: Path) -> None:
        """Step numbers are sequential starting from 1."""
        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        for i, step in enumerate(results, start=1):
            assert step.step_number == i

    def test_step_names_contain_filenames(self, tmp_path: Path) -> None:
        """Each step name contains the corresponding filename."""
        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        for step, filename in zip(results, NEW_RELIC_REQUIRED_SCREENSHOTS):
            assert filename in step.step_name


class TestMissingFile:
    """Test that a missing file produces a failure with 'File not found'."""

    def test_missing_file_reports_failure(self, tmp_path: Path) -> None:
        """Missing file → result='failure' with 'File not found' in error_detail."""
        # Create all files except the first one
        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS[1:]:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        missing_step = results[0]
        assert missing_step.result == "failure"
        assert "File not found" in missing_step.error_detail

    def test_missing_file_error_includes_filename(self, tmp_path: Path) -> None:
        """Error detail includes the missing filename path."""
        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS[1:]:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        missing_step = results[0]
        assert NEW_RELIC_REQUIRED_SCREENSHOTS[0] in missing_step.error_detail

    def test_missing_file_does_not_affect_others(self, tmp_path: Path) -> None:
        """Other valid files still report success when one is missing."""
        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS[1:]:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        for step in results[1:]:
            assert step.result == "success"


class TestFileTooLarge:
    """Test that a file larger than MAX_FILE_SIZE_BYTES reports failure."""

    def test_large_file_reports_failure(self, tmp_path: Path) -> None:
        """File too large → result='failure' with 'too large' in error_detail."""
        # Create a file exceeding 500KB
        large_content = PNG_MAGIC_BYTES + b"\x00" * MAX_FILE_SIZE_BYTES
        (tmp_path / NEW_RELIC_REQUIRED_SCREENSHOTS[0]).write_bytes(large_content)

        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS[1:]:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        large_step = results[0]
        assert large_step.result == "failure"
        assert "too large" in large_step.error_detail

    def test_large_file_error_includes_size(self, tmp_path: Path) -> None:
        """Error detail includes the actual file size."""
        large_content = PNG_MAGIC_BYTES + b"\x00" * MAX_FILE_SIZE_BYTES
        (tmp_path / NEW_RELIC_REQUIRED_SCREENSHOTS[0]).write_bytes(large_content)

        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS[1:]:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        large_step = results[0]
        expected_size = str(len(large_content))
        assert expected_size in large_step.error_detail


class TestFileTooSmall:
    """Test that a file smaller than MIN_FILE_SIZE_BYTES reports failure."""

    def test_small_file_reports_failure(self, tmp_path: Path) -> None:
        """File too small → result='failure' with 'too small' in error_detail."""
        # Create a file with valid PNG header but under 1KB
        small_content = PNG_MAGIC_BYTES + b"\x00" * 92  # 100 bytes total
        (tmp_path / NEW_RELIC_REQUIRED_SCREENSHOTS[0]).write_bytes(small_content)

        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS[1:]:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        small_step = results[0]
        assert small_step.result == "failure"
        assert "too small" in small_step.error_detail

    def test_small_file_error_includes_size(self, tmp_path: Path) -> None:
        """Error detail includes the actual file size."""
        small_content = PNG_MAGIC_BYTES + b"\x00" * 92  # 100 bytes total
        (tmp_path / NEW_RELIC_REQUIRED_SCREENSHOTS[0]).write_bytes(small_content)

        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS[1:]:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        small_step = results[0]
        assert "100" in small_step.error_detail


class TestWrongFormat:
    """Test that a non-PNG file reports failure with 'Invalid PNG'."""

    def test_wrong_format_reports_failure(self, tmp_path: Path) -> None:
        """Wrong format → result='failure' with 'Invalid PNG' in error_detail."""
        # Create a file with JPEG-like header but large enough
        jpeg_header = b"\xff\xd8\xff\xe0"
        fake_jpeg = jpeg_header + b"\x00" * (MIN_FILE_SIZE_BYTES - len(jpeg_header))
        (tmp_path / NEW_RELIC_REQUIRED_SCREENSHOTS[0]).write_bytes(fake_jpeg)

        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS[1:]:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        wrong_format_step = results[0]
        assert wrong_format_step.result == "failure"
        assert "Invalid PNG" in wrong_format_step.error_detail

    def test_text_file_reports_invalid_png(self, tmp_path: Path) -> None:
        """A text file large enough still fails PNG validation."""
        text_content = b"This is not a PNG file\n" * 100  # well over 1KB
        (tmp_path / NEW_RELIC_REQUIRED_SCREENSHOTS[0]).write_bytes(text_content)

        for filename in NEW_RELIC_REQUIRED_SCREENSHOTS[1:]:
            _create_valid_png(tmp_path / filename)

        results = validate_new_relic_screenshots(str(tmp_path))

        wrong_format_step = results[0]
        assert wrong_format_step.result == "failure"
        assert "Invalid PNG" in wrong_format_step.error_detail


class TestEmptyDirectory:
    """Test that an empty directory reports all 4 files as failure."""

    def test_all_results_are_failure(self, tmp_path: Path) -> None:
        """Empty directory → all 4 results are 'failure'."""
        results = validate_new_relic_screenshots(str(tmp_path))

        assert len(results) == 4
        for step in results:
            assert step.result == "failure"

    def test_all_errors_mention_file_not_found(self, tmp_path: Path) -> None:
        """All error details mention 'File not found'."""
        results = validate_new_relic_screenshots(str(tmp_path))

        for step in results:
            assert "File not found" in step.error_detail
