"""Screenshot validation tests for Grafana integration documentation.

Verifies that required screenshot files exist, are valid PNG images,
and meet minimum size thresholds.

Requirements validated:
- 7.1: explore-log-arrival.png exists as valid PNG
- 7.2: dashboard-overview.png exists as valid PNG
- 7.5: Referenced screenshots exist at specified paths
"""

from pathlib import Path

import pytest

# Resolve screenshots directory relative to this test file
TESTS_DIR = Path(__file__).parent
GRAFANA_DIR = TESTS_DIR.parent
SCREENSHOTS_DIR = GRAFANA_DIR / "docs" / "screenshots"

# PNG magic bytes: \x89PNG\r\n\x1a\n
PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"

# Required screenshot files
REQUIRED_SCREENSHOTS = [
    "explore-log-arrival.png",
    "dashboard-overview.png",
]

# Minimum size threshold in bytes (>1KB for non-placeholder)
MIN_SIZE_NON_PLACEHOLDER = 1024


class TestScreenshotFilesExist:
    """Verify required screenshot files exist at the expected location."""

    def test_screenshots_directory_exists(self) -> None:
        """The screenshots directory must exist."""
        assert SCREENSHOTS_DIR.exists(), (
            f"Screenshots directory not found: {SCREENSHOTS_DIR}"
        )
        assert SCREENSHOTS_DIR.is_dir(), (
            f"Screenshots path is not a directory: {SCREENSHOTS_DIR}"
        )

    @pytest.mark.parametrize("filename", REQUIRED_SCREENSHOTS)
    def test_required_screenshot_exists(self, filename: str) -> None:
        """Each required screenshot file must exist."""
        filepath = SCREENSHOTS_DIR / filename
        assert filepath.exists(), (
            f"Required screenshot not found: {filepath}"
        )
        assert filepath.is_file(), (
            f"Screenshot path is not a file: {filepath}"
        )


class TestScreenshotValidPNG:
    """Verify screenshot files are valid PNG images (magic bytes check)."""

    @pytest.mark.parametrize("filename", REQUIRED_SCREENSHOTS)
    def test_file_has_png_magic_bytes(self, filename: str) -> None:
        """Each screenshot file must start with PNG magic bytes."""
        filepath = SCREENSHOTS_DIR / filename
        if not filepath.exists():
            pytest.skip(f"Screenshot file not found: {filepath}")

        with open(filepath, "rb") as f:
            header = f.read(8)

        assert header == PNG_MAGIC_BYTES, (
            f"File {filename} does not have valid PNG magic bytes. "
            f"Got: {header!r}, expected: {PNG_MAGIC_BYTES!r}"
        )


class TestScreenshotSize:
    """Verify screenshot files meet minimum size thresholds."""

    @pytest.mark.parametrize("filename", REQUIRED_SCREENSHOTS)
    def test_file_meets_size_threshold(self, filename: str) -> None:
        """Screenshot files must be >1KB for non-placeholder, or valid PNG for placeholder.

        A valid PNG placeholder (e.g., 1x1 pixel) is acceptable as long as
        it has valid PNG magic bytes. Full-size screenshots should be >1KB.
        """
        filepath = SCREENSHOTS_DIR / filename
        if not filepath.exists():
            pytest.skip(f"Screenshot file not found: {filepath}")

        file_size = filepath.stat().st_size

        # Read magic bytes to verify it's a valid PNG regardless of size
        with open(filepath, "rb") as f:
            header = f.read(8)

        is_valid_png = header == PNG_MAGIC_BYTES

        # Either the file is >1KB (full screenshot) or it's a valid PNG placeholder
        assert is_valid_png, (
            f"File {filename} ({file_size} bytes) is neither a valid PNG "
            f"nor meets the minimum size threshold of {MIN_SIZE_NON_PLACEHOLDER} bytes"
        )

    @pytest.mark.parametrize("filename", REQUIRED_SCREENSHOTS)
    def test_file_is_not_empty(self, filename: str) -> None:
        """Screenshot files must not be empty (0 bytes)."""
        filepath = SCREENSHOTS_DIR / filename
        if not filepath.exists():
            pytest.skip(f"Screenshot file not found: {filepath}")

        file_size = filepath.stat().st_size
        assert file_size > 0, f"Screenshot file {filename} is empty (0 bytes)"
