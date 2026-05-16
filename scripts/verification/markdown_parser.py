"""Markdown structural parser for bilingual document comparison.

Extracts structural elements (headings, fenced code blocks, pipe-delimited
tables) from Markdown content for structural comparison between documents.
"""

from __future__ import annotations

import re

from scripts.verification.models import Heading, MarkdownStructure, Table


def parse_markdown(content: str) -> MarkdownStructure:
    """Parse Markdown content and extract structural elements.

    Extracts ATX headings (# through ######), fenced code blocks (```),
    and pipe-delimited tables from the given Markdown content. Elements
    inside fenced code blocks are not extracted as top-level elements.

    Args:
        content: Raw Markdown content as a string. May be empty.

    Returns:
        A MarkdownStructure containing all extracted headings, code blocks,
        and tables in document order.

    Examples:
        >>> result = parse_markdown("# Title\\n\\nSome text")
        >>> len(result.headings)
        1
        >>> result.headings[0].level
        1
        >>> result.headings[0].text
        'Title'

        >>> result = parse_markdown("")
        >>> result.headings
        []
        >>> result.code_blocks
        []
        >>> result.tables
        []
    """
    if not content:
        return MarkdownStructure()

    headings: list[Heading] = []
    code_blocks: list[str] = []
    tables: list[Table] = []

    lines = content.split("\n")
    i = 0
    in_code_block = False
    code_block_lines: list[str] = []

    while i < len(lines):
        line = lines[i]

        # Handle fenced code blocks
        if _is_fence_line(line):
            if not in_code_block:
                # Opening fence
                in_code_block = True
                code_block_lines = []
            else:
                # Closing fence
                in_code_block = False
                code_blocks.append("\n".join(code_block_lines))
            i += 1
            continue

        if in_code_block:
            code_block_lines.append(line)
            i += 1
            continue

        # Extract ATX headings (outside code blocks)
        heading = _parse_heading(line)
        if heading is not None:
            headings.append(heading)
            i += 1
            continue

        # Extract pipe-delimited tables (outside code blocks)
        if _is_table_row(line):
            table_rows: list[list[str]] = []
            while i < len(lines) and _is_table_row(lines[i]):
                row_line = lines[i]
                if not _is_separator_row(row_line):
                    cells = _parse_table_row(row_line)
                    table_rows.append(cells)
                i += 1

            if table_rows:
                column_count = max(len(row) for row in table_rows)
                tables.append(Table(rows=table_rows, column_count=column_count))
            continue

        i += 1

    # Handle unclosed code block (treat accumulated lines as a code block)
    if in_code_block and code_block_lines:
        code_blocks.append("\n".join(code_block_lines))

    return MarkdownStructure(
        headings=headings,
        code_blocks=code_blocks,
        tables=tables,
    )


def _is_fence_line(line: str) -> bool:
    """Check if a line is a fenced code block delimiter.

    Matches lines starting with three or more backticks, optionally
    followed by a language specifier (e.g., ```python, ```bash).

    Args:
        line: A single line of text.

    Returns:
        True if the line is a code fence delimiter.
    """
    stripped = line.strip()
    # Match ``` optionally followed by a language identifier
    return bool(re.match(r"^`{3,}(\S*)\s*$", stripped))


def _parse_heading(line: str) -> Heading | None:
    """Parse an ATX heading from a line.

    ATX headings start with 1-6 '#' characters followed by a space
    and the heading text.

    Args:
        line: A single line of text.

    Returns:
        A Heading instance if the line is a valid ATX heading, None otherwise.
    """
    match = re.match(r"^(#{1,6})\s+(.+?)(?:\s+#+\s*)?$", line)
    if match:
        level = len(match.group(1))
        text = match.group(2).strip()
        return Heading(level=level, text=text)
    return None


def _is_table_row(line: str) -> bool:
    """Check if a line is a pipe-delimited table row.

    A table row must contain at least one pipe character and have
    pipe characters at both the start and end (after stripping).

    Args:
        line: A single line of text.

    Returns:
        True if the line appears to be a table row.
    """
    stripped = line.strip()
    if not stripped:
        return False
    return stripped.startswith("|") and stripped.endswith("|")


def _is_separator_row(line: str) -> bool:
    """Check if a table row is a separator row (|---|---|).

    Separator rows contain only pipes, dashes, colons, and whitespace.

    Args:
        line: A single line of text.

    Returns:
        True if the line is a table separator row.
    """
    stripped = line.strip()
    # Remove leading/trailing pipes and check remaining content
    inner = stripped.strip("|")
    # Separator cells contain only dashes, colons, and spaces
    return bool(re.match(r"^[\s\-:|]+$", inner)) and "-" in inner


def _parse_table_row(line: str) -> list[str]:
    """Parse a pipe-delimited table row into cells.

    Splits the row by pipe characters and strips whitespace from each cell.
    Leading and trailing empty cells (from outer pipes) are removed.

    Args:
        line: A single line of text representing a table row.

    Returns:
        A list of cell contents (stripped of whitespace).
    """
    stripped = line.strip()
    # Remove leading and trailing pipes
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    # Split by pipe and strip each cell
    cells = [cell.strip() for cell in stripped.split("|")]
    return cells
