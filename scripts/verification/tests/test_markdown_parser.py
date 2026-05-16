"""Unit tests for the Markdown structural parser.

Tests heading extraction, code block extraction, table parsing,
and edge cases for the parse_markdown function.

Requirements: 9.1, 9.2, 9.3
"""

from __future__ import annotations

from scripts.verification.markdown_parser import parse_markdown
from scripts.verification.models import Heading, MarkdownStructure, Table


class TestEmptyInput:
    """Tests for empty or minimal input."""

    def test_empty_string_returns_empty_structure(self) -> None:
        """Empty string produces an empty MarkdownStructure."""
        result = parse_markdown("")
        assert result.headings == []
        assert result.code_blocks == []
        assert result.tables == []

    def test_whitespace_only_returns_empty_structure(self) -> None:
        """Whitespace-only content produces no structural elements."""
        result = parse_markdown("   \n\n  \n")
        assert result.headings == []
        assert result.code_blocks == []
        assert result.tables == []

    def test_plain_text_returns_empty_structure(self) -> None:
        """Plain text without any Markdown structure."""
        result = parse_markdown("Just some plain text\nwith multiple lines.")
        assert result.headings == []
        assert result.code_blocks == []
        assert result.tables == []


class TestHeadingExtraction:
    """Tests for ATX heading extraction (h1-h6)."""

    def test_single_h1_heading(self) -> None:
        """Single h1 heading is correctly extracted."""
        result = parse_markdown("# Title")
        assert len(result.headings) == 1
        assert result.headings[0].level == 1
        assert result.headings[0].text == "Title"

    def test_single_h2_heading(self) -> None:
        """Single h2 heading is correctly extracted."""
        result = parse_markdown("## Subtitle")
        assert len(result.headings) == 1
        assert result.headings[0].level == 2
        assert result.headings[0].text == "Subtitle"

    def test_all_heading_levels(self) -> None:
        """All heading levels h1-h6 are correctly extracted."""
        content = """\
# Heading 1
## Heading 2
### Heading 3
#### Heading 4
##### Heading 5
###### Heading 6
"""
        result = parse_markdown(content)
        assert len(result.headings) == 6
        for i, heading in enumerate(result.headings, start=1):
            assert heading.level == i
            assert heading.text == f"Heading {i}"

    def test_multiple_headings_at_different_levels(self) -> None:
        """Multiple headings at varying levels preserve order."""
        content = """\
# Introduction
## Background
### Details
## Summary
# Conclusion
"""
        result = parse_markdown(content)
        assert len(result.headings) == 5
        assert result.headings[0] == Heading(level=1, text="Introduction")
        assert result.headings[1] == Heading(level=2, text="Background")
        assert result.headings[2] == Heading(level=3, text="Details")
        assert result.headings[3] == Heading(level=2, text="Summary")
        assert result.headings[4] == Heading(level=1, text="Conclusion")

    def test_heading_with_surrounding_text(self) -> None:
        """Headings are extracted even with surrounding paragraph text."""
        content = """\
Some intro text.

# Main Title

More text here.

## Section

Final text.
"""
        result = parse_markdown(content)
        assert len(result.headings) == 2
        assert result.headings[0].text == "Main Title"
        assert result.headings[1].text == "Section"

    def test_no_headings_in_document(self) -> None:
        """Document without headings returns empty headings list."""
        content = "Just text\n\nMore text\n\n- list item"
        result = parse_markdown(content)
        assert result.headings == []

    def test_heading_with_inline_code(self) -> None:
        """Heading containing inline code is extracted with backticks."""
        result = parse_markdown("## Using `parse_markdown`")
        assert len(result.headings) == 1
        assert result.headings[0].text == "Using `parse_markdown`"


class TestCodeBlockExtraction:
    """Tests for fenced code block extraction."""

    def test_single_code_block_with_language(self) -> None:
        """Fenced code block with language specifier is extracted."""
        content = """\
# Example

```python
def hello():
    print("hello")
```
"""
        result = parse_markdown(content)
        assert len(result.code_blocks) == 1
        assert result.code_blocks[0] == 'def hello():\n    print("hello")'

    def test_code_block_without_language(self) -> None:
        """Fenced code block without language specifier is extracted."""
        content = """\
```
plain code
```
"""
        result = parse_markdown(content)
        assert len(result.code_blocks) == 1
        assert result.code_blocks[0] == "plain code"

    def test_multiple_code_blocks(self) -> None:
        """Multiple code blocks are extracted in order."""
        content = """\
```bash
echo "first"
```

Some text.

```json
{"key": "value"}
```
"""
        result = parse_markdown(content)
        assert len(result.code_blocks) == 2
        assert result.code_blocks[0] == 'echo "first"'
        assert result.code_blocks[1] == '{"key": "value"}'

    def test_code_block_with_multiple_lines(self) -> None:
        """Multi-line code block preserves all lines."""
        content = """\
```python
import os
import sys

def main():
    pass
```
"""
        result = parse_markdown(content)
        assert len(result.code_blocks) == 1
        assert result.code_blocks[0] == "import os\nimport sys\n\ndef main():\n    pass"

    def test_empty_code_block(self) -> None:
        """Empty code block is extracted as empty string."""
        content = """\
```
```
"""
        result = parse_markdown(content)
        assert len(result.code_blocks) == 1
        assert result.code_blocks[0] == ""

    def test_code_block_with_bash_language(self) -> None:
        """Code block with bash language specifier."""
        content = """\
```bash
aws cloudformation deploy \\
  --template-file template.yaml
```
"""
        result = parse_markdown(content)
        assert len(result.code_blocks) == 1
        assert "aws cloudformation deploy" in result.code_blocks[0]


