"""Property-based tests for bilingual document structural consistency.

Uses Hypothesis to verify that paired Markdown documents maintain
identical heading structure and code blocks.
"""

import re
import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# ─── Bilingual comparison utilities ────────────────────────────────────────


def extract_headings(markdown: str) -> list[str]:
    """Extract level-2 headings from Markdown content.

    Args:
        markdown: Markdown text content.

    Returns:
        List of heading texts (without ## prefix).
    """
    headings = []
    for line in markdown.split("\n"):
        if line.startswith("## "):
            headings.append(line[3:].strip())
    return headings


def extract_code_blocks(markdown: str) -> list[str]:
    """Extract fenced code block contents from Markdown.

    Args:
        markdown: Markdown text content.

    Returns:
        List of code block contents (without fence markers).
    """
    blocks = []
    pattern = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
    for match in pattern.finditer(markdown):
        blocks.append(match.group(1))
    return blocks


def compare_bilingual_docs(doc_ja: str, doc_en: str) -> dict[str, list[str]]:
    """Compare bilingual documents for structural consistency.

    Args:
        doc_ja: Japanese Markdown content.
        doc_en: English Markdown content.

    Returns:
        Dict with 'heading_errors' and 'code_block_errors' lists.
        Empty lists indicate documents are structurally consistent.
    """
    errors: dict[str, list[str]] = {"heading_errors": [], "code_block_errors": []}

    # Compare headings
    headings_ja = extract_headings(doc_ja)
    headings_en = extract_headings(doc_en)

    if len(headings_ja) != len(headings_en):
        errors["heading_errors"].append(
            f"Heading count mismatch: JA={len(headings_ja)}, EN={len(headings_en)}"
        )

    # Compare code blocks
    blocks_ja = extract_code_blocks(doc_ja)
    blocks_en = extract_code_blocks(doc_en)

    if len(blocks_ja) != len(blocks_en):
        errors["code_block_errors"].append(
            f"Code block count mismatch: JA={len(blocks_ja)}, EN={len(blocks_en)}"
        )
    else:
        for i, (ja_block, en_block) in enumerate(zip(blocks_ja, blocks_en)):
            if ja_block != en_block:
                errors["code_block_errors"].append(
                    f"Code block {i+1} differs between JA and EN"
                )

    return errors


# ─── Strategies ────────────────────────────────────────────────────────────

# Generate random prose (non-heading, non-code text)
prose_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=5,
    max_size=100,
)

# Generate heading text
heading_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=3,
    max_size=30,
)

# Generate code block content
code_content = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z", "S")),
    min_size=5,
    max_size=200,
).filter(lambda s: "```" not in s)


@st.composite
def bilingual_doc_pair(draw):
    """Generate a pair of Markdown documents with identical structure.

    Both documents share the same headings and code blocks but have
    different prose content.
    """
    num_sections = draw(st.integers(min_value=1, max_value=6))
    num_code_blocks = draw(st.integers(min_value=0, max_value=4))

    # Shared structure
    headings = [draw(heading_text) for _ in range(num_sections)]
    code_blocks = [draw(code_content) for _ in range(num_code_blocks)]

    # Build JA document
    ja_parts = ["# Title JA\n\n"]
    for i, heading in enumerate(headings):
        ja_parts.append(f"## {heading}\n\n")
        ja_parts.append(draw(prose_text) + "\n\n")
        if i < len(code_blocks):
            ja_parts.append(f"```yaml\n{code_blocks[i]}```\n\n")

    # Build EN document
    en_parts = ["# Title EN\n\n"]
    for i, heading in enumerate(headings):
        en_parts.append(f"## {heading}\n\n")
        en_parts.append(draw(prose_text) + "\n\n")
        if i < len(code_blocks):
            en_parts.append(f"```yaml\n{code_blocks[i]}```\n\n")

    return "".join(ja_parts), "".join(en_parts)


# ─── Property 6: Bilingual document structural consistency ─────────────────
# Feature: otel-collector-e2e-verification, Property 6: Bilingual document structural consistency


class TestProperty6BilingualConsistency:
    """Property 6: Bilingual document structural consistency.

    For any pair of Markdown documents with identical heading structure
    and code blocks, the comparison SHALL report no differences.

    **Validates: Requirements 6.5**
    """

    @given(doc_pair=bilingual_doc_pair())
    @settings(max_examples=100)
    def test_identical_structure_passes(self, doc_pair):
        """Documents with identical structure → no errors."""
        doc_ja, doc_en = doc_pair
        result = compare_bilingual_docs(doc_ja, doc_en)
        assert result["heading_errors"] == []
        assert result["code_block_errors"] == []

    @given(
        headings_ja=st.lists(heading_text, min_size=2, max_size=5),
        extra_heading=heading_text,
        prose=prose_text,
    )
    @settings(max_examples=100)
    def test_different_heading_counts_fails(self, headings_ja, extra_heading, prose):
        """Documents with different heading counts → heading error."""
        # JA has more headings than EN
        doc_ja = "# Title\n\n" + "".join(
            f"## {h}\n\n{prose}\n\n" for h in headings_ja
        ) + f"## {extra_heading}\n\n{prose}\n\n"

        doc_en = "# Title\n\n" + "".join(
            f"## {h}\n\n{prose}\n\n" for h in headings_ja
        )

        result = compare_bilingual_docs(doc_ja, doc_en)
        assert len(result["heading_errors"]) > 0

    @given(
        heading=heading_text,
        code_ja=code_content,
        code_en=code_content,
        prose=prose_text,
    )
    @settings(max_examples=100)
    def test_different_code_blocks_fails(self, heading, code_ja, code_en, prose):
        """Documents with different code block content → code block error."""
        from hypothesis import assume
        assume(code_ja != code_en)

        doc_ja = f"# Title\n\n## {heading}\n\n{prose}\n\n```yaml\n{code_ja}```\n\n"
        doc_en = f"# Title\n\n## {heading}\n\n{prose}\n\n```yaml\n{code_en}```\n\n"

        result = compare_bilingual_docs(doc_ja, doc_en)
        assert len(result["code_block_errors"]) > 0
