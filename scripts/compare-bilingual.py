"""CLI entry point for bilingual setup guide comparison.

Compares Japanese and English Markdown setup guides for structural
consistency (headings, code blocks, tables) and reports differences.

Usage:
    python scripts/compare-bilingual.py \
      --ja integrations/datadog/docs/ja/setup-guide.md \
      --en integrations/datadog/docs/en/setup-guide.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path for package imports
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from scripts.verification.bilingual_comparator import compare_setup_guides
from scripts.verification.models import BilingualComparisonResult


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the bilingual comparison CLI.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description="Compare Japanese and English setup guides for structural consistency.",
        prog="compare-bilingual",
    )
    parser.add_argument(
        "--ja",
        required=True,
        help="Path to the Japanese setup guide Markdown file.",
    )
    parser.add_argument(
        "--en",
        required=True,
        help="Path to the English setup guide Markdown file.",
    )
    return parser


def format_result(result: BilingualComparisonResult) -> str:
    """Format comparison result as human-readable text.

    Args:
        result: The bilingual comparison result to format.

    Returns:
        Formatted string for stdout output.
    """
    lines: list[str] = []

    # Status
    status_display = "PASS" if result.status == "pass" else "FAIL"
    lines.append(f"Status: {status_display}")
    lines.append("")

    # Files compared
    lines.append("Files compared:")
    for ja_path, en_path in result.files_compared:
        lines.append(f"  JA: {ja_path}")
        lines.append(f"  EN: {en_path}")
    lines.append("")

    # Counts
    lines.append("Counts:")
    lines.append(f"  Headings:    {result.heading_count}")
    lines.append(f"  Code blocks: {result.code_block_count}")
    lines.append(f"  Tables:      {result.table_count}")

    # Differences
    if result.differences:
        lines.append("")
        lines.append(f"Differences ({len(result.differences)}):")
        for i, diff in enumerate(result.differences, start=1):
            lines.append(f"  [{i}] Section: {diff.section}")
            lines.append(f"      Type:     {diff.diff_type}")
            lines.append(f"      Expected: {diff.expected}")
            lines.append(f"      Actual:   {diff.actual}")

    return "\n".join(lines)


def main() -> int:
    """Run the bilingual comparison CLI.

    Returns:
        Exit code: 0 for pass, 1 for fail.
    """
    parser = build_parser()
    args = parser.parse_args()

    result = compare_setup_guides(args.ja, args.en)
    print(format_result(result))

    return 0 if result.status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
