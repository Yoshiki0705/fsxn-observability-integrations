"""Property-based tests for bilingual document comparison.

Uses Hypothesis to generate random Markdown documents and verify that
the bilingual comparator correctly identifies structural equivalence
and differences.
"""

from __future__ import annotations

import os
import tempfile

from hypothesis import given, settings
from hypothesis import strategies as st

from scripts.verification.bilingual_comparator import compare_setup_guides


# --- Hypothesis strategies for Markdown generation ---


@st.composite
def heading_text(draw: st.DrawFn) -> str:
    """Generate valid heading text (non-empty, no newlines, no leading '#')."""
    text = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S", "Z"),
                blacklist_characters="\n\r#|",
            ),
            min_size=1,
            max_size=30,
        )
    )
    result = text.strip()
    return result if result else "Heading"


@st.composite
def code_block_content(draw: st.DrawFn) -> str:
    """Generate valid code block content (no backticks)."""
    content = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S", "Z"),
                blacklist_characters="`",
            ),
            min_size=1,
            max_size=50,
        )
    )
    return content


@st.composite
def table_cell(draw: st.DrawFn) -> str:
    """Generate a valid table cell (no pipes or newlines)."""
    cell = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"),
                blacklist_characters="|\n\r",
            ),
            min_size=1,
            max_size=15,
        )
    )
    result = cell.strip()
    return result if result else "cell"


@st.composite
def markdown_document(draw: st.DrawFn) -> str:
    """Generate a random Markdown document with headings, code blocks, and tables.

    Generates:
    - 0-5 headings with random levels (1-6) and random text
    - 0-3 code blocks with random content (no backticks inside)
    - 0-2 tables with random rows and columns

    Returns:
        Markdown content as a string.
    """
    parts: list[str] = []

    # Generate headings
    num_headings = draw(st.integers(min_value=0, max_value=5))
    for _ in range(num_headings):
        level = draw(st.integers(min_value=1, max_value=6))
        text = draw(heading_text())
        parts.append(f"{'#' * level} {text}")
        parts.append("")
        parts.append("Some paragraph text here.")
        parts.append("")

    # Generate code blocks
    num_code_blocks = draw(st.integers(min_value=0, max_value=3))
    for _ in range(num_code_blocks):
        content = draw(code_block_content())
        parts.append("```bash")
        parts.append(content)
        parts.append("```")
        parts.append("")

    # Generate tables
    num_tables = draw(st.integers(min_value=0, max_value=2))
    for _ in range(num_tables):
        num_cols = draw(st.integers(min_value=2, max_value=4))
        num_rows = draw(st.integers(min_value=1, max_value=4))

        # Header row
        header_cells = [draw(table_cell()) for _ in range(num_cols)]
        parts.append("| " + " | ".join(header_cells) + " |")

        # Separator row
        parts.append("| " + " | ".join(["---"] * num_cols) + " |")

        # Data rows
        for _ in range(num_rows):
            row_cells = [draw(table_cell()) for _ in range(num_cols)]
            parts.append("| " + " | ".join(row_cells) + " |")

        parts.append("")

    return "\n".join(parts)


# --- Property 3: Structurally identical documents report no differences ---

# Feature: datadog-e2e-verification, Property 3: Structurally identical documents report no differences


