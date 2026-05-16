"""Unit tests for the bilingual comparator module.

Tests structural comparison of Japanese and English Markdown documents
including headings, code blocks, and tables.

Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.7
"""

from __future__ import annotations

import pytest

from scripts.verification.bilingual_comparator import compare_setup_guides


class TestIdenticalStructure:
    """Tests for documents with identical structure → status="pass"."""

    def test_identical_documents_pass_with_empty_differences(
        self, tmp_path, sample_markdown_ja, sample_markdown_en
    ):
        """Identical structure (same headings, code blocks, tables) returns pass."""
        ja_file = tmp_path / "ja" / "setup-guide.md"
        en_file = tmp_path / "en" / "setup-guide.md"
        ja_file.parent.mkdir(parents=True)
        en_file.parent.mkdir(parents=True)
        ja_file.write_text(sample_markdown_ja, encoding="utf-8")
        en_file.write_text(sample_markdown_en, encoding="utf-8")

        result = compare_setup_guides(str(ja_file), str(en_file))

        assert result.status == "pass"
        assert result.differences == []

    def test_identical_simple_documents_pass(self, tmp_path):
        """Two minimal identical documents return pass."""
        content_ja = "# タイトル\n\n## セクション1\n\n```bash\necho hello\n```\n"
        content_en = "# Title\n\n## Section 1\n\n```bash\necho hello\n```\n"

        ja_file = tmp_path / "ja.md"
        en_file = tmp_path / "en.md"
        ja_file.write_text(content_ja, encoding="utf-8")
        en_file.write_text(content_en, encoding="utf-8")

        result = compare_setup_guides(str(ja_file), str(en_file))

        assert result.status == "pass"
        assert result.differences == []
        assert result.heading_count == 2
        assert result.code_block_count == 1


class TestHeadingDifferences:
    """Tests for heading structure differences → status="fail"."""

    def test_different_heading_count_fails(self, tmp_path):
        """JA has 3 headings, EN has 2 → fail with heading diff."""
        content_ja = "# Title\n\n## Section 1\n\n## Section 2\n"
        content_en = "# Title\n\n## Section 1\n"

        ja_file = tmp_path / "ja.md"
        en_file = tmp_path / "en.md"
        ja_file.write_text(content_ja, encoding="utf-8")
        en_file.write_text(content_en, encoding="utf-8")

        result = compare_setup_guides(str(ja_file), str(en_file))

        assert result.status == "fail"
        assert len(result.differences) >= 1
        diff = result.differences[0]
        assert diff.diff_type == "heading"
        assert "3" in diff.expected
        assert "2" in diff.actual

    def test_different_heading_level_fails(self, tmp_path):
        """JA has h2, EN has h3 at same position → fail."""
        content_ja = "# Title\n\n## Section\n"
        content_en = "# Title\n\n### Section\n"

        ja_file = tmp_path / "ja.md"
        en_file = tmp_path / "en.md"
        ja_file.write_text(content_ja, encoding="utf-8")
        en_file.write_text(content_en, encoding="utf-8")

        result = compare_setup_guides(str(ja_file), str(en_file))

        assert result.status == "fail"
        assert len(result.differences) >= 1
        diff = result.differences[0]
        assert diff.diff_type == "heading"
        assert "2" in diff.expected
        assert "3" in diff.actual


class TestCodeBlockDifferences:
    """Tests for code block differences → status="fail"."""

    def test_different_code_block_content_fails(self, tmp_path):
        """Different code block content → fail with code_block diff."""
        content_ja = "# Title\n\n```bash\naws s3 ls\n```\n"
        content_en = "# Title\n\n```bash\naws s3 cp file.txt s3://bucket/\n```\n"

        ja_file = tmp_path / "ja.md"
        en_file = tmp_path / "en.md"
        ja_file.write_text(content_ja, encoding="utf-8")
        en_file.write_text(content_en, encoding="utf-8")

        result = compare_setup_guides(str(ja_file), str(en_file))

        assert result.status == "fail"
        assert len(result.differences) >= 1
        diff = result.differences[0]
        assert diff.diff_type == "code_block"

    def test_different_code_block_count_fails(self, tmp_path):
        """JA has 2 code blocks, EN has 1 → fail."""
        content_ja = "# Title\n\n```bash\necho a\n```\n\n```bash\necho b\n```\n"
        content_en = "# Title\n\n```bash\necho a\n```\n"

        ja_file = tmp_path / "ja.md"
        en_file = tmp_path / "en.md"
        ja_file.write_text(content_ja, encoding="utf-8")
        en_file.write_text(content_en, encoding="utf-8")

        result = compare_setup_guides(str(ja_file), str(en_file))

        assert result.status == "fail"
        assert len(result.differences) >= 1
        diff = result.differences[0]
        assert diff.diff_type == "code_block"
        assert "2" in diff.expected
        assert "1" in diff.actual


