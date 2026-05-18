"""Unit tests for bilingual document comparison."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_bilingual_properties import (
    compare_bilingual_docs,
    extract_code_blocks,
    extract_headings,
)


class TestExtractHeadings:
    """Tests for extract_headings function."""

    def test_extracts_level2_headings(self):
        md = "# Title\n\n## Section 1\n\nText\n\n## Section 2\n\nMore text"
        headings = extract_headings(md)
        assert headings == ["Section 1", "Section 2"]

    def test_ignores_other_levels(self):
        md = "# H1\n\n## H2\n\n### H3\n\n#### H4"
        headings = extract_headings(md)
        assert headings == ["H2"]

    def test_empty_document(self):
        headings = extract_headings("")
        assert headings == []


class TestExtractCodeBlocks:
    """Tests for extract_code_blocks function."""

    def test_extracts_fenced_blocks(self):
        md = "Text\n\n```yaml\nkey: value\n```\n\nMore text\n\n```bash\necho hi\n```"
        blocks = extract_code_blocks(md)
        assert len(blocks) == 2
        assert "key: value\n" in blocks[0]
        assert "echo hi\n" in blocks[1]

    def test_empty_document(self):
        blocks = extract_code_blocks("")
        assert blocks == []


class TestCompareBilingualDocs:
    """Tests for compare_bilingual_docs function."""

    def test_identical_documents_pass(self):
        doc = "# Title\n\n## Section 1\n\nText\n\n```yaml\nkey: value\n```\n\n## Section 2\n\nMore"
        result = compare_bilingual_docs(doc, doc)
        assert result["heading_errors"] == []
        assert result["code_block_errors"] == []

    def test_different_heading_counts_fail(self):
        doc_ja = "# Title\n\n## Section 1\n\n## Section 2\n\n## Section 3\n"
        doc_en = "# Title\n\n## Section 1\n\n## Section 2\n"
        result = compare_bilingual_docs(doc_ja, doc_en)
        assert len(result["heading_errors"]) > 0

    def test_different_code_blocks_fail(self):
        doc_ja = "# Title\n\n## Section\n\n```yaml\nkey: value_ja\n```\n"
        doc_en = "# Title\n\n## Section\n\n```yaml\nkey: value_en\n```\n"
        result = compare_bilingual_docs(doc_ja, doc_en)
        assert len(result["code_block_errors"]) > 0

    def test_same_structure_different_prose_passes(self):
        doc_ja = "# タイトル\n\n## セクション\n\n日本語テキスト\n\n```bash\necho hello\n```\n"
        doc_en = "# Title\n\n## セクション\n\nEnglish text\n\n```bash\necho hello\n```\n"
        result = compare_bilingual_docs(doc_ja, doc_en)
        assert result["heading_errors"] == []
        assert result["code_block_errors"] == []


class TestActualSetupGuides:
    """Test the actual setup guide files for structural consistency."""

    def test_setup_guides_consistent(self):
        base = Path(__file__).parent.parent / "docs"
        ja_path = base / "ja" / "setup-guide.md"
        en_path = base / "en" / "setup-guide.md"

        if not ja_path.exists() or not en_path.exists():
            pytest.skip("Setup guide files not found")

        doc_ja = ja_path.read_text(encoding="utf-8")
        doc_en = en_path.read_text(encoding="utf-8")

        result = compare_bilingual_docs(doc_ja, doc_en)
        assert result["heading_errors"] == [], f"Heading errors: {result['heading_errors']}"
        assert result["code_block_errors"] == [], f"Code block errors: {result['code_block_errors']}"
