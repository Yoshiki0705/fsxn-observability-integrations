"""Property-based test for bilingual comparison — identical structures.

# Feature: new-relic-e2e-verification, Property 4: Structurally identical documents report no differences

Validates: Requirements 7.2, 7.3, 7.5
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.verification.bilingual_comparator import compare_setup_guides


# ---------------------------------------------------------------------------
# Hypothesis strategies for generating random Markdown content
# ---------------------------------------------------------------------------


@st.composite
def heading_strategy(draw: st.DrawFn) -> tuple[int, str, str]:
    """Generate a random ATX heading with different ja/en text.

    Returns (level, ja_text, en_text) where level is 1-6 and texts
    are different natural language strings.
    """
    level = draw(st.integers(min_value=1, max_value=6))
    ja_text = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                blacklist_characters="\n\r#",
            ),
            min_size=2,
            max_size=30,
        ).map(lambda s: s.strip() or "見出し")
    )
    en_text = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                blacklist_characters="\n\r#",
            ),
            min_size=2,
            max_size=30,
        ).map(lambda s: s.strip() or "Heading")
    )
    return level, ja_text, en_text


@st.composite
def code_block_strategy(draw: st.DrawFn) -> str:
    """Generate a random fenced code block content.

    Code blocks are language-independent so both ja and en use the same content.
    """
    lang = draw(st.sampled_from(["", "python", "bash", "yaml", "json", "sql"]))
    # Generate code content without backtick sequences that could break fences
    content_lines = draw(
        st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "Z"),
                    blacklist_characters="\n\r`",
                ),
                min_size=1,
                max_size=60,
            ).map(lambda s: s.strip() or "echo hello"),
            min_size=1,
            max_size=5,
        )
    )
    content = "\n".join(content_lines)
    return f"```{lang}\n{content}\n```"


@st.composite
def table_strategy(draw: st.DrawFn) -> tuple[str, str]:
    """Generate a random pipe-delimited table with same structure for ja/en.

    Returns (ja_table, en_table) with identical row/column counts but
    different natural language text in non-code cells.
    """
    num_cols = draw(st.integers(min_value=2, max_value=5))
    num_data_rows = draw(st.integers(min_value=1, max_value=4))

    # Generate header cells (different text for ja/en)
    ja_headers = [
        draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N"),
                    blacklist_characters="\n\r|",
                ),
                min_size=2,
                max_size=15,
            ).map(lambda s: s.strip() or "列")
        )
        for _ in range(num_cols)
    ]
    en_headers = [
        draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N"),
                    blacklist_characters="\n\r|",
                ),
                min_size=2,
                max_size=15,
            ).map(lambda s: s.strip() or "Col")
        )
        for _ in range(num_cols)
    ]

    # Generate data rows (different text for ja/en)
    ja_rows: list[list[str]] = []
    en_rows: list[list[str]] = []
    for _ in range(num_data_rows):
        ja_row = [
            draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                        blacklist_characters="\n\r|`",
                    ),
                    min_size=1,
                    max_size=15,
                ).map(lambda s: s.strip() or "値")
            )
            for _ in range(num_cols)
        ]
        en_row = [
            draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                        blacklist_characters="\n\r|`",
                    ),
                    min_size=1,
                    max_size=15,
                ).map(lambda s: s.strip() or "val")
            )
            for _ in range(num_cols)
        ]
        ja_rows.append(ja_row)
        en_rows.append(en_row)

    def format_table(headers: list[str], rows: list[list[str]]) -> str:
        header_line = "| " + " | ".join(headers) + " |"
        separator = "| " + " | ".join(["---"] * num_cols) + " |"
        data_lines = [
            "| " + " | ".join(row) + " |" for row in rows
        ]
        return "\n".join([header_line, separator] + data_lines)

    ja_table = format_table(ja_headers, ja_rows)
    en_table = format_table(en_headers, en_rows)
    return ja_table, en_table


@st.composite
def markdown_document_pair_strategy(
    draw: st.DrawFn,
) -> tuple[str, str]:
    """Generate a pair of structurally identical Markdown documents.

    Both documents have the same heading levels/count, same code block
    contents, and same table row/column counts. Natural language text
    differs between ja and en versions.

    Returns (ja_content, en_content).
    """
    sections: list[tuple[str, str]] = []

    # Generate a mix of headings, code blocks, and tables
    num_elements = draw(st.integers(min_value=1, max_value=8))

    for _ in range(num_elements):
        element_type = draw(st.sampled_from(["heading", "code_block", "table"]))

        if element_type == "heading":
            level, ja_text, en_text = draw(heading_strategy())
            ja_line = "#" * level + " " + ja_text
            en_line = "#" * level + " " + en_text
            sections.append((ja_line, en_line))

        elif element_type == "code_block":
            # Code blocks are identical in both languages
            code_block = draw(code_block_strategy())
            sections.append((code_block, code_block))

        else:  # table
            ja_table, en_table = draw(table_strategy())
            sections.append((ja_table, en_table))

    # Add paragraph text between sections (different for ja/en)
    ja_parts: list[str] = []
    en_parts: list[str] = []
    for ja_section, en_section in sections:
        ja_parts.append(ja_section)
        en_parts.append(en_section)
        # Add a blank line separator
        ja_parts.append("")
        en_parts.append("")

    ja_content = "\n".join(ja_parts)
    en_content = "\n".join(en_parts)
    return ja_content, en_content


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(doc_pair=markdown_document_pair_strategy())
def test_bilingual_identical_structures_report_no_differences(
    doc_pair: tuple[str, str],
) -> None:
    """Property 4: Bilingual comparison — structurally identical documents report no differences.

    **Validates: Requirements 7.2, 7.3, 7.5**

    For any pair of Markdown documents that have identical heading structure
    (same levels and count in order), identical code block contents (same
    content in order), and identical table structures (same row/column counts),
    the bilingual comparison function SHALL return a result with
    status == "pass" and an empty differences list.
    """
    ja_content, en_content = doc_pair

    # Write to temporary files for comparison
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", encoding="utf-8", delete=False
    ) as ja_file:
        ja_file.write(ja_content)
        ja_path = ja_file.name

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", encoding="utf-8", delete=False
    ) as en_file:
        en_file.write(en_content)
        en_path = en_file.name

    try:
        result = compare_setup_guides(ja_path, en_path)

        assert result.status == "pass", (
            f"Expected status 'pass' but got '{result.status}'. "
            f"Differences: {result.differences}"
        )
        assert result.differences == [], (
            f"Expected empty differences but got: {result.differences}"
        )
    finally:
        # Clean up temp files
        Path(ja_path).unlink(missing_ok=True)
        Path(en_path).unlink(missing_ok=True)