class TestTableDifferences:
    """Tests for table structure differences → status="fail"."""

    def test_different_table_row_count_fails(self, tmp_path):
        """Different row counts → fail with table diff."""
        content_ja = (
            "# Title\n\n"
            "| Param | Value |\n"
            "|-------|-------|\n"
            "| `A` | `1` |\n"
            "| `B` | `2` |\n"
            "| `C` | `3` |\n"
        )
        content_en = (
            "# Title\n\n"
            "| Param | Value |\n"
            "|-------|-------|\n"
            "| `A` | `1` |\n"
            "| `B` | `2` |\n"
        )

        ja_file = tmp_path / "ja.md"
        en_file = tmp_path / "en.md"
        ja_file.write_text(content_ja, encoding="utf-8")
        en_file.write_text(content_en, encoding="utf-8")

        result = compare_setup_guides(str(ja_file), str(en_file))

        assert result.status == "fail"
        assert len(result.differences) >= 1
        diff = result.differences[0]
        assert diff.diff_type == "table"
        assert "row count" in diff.expected or "row count" in diff.actual

    def test_different_table_column_count_fails(self, tmp_path):
        """Different column counts → fail with table diff."""
        content_ja = (
            "# Title\n\n"
            "| Param | Value | Note |\n"
            "|-------|-------|------|\n"
            "| `A` | `1` | info |\n"
        )
        content_en = (
            "# Title\n\n"
            "| Param | Value |\n"
            "|-------|-------|\n"
            "| `A` | `1` |\n"
        )

        ja_file = tmp_path / "ja.md"
        en_file = tmp_path / "en.md"
        ja_file.write_text(content_ja, encoding="utf-8")
        en_file.write_text(content_en, encoding="utf-8")

        result = compare_setup_guides(str(ja_file), str(en_file))

        assert result.status == "fail"
        assert len(result.differences) >= 1
        diff = result.differences[0]
        assert diff.diff_type == "table"
        assert "column count" in diff.expected or "column count" in diff.actual

    def test_different_code_value_cells_in_table_fails(self, tmp_path):
        """Different backtick-wrapped code cells → fail with table diff."""
        content_ja = (
            "# Title\n\n"
            "| Param | Value |\n"
            "|-------|-------|\n"
            "| `StackName` | `fsxn-datadog-integration` |\n"
        )
        content_en = (
            "# Title\n\n"
            "| Param | Value |\n"
            "|-------|-------|\n"
            "| `StackName` | `fsxn-newrelic-integration` |\n"
        )

        ja_file = tmp_path / "ja.md"
        en_file = tmp_path / "en.md"
        ja_file.write_text(content_ja, encoding="utf-8")
        en_file.write_text(content_en, encoding="utf-8")

        result = compare_setup_guides(str(ja_file), str(en_file))

        assert result.status == "fail"
        assert len(result.differences) >= 1
        diff = result.differences[0]
        assert diff.diff_type == "table"


class TestMissingFile:
    """Tests for missing file handling → status="fail"."""

    def test_missing_ja_file_fails(self, tmp_path):
        """Missing JA file → fail with FileNotFoundError info."""
        content_en = "# Title\n\n## Section\n"
        en_file = tmp_path / "en.md"
        en_file.write_text(content_en, encoding="utf-8")

        nonexistent_ja = str(tmp_path / "ja" / "setup-guide.md")

        result = compare_setup_guides(nonexistent_ja, str(en_file))

        assert result.status == "fail"
        assert len(result.differences) >= 1
        diff = result.differences[0]
        assert "FileNotFoundError" in diff.actual

    def test_missing_en_file_fails(self, tmp_path):
        """Missing EN file → fail with FileNotFoundError info."""
        content_ja = "# タイトル\n\n## セクション\n"
        ja_file = tmp_path / "ja.md"
        ja_file.write_text(content_ja, encoding="utf-8")

        nonexistent_en = str(tmp_path / "en" / "setup-guide.md")

        result = compare_setup_guides(str(ja_file), nonexistent_en)

        assert result.status == "fail"
        assert len(result.differences) >= 1
        diff = result.differences[0]
        assert "FileNotFoundError" in diff.actual


class TestConftestFixtures:
    """Tests using conftest fixtures to verify full document comparison."""

    def test_conftest_fixtures_identical_structure(
        self, tmp_path, sample_markdown_ja, sample_markdown_en
    ):
        """Conftest sample documents have identical structure → pass."""
        ja_file = tmp_path / "ja" / "setup-guide.md"
        en_file = tmp_path / "en" / "setup-guide.md"
        ja_file.parent.mkdir(parents=True)
        en_file.parent.mkdir(parents=True)
        ja_file.write_text(sample_markdown_ja, encoding="utf-8")
        en_file.write_text(sample_markdown_en, encoding="utf-8")

        result = compare_setup_guides(str(ja_file), str(en_file))

        assert result.status == "pass"
        assert result.differences == []
        assert result.heading_count > 0
        assert result.code_block_count > 0
        assert result.table_count > 0
        assert len(result.files_compared) == 1
