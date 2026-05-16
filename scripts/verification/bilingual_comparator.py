"""Bilingual document comparator for ja/en setup guide consistency.

Compares structural elements (headings, code blocks, tables) between
Japanese and English Markdown documents to ensure bilingual consistency.
"""

from __future__ import annotations

import re

from scripts.verification.markdown_parser import parse_markdown
from scripts.verification.models import (
    BilingualComparisonResult,
    BilingualDifference,
    MarkdownStructure,
)


def compare_setup_guides(ja_path: str, en_path: str) -> BilingualComparisonResult:
    """Compare Japanese and English setup guides for structural consistency.

    Reads both files, parses their Markdown structure, and compares
    headings (levels and count), code blocks (byte-level content),
    and tables (row/column counts and code-value cells).

    Args:
        ja_path: Path to the Japanese setup guide Markdown file.
        en_path: Path to the English setup guide Markdown file.

    Returns:
        A BilingualComparisonResult with status "pass" if no structural
        differences are found, or "fail" with a list of differences.
    """
    differences: list[BilingualDifference] = []

    # Read files with error handling
    ja_content = _read_file_safe(ja_path, differences, en_path)
    en_content = _read_file_safe(en_path, differences, ja_path)

    if ja_content is None or en_content is None:
        return BilingualComparisonResult(
            status="fail",
            files_compared=[(ja_path, en_path)],
            differences=differences,
        )

    # Parse both documents
    ja_structure = parse_markdown(ja_content)
    en_structure = parse_markdown(en_content)

    # Compare headings
    _compare_headings(ja_structure, en_structure, ja_path, en_path, differences)

    # Compare code blocks
    _compare_code_blocks(ja_structure, en_structure, ja_path, en_path, differences)

    # Compare tables
    _compare_tables(ja_structure, en_structure, ja_path, en_path, differences)

    status: str = "pass" if not differences else "fail"

    return BilingualComparisonResult(
        status=status,
        files_compared=[(ja_path, en_path)],
        heading_count=len(ja_structure.headings),
        code_block_count=len(ja_structure.code_blocks),
        table_count=len(ja_structure.tables),
        differences=differences,
    )


