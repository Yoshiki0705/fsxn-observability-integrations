"""Tests for bilingual comparator with New Relic setup guide paths.

Verifies that the bilingual comparator correctly handles New Relic
integration paths and produces correct exit codes for matching and
mismatched document structures.

Validates: Requirements 7.2, 7.3, 7.5
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.verification.bilingual_comparator import compare_setup_guides

# Path to test data fixtures
TEST_DATA_DIR = Path(__file__).parent / "test_data"
JA_MATCHING = TEST_DATA_DIR / "ja_setup_guide_matching.md"
EN_MATCHING = TEST_DATA_DIR / "en_setup_guide_matching.md"
EN_MISMATCHED = TEST_DATA_DIR / "en_setup_guide_mismatched.md"

# Path to the CLI entry point
COMPARE_SCRIPT = Path(__file__).parents[3] / "compare-bilingual.py"


class TestBilingualComparatorNewRelicPaths:
    """Test bilingual comparator with New Relic-specific file paths."""

    def test_matching_new_relic_guides_return_pass(self) -> None:
        """Matching ja/en New Relic setup guides return status pass."""
        result = compare_setup_guides(str(JA_MATCHING), str(EN_MATCHING))

        assert result.status == "pass"
        assert result.differences == []
        assert result.heading_count > 0
        assert result.code_block_count > 0
        assert result.table_count > 0

    def test_mismatched_new_relic_guides_return_fail(self) -> None:
        """Mismatched ja/en New Relic setup guides return status fail."""
        result = compare_setup_guides(str(JA_MATCHING), str(EN_MISMATCHED))

        assert result.status == "fail"
        assert len(result.differences) >= 1
        # Should detect code block content difference
        code_block_diffs = [
            d for d in result.differences if d.diff_type == "code_block"
        ]
        assert len(code_block_diffs) >= 1

    def test_matching_guides_have_correct_counts(self) -> None:
        """Matching guides report correct heading, code block, and table counts."""
        result = compare_setup_guides(str(JA_MATCHING), str(EN_MATCHING))

        # Both fixtures have: 5 headings (h1 + h2*3 + h3*2 = actually count them)
        # # (h1), ## (h2), ### (h3), ### (h3), ## (h2), ## (h2) = 6 headings
        assert result.heading_count >= 5
        # Code blocks: bash (secretsmanager), bash (cfn deploy), json, sql = 4
        assert result.code_block_count == 4
        # Tables: 1 parameter table
        assert result.table_count == 1

    def test_nonexistent_new_relic_path_returns_fail(self) -> None:
        """Non-existent New Relic path returns fail with FileNotFoundError."""
        nonexistent = "integrations/new-relic/docs/ja/nonexistent-guide.md"

        result = compare_setup_guides(nonexistent, str(EN_MATCHING))

        assert result.status == "fail"
        assert len(result.differences) >= 1
        assert "FileNotFoundError" in result.differences[0].actual


class TestBilingualComparatorCLINewRelic:
    """Test the CLI entry point with New Relic paths."""

    def test_cli_exit_code_0_for_matching_structures(self) -> None:
        """CLI returns exit code 0 when ja/en structures match."""
        result = subprocess.run(
            [
                sys.executable,
                str(COMPARE_SCRIPT),
                "--ja",
                str(JA_MATCHING),
                "--en",
                str(EN_MATCHING),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_cli_exit_code_1_for_mismatched_structures(self) -> None:
        """CLI returns exit code 1 when ja/en structures differ."""
        result = subprocess.run(
            [
                sys.executable,
                str(COMPARE_SCRIPT),
                "--ja",
                str(JA_MATCHING),
                "--en",
                str(EN_MISMATCHED),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "FAIL" in result.stdout
        assert "Differences" in result.stdout

    def test_cli_accepts_new_relic_style_paths(self) -> None:
        """CLI accepts paths in the format used for New Relic integration."""
        # Verify the CLI accepts --ja and --en arguments with New Relic paths
        # The actual setup guide files exist, so this should run successfully
        result = subprocess.run(
            [
                sys.executable,
                str(COMPARE_SCRIPT),
                "--ja",
                "integrations/new-relic/docs/ja/setup-guide.md",
                "--en",
                "integrations/new-relic/docs/en/setup-guide.md",
            ],
            capture_output=True,
            text=True,
        )

        # CLI should not crash — it should produce output with status
        assert result.returncode in (0, 1)
        assert "Status:" in result.stdout
        assert "Files compared:" in result.stdout

    def test_cli_nonexistent_paths_report_failure(self) -> None:
        """CLI reports failure for non-existent New Relic paths."""
        result = subprocess.run(
            [
                sys.executable,
                str(COMPARE_SCRIPT),
                "--ja",
                "integrations/new-relic/docs/ja/nonexistent.md",
                "--en",
                "integrations/new-relic/docs/en/nonexistent.md",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "FAIL" in result.stdout
        assert "FileNotFoundError" in result.stdout

    def test_cli_output_includes_file_paths(self) -> None:
        """CLI output includes the compared file paths."""
        result = subprocess.run(
            [
                sys.executable,
                str(COMPARE_SCRIPT),
                "--ja",
                str(JA_MATCHING),
                "--en",
                str(EN_MATCHING),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "JA:" in result.stdout
        assert "EN:" in result.stdout