class TestTableParsing:
    """Tests for pipe-delimited Markdown table parsing."""

    def test_simple_table_with_header_and_data(self) -> None:
        """Simple table with header and data rows is parsed correctly."""
        content = """\
| Name | Value |
|------|-------|
| foo  | bar   |
| baz  | qux   |
"""
        result = parse_markdown(content)
        assert len(result.tables) == 1
        table = result.tables[0]
        assert table.column_count == 2
        # Separator row is excluded
        assert len(table.rows) == 3
        assert table.rows[0] == ["Name", "Value"]
        assert table.rows[1] == ["foo", "bar"]
        assert table.rows[2] == ["baz", "qux"]

    def test_separator_row_excluded(self) -> None:
        """Separator row (|---|---|) is not included in table rows."""
        content = """\
| A | B |
|---|---|
| 1 | 2 |
"""
        result = parse_markdown(content)
        assert len(result.tables) == 1
        table = result.tables[0]
        # Only header and data rows, not separator
        assert len(table.rows) == 2
        assert table.rows[0] == ["A", "B"]
        assert table.rows[1] == ["1", "2"]

    def test_table_with_three_columns(self) -> None:
        """Table with three columns is parsed correctly."""
        content = """\
| Parameter | Description | Default |
|-----------|-------------|---------|
| `StackName` | Stack name | `fsxn-datadog-integration` |
"""
        result = parse_markdown(content)
        assert len(result.tables) == 1
        table = result.tables[0]
        assert table.column_count == 3
        assert table.rows[0] == ["Parameter", "Description", "Default"]
        assert table.rows[1] == ["`StackName`", "Stack name", "`fsxn-datadog-integration`"]

    def test_no_tables_in_document(self) -> None:
        """Document without tables returns empty tables list."""
        content = "# Title\n\nSome text\n\n- list item"
        result = parse_markdown(content)
        assert result.tables == []


class TestCodeBlockIsolation:
    """Tests that elements inside code blocks are NOT extracted."""

    def test_headings_inside_code_blocks_not_extracted(self) -> None:
        """Headings inside code blocks are not extracted as headings."""
        content = """\
# Real Heading

```markdown
# This is inside a code block
## Also inside
```

## Another Real Heading
"""
        result = parse_markdown(content)
        assert len(result.headings) == 2
        assert result.headings[0].text == "Real Heading"
        assert result.headings[1].text == "Another Real Heading"

    def test_tables_inside_code_blocks_not_extracted(self) -> None:
        """Tables inside code blocks are not extracted as tables."""
        content = """\
# Example

```markdown
| Col1 | Col2 |
|------|------|
| a    | b    |
```

| Real | Table |
|------|-------|
| x    | y     |
"""
        result = parse_markdown(content)
        assert len(result.tables) == 1
        assert result.tables[0].rows[0] == ["Real", "Table"]


class TestMixedContent:
    """Tests for documents with mixed content types."""

    def test_mixed_headings_code_blocks_tables(self) -> None:
        """Document with headings, code blocks, and tables extracts all."""
        content = """\
# Setup Guide

## Prerequisites

- AWS Account

## Deployment

```bash
aws deploy --stack-name test
```

| Parameter | Value |
|-----------|-------|
| Region    | us-east-1 |

## Verification

```json
{"status": "ok"}
```
"""
        result = parse_markdown(content)
        assert len(result.headings) == 4
        assert len(result.code_blocks) == 2
        assert len(result.tables) == 1

    def test_sample_markdown_ja_fixture(self, sample_markdown_ja: str) -> None:
        """Parse the Japanese sample fixture and verify structure."""
        result = parse_markdown(sample_markdown_ja)
        # Headings: セットアップガイド, 前提条件, デプロイ手順, ステップ1, ステップ2, 動作確認
        assert len(result.headings) >= 5
        assert result.headings[0].level == 1
        assert result.headings[0].text == "セットアップガイド"
        # Code blocks: bash and json
        assert len(result.code_blocks) == 2
        # Tables: parameter table
        assert len(result.tables) == 1
        assert result.tables[0].column_count == 3

    def test_sample_markdown_en_fixture(self, sample_markdown_en: str) -> None:
        """Parse the English sample fixture and verify structure."""
        result = parse_markdown(sample_markdown_en)
        # Headings: Setup Guide, Prerequisites, Deployment Steps, Step 1, Step 2, Verification
        assert len(result.headings) >= 5
        assert result.headings[0].level == 1
        assert result.headings[0].text == "Setup Guide"
        # Code blocks: bash and json
        assert len(result.code_blocks) == 2
        # Tables: parameter table
        assert len(result.tables) == 1
        assert result.tables[0].column_count == 3

    def test_ja_and_en_have_same_structure(
        self, sample_markdown_ja: str, sample_markdown_en: str
    ) -> None:
        """Japanese and English samples have identical structural counts."""
        ja_result = parse_markdown(sample_markdown_ja)
        en_result = parse_markdown(sample_markdown_en)
        assert len(ja_result.headings) == len(en_result.headings)
        assert len(ja_result.code_blocks) == len(en_result.code_blocks)
        assert len(ja_result.tables) == len(en_result.tables)
        # Same heading levels
        for ja_h, en_h in zip(ja_result.headings, en_result.headings):
            assert ja_h.level == en_h.level