def _read_file_safe(
    path: str,
    differences: list[BilingualDifference],
    counterpart_path: str,
) -> str | None:
    """Read a file with graceful error handling.

    Handles FileNotFoundError and UnicodeDecodeError, appending
    appropriate differences to the list.

    Args:
        path: Path to the file to read.
        differences: List to append error differences to.
        counterpart_path: Path of the counterpart file (for difference reporting).

    Returns:
        File content as a string, or None if the file could not be read.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        differences.append(
            BilingualDifference(
                file_path_ja=path if path.endswith(counterpart_path) or "/ja/" in path else counterpart_path,
                file_path_en=counterpart_path if "/ja/" in path else path,
                section="file",
                diff_type="heading",
                expected="file exists",
                actual=f"FileNotFoundError: {path}",
            )
        )
        return None
    except UnicodeDecodeError:
        # Retry with errors='replace' and add a warning
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            differences.append(
                BilingualDifference(
                    file_path_ja=path if "/ja/" in path else counterpart_path,
                    file_path_en=counterpart_path if "/ja/" in path else path,
                    section="file",
                    diff_type="heading",
                    expected="valid UTF-8 encoding",
                    actual=f"UnicodeDecodeError in {path} (read with replacement characters)",
                )
            )
            return content
        except OSError:
            return None


def _compare_headings(
    ja_structure: MarkdownStructure,
    en_structure: MarkdownStructure,
    ja_path: str,
    en_path: str,
    differences: list[BilingualDifference],
) -> None:
    """Compare heading structures between two documents.

    Checks that both documents have the same number of headings and
    that heading levels match in order. Text content is not compared
    since it differs between languages.

    Args:
        ja_structure: Parsed structure of the Japanese document.
        en_structure: Parsed structure of the English document.
        ja_path: Path to the Japanese file.
        en_path: Path to the English file.
        differences: List to append differences to.
    """
    ja_headings = ja_structure.headings
    en_headings = en_structure.headings

    if len(ja_headings) != len(en_headings):
        differences.append(
            BilingualDifference(
                file_path_ja=ja_path,
                file_path_en=en_path,
                section="headings",
                diff_type="heading",
                expected=f"heading count: {len(ja_headings)}",
                actual=f"heading count: {len(en_headings)}",
            )
        )
        return

    for i, (ja_h, en_h) in enumerate(zip(ja_headings, en_headings)):
        if ja_h.level != en_h.level:
            differences.append(
                BilingualDifference(
                    file_path_ja=ja_path,
                    file_path_en=en_path,
                    section=f"heading[{i}]",
                    diff_type="heading",
                    expected=f"level {ja_h.level}",
                    actual=f"level {en_h.level}",
                )
            )


def _compare_code_blocks(
    ja_structure: MarkdownStructure,
    en_structure: MarkdownStructure,
    ja_path: str,
    en_path: str,
    differences: list[BilingualDifference],
) -> None:
    """Compare code block contents between two documents.

    Checks that both documents have the same number of code blocks and
    that their contents match byte-for-byte in order.

    Args:
        ja_structure: Parsed structure of the Japanese document.
        en_structure: Parsed structure of the English document.
        ja_path: Path to the Japanese file.
        en_path: Path to the English file.
        differences: List to append differences to.
    """
    ja_blocks = ja_structure.code_blocks
    en_blocks = en_structure.code_blocks

    if len(ja_blocks) != len(en_blocks):
        differences.append(
            BilingualDifference(
                file_path_ja=ja_path,
                file_path_en=en_path,
                section="code_blocks",
                diff_type="code_block",
                expected=f"code block count: {len(ja_blocks)}",
                actual=f"code block count: {len(en_blocks)}",
            )
        )
        return

    for i, (ja_block, en_block) in enumerate(zip(ja_blocks, en_blocks)):
        if ja_block != en_block:
            # Truncate for readability
            ja_preview = ja_block[:80] + ("..." if len(ja_block) > 80 else "")
            en_preview = en_block[:80] + ("..." if len(en_block) > 80 else "")
            differences.append(
                BilingualDifference(
                    file_path_ja=ja_path,
                    file_path_en=en_path,
                    section=f"code_block[{i}]",
                    diff_type="code_block",
                    expected=ja_preview,
                    actual=en_preview,
                )
            )


def _compare_tables(
    ja_structure: MarkdownStructure,
    en_structure: MarkdownStructure,
    ja_path: str,
    en_path: str,
    differences: list[BilingualDifference],
) -> None:
    """Compare table structures between two documents.

    Checks that both documents have the same number of tables, and for
    each table pair: same row count, same column count, and matching
    parameter-name/code-value cells (cells containing backtick-wrapped
    code like `StackName`).

    Args:
        ja_structure: Parsed structure of the Japanese document.
        en_structure: Parsed structure of the English document.
        ja_path: Path to the Japanese file.
        en_path: Path to the English file.
        differences: List to append differences to.
    """
    ja_tables = ja_structure.tables
    en_tables = en_structure.tables

    if len(ja_tables) != len(en_tables):
        differences.append(
            BilingualDifference(
                file_path_ja=ja_path,
                file_path_en=en_path,
                section="tables",
                diff_type="table",
                expected=f"table count: {len(ja_tables)}",
                actual=f"table count: {len(en_tables)}",
            )
        )
        return

    for i, (ja_table, en_table) in enumerate(zip(ja_tables, en_tables)):
        # Compare row counts
        if len(ja_table.rows) != len(en_table.rows):
            differences.append(
                BilingualDifference(
                    file_path_ja=ja_path,
                    file_path_en=en_path,
                    section=f"table[{i}]",
                    diff_type="table",
                    expected=f"row count: {len(ja_table.rows)}",
                    actual=f"row count: {len(en_table.rows)}",
                )
            )
            continue

        # Compare column counts
        if ja_table.column_count != en_table.column_count:
            differences.append(
                BilingualDifference(
                    file_path_ja=ja_path,
                    file_path_en=en_path,
                    section=f"table[{i}]",
                    diff_type="table",
                    expected=f"column count: {ja_table.column_count}",
                    actual=f"column count: {en_table.column_count}",
                )
            )
            continue

        # Compare parameter-name/code-value cells
        _compare_table_code_cells(
            ja_table.rows, en_table.rows, i, ja_path, en_path, differences
        )


def _compare_table_code_cells(
    ja_rows: list[list[str]],
    en_rows: list[list[str]],
    table_index: int,
    ja_path: str,
    en_path: str,
    differences: list[BilingualDifference],
) -> None:
    """Compare code-value cells in table rows.

    Cells containing backtick-wrapped code (e.g., `StackName`) should
    match between languages since they are language-independent.

    Args:
        ja_rows: Rows from the Japanese table.
        en_rows: Rows from the English table.
        table_index: Index of the table being compared.
        ja_path: Path to the Japanese file.
        en_path: Path to the English file.
        differences: List to append differences to.
    """
    for row_idx, (ja_row, en_row) in enumerate(zip(ja_rows, en_rows)):
        for col_idx in range(min(len(ja_row), len(en_row))):
            ja_cell = ja_row[col_idx]
            en_cell = en_row[col_idx]

            # Only compare cells that contain backtick-wrapped code
            if _is_code_cell(ja_cell) or _is_code_cell(en_cell):
                if ja_cell != en_cell:
                    differences.append(
                        BilingualDifference(
                            file_path_ja=ja_path,
                            file_path_en=en_path,
                            section=f"table[{table_index}].row[{row_idx}].col[{col_idx}]",
                            diff_type="table",
                            expected=ja_cell,
                            actual=en_cell,
                        )
                    )


def _is_code_cell(cell: str) -> bool:
    """Check if a table cell contains backtick-wrapped code.

    A code cell is one that contains at least one backtick-wrapped
    segment (e.g., `StackName`, `ap-northeast-1`).

    Args:
        cell: The cell content to check.

    Returns:
        True if the cell contains backtick-wrapped code.
    """
    return bool(re.search(r"`[^`]+`", cell))