@given(content=markdown_document())
@settings(max_examples=100)
def test_identical_documents_report_no_differences(content: str) -> None:
    """Structurally identical documents should always report no differences.

    For any pair of Markdown documents that have identical heading structure
    (same levels and count in order), identical code block contents (same
    content in order), and identical table structures (same row/column counts
    and parameter-name/code-value cells), the bilingual comparison function
    shall return a result with status == "pass" and an empty differences list.

    **Validates: Requirements 9.1, 9.2, 9.3**
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        ja_path = os.path.join(tmpdir, "ja", "setup-guide.md")
        en_path = os.path.join(tmpdir, "en", "setup-guide.md")
        os.makedirs(os.path.dirname(ja_path))
        os.makedirs(os.path.dirname(en_path))

        # Write the SAME content to both files
        with open(ja_path, "w", encoding="utf-8") as f:
            f.write(content)
        with open(en_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Compare
        result = compare_setup_guides(ja_path, en_path)

    # Assert no differences
    assert result.status == "pass", (
        f"Expected status 'pass' but got '{result.status}'. "
        f"Differences: {result.differences}"
    )
    assert result.differences == [], (
        f"Expected empty differences but got {len(result.differences)}: "
        f"{result.differences}"
    )


# --- Property 4: Structural differences are detected ---

# Feature: datadog-e2e-verification, Property 4: Structural differences are detected


@given(
    base_doc=markdown_document(),
    diff_type=st.sampled_from(["heading", "code_block", "table"]),
)
@settings(max_examples=100)
def test_structural_differences_detected(
    base_doc: str,
    diff_type: str,
) -> None:
    """Structural differences between documents are detected by the comparator.

    **Validates: Requirements 9.1, 9.2, 9.3, 9.4**

    For any pair of Markdown documents where at least one structural element
    differs (a heading level mismatch, a code block content difference, or a
    table row/column count mismatch), the bilingual comparison function returns
    status == "fail" and a non-empty differences list with correct diff_type,
    section, expected, and actual values.
    """
    content = base_doc

    # Create modified version with a structural difference
    modified = _inject_difference(content, diff_type)

    # If injection didn't change anything (e.g., no elements of that type),
    # skip this example
    if modified == content:
        return

    # Write to temp files and compare
    with tempfile.TemporaryDirectory() as tmpdir:
        ja_path = os.path.join(tmpdir, "ja", "setup-guide.md")
        en_path = os.path.join(tmpdir, "en", "setup-guide.md")
        os.makedirs(os.path.dirname(ja_path))
        os.makedirs(os.path.dirname(en_path))

        # Write original to ja path, modified to en path
        with open(ja_path, "w", encoding="utf-8") as f:
            f.write(content)
        with open(en_path, "w", encoding="utf-8") as f:
            f.write(modified)

        result = compare_setup_guides(ja_path, en_path)

    # Assert comparison detects the difference
    assert result.status == "fail", (
        f"Expected status 'fail' for diff_type={diff_type}, got '{result.status}'"
    )
    assert len(result.differences) >= 1, (
        f"Expected at least 1 difference for diff_type={diff_type}, got 0"
    )

    # Assert each difference has non-empty required fields
    for diff in result.differences:
        assert diff.diff_type, "diff_type must be non-empty"
        assert diff.section, "section must be non-empty"
        assert diff.expected, "expected must be non-empty"
        assert diff.actual, "actual must be non-empty"


def _inject_difference(content: str, diff_type: str) -> str:
    """Inject a structural difference into Markdown content.

    Args:
        content: Original Markdown content.
        diff_type: Type of difference to inject ("heading", "code_block", "table").

    Returns:
        Modified Markdown content with the injected difference.
    """
    lines = content.split("\n")

    if diff_type == "heading":
        return _inject_heading_difference(lines)
    elif diff_type == "code_block":
        return _inject_code_block_difference(lines)
    elif diff_type == "table":
        return _inject_table_difference(lines)
    else:
        return content


def _inject_heading_difference(lines: list[str]) -> str:
    """Change the level of the first heading found.

    Shifts the heading level: if level < 6, increment by 1; otherwise set to 1.
    """
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#") and not stripped.startswith("```"):
            # Count current level
            level = 0
            for ch in stripped:
                if ch == "#":
                    level += 1
                else:
                    break
            # Only modify if it's a valid heading (has space after #)
            if level <= 6 and len(stripped) > level and stripped[level] == " ":
                new_level = (level % 6) + 1  # Shift level
                rest = stripped[level:]  # includes the space and text
                lines[i] = "#" * new_level + rest
                break
    return "\n".join(lines)


def _inject_code_block_difference(lines: list[str]) -> str:
    """Change the content of the first code block found."""
    in_code_block = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                continue
            else:
                # Closing fence — we should have modified content already
                break
        elif in_code_block:
            # Modify the first line inside the code block
            lines[i] = line + " --modified-flag"
            break
    return "\n".join(lines)


def _inject_table_difference(lines: list[str]) -> str:
    """Add an extra row to the first table found.

    This creates a row count mismatch between the original and modified documents.
    """
    # Find the first table and add a row after it
    in_table = False
    last_table_line = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            in_table = True
            last_table_line = i
        elif in_table and not (stripped.startswith("|") and stripped.endswith("|")):
            # End of table found
            break

    if last_table_line >= 0:
        # Determine column count from the last table row
        last_row = lines[last_table_line].strip()
        # Count pipes (subtract outer pipes)
        col_count = last_row.count("|") - 1
        # Create a new row with the same number of columns
        new_row = "| " + " | ".join(["extra"] * col_count) + " |"
        lines.insert(last_table_line + 1, new_row)

    return "\n".join(lines)
