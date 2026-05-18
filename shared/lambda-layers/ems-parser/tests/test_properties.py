"""Property-based tests for EMS Parser using Hypothesis.

Tests cover:
- Property 1: Parsing correctness for valid EMS payloads
- Property 2: Invalid input rejection
- Property 3: Serialization round-trip
- Property 4: Bilingual code block consistency
"""

from __future__ import annotations

import json
import re
from typing import Any

from hypothesis import given, settings
from hypothesis.strategies import (
    booleans,
    composite,
    dictionaries,
    floats,
    integers,
    just,
    lists,
    none,
    one_of,
    text,
)

from ems_parser import EmsParseError, format_ems_event, parse_ems_event

from .test_bilingual import compare_code_blocks


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@composite
def valid_ems_payloads(draw: Any) -> dict[str, Any]:
    """Generate random valid EMS Webhook payloads.

    Produces payloads with all required fields: messageName, time,
    severity, node, svmName, message, and parameters.
    """
    message_name = draw(text(min_size=1, max_size=100))
    time = draw(text(min_size=1, max_size=50))
    severity = draw(text(min_size=1, max_size=30))
    node = draw(text(min_size=1, max_size=100))
    svm_name = draw(text(min_size=1, max_size=100))
    message = draw(text(min_size=0, max_size=3000))
    # Generate parameters as a dict of string keys to simple JSON values
    parameters = draw(
        dictionaries(
            keys=text(min_size=1, max_size=30),
            values=one_of(
                text(max_size=100),
                integers(min_value=-1000000, max_value=1000000),
                booleans(),
            ),
            min_size=1,
            max_size=5,
        )
    )

    return {
        "time": time,
        "messageName": message_name,
        "severity": severity,
        "node": node,
        "svmName": svm_name,
        "message": message,
        "parameters": parameters,
    }


def _is_not_valid_json(s: str) -> bool:
    """Return True if the string is NOT valid JSON."""
    try:
        json.loads(s)
        return False
    except (json.JSONDecodeError, ValueError):
        return True


@composite
def invalid_ems_inputs(draw: Any) -> Any:
    """Generate random invalid inputs for parse_ems_event.

    Produces one of:
    - None
    - Empty string
    - Non-JSON text
    - Valid JSON missing messageName field
    """
    strategy = draw(
        one_of(
            just(None),
            just(""),
            text(min_size=1, max_size=200).filter(_is_not_valid_json),
            # Valid JSON dict missing messageName
            dictionaries(
                keys=text(min_size=1, max_size=20).filter(
                    lambda k: k != "messageName"
                ),
                values=text(max_size=50),
                min_size=0,
                max_size=5,
            ).map(json.dumps),
        )
    )
    return strategy


@composite
def markdown_with_code_blocks(draw: Any, num_blocks: int = 3) -> tuple[str, list[str]]:
    """Generate a Markdown document with fenced code blocks.

    Returns a tuple of (markdown_content, list_of_code_block_contents).
    """
    blocks: list[str] = []
    parts: list[str] = []

    for i in range(num_blocks):
        # Add some prose before each code block
        prose = draw(text(min_size=1, max_size=50, alphabet="abcdefghijklmnop "))
        parts.append(f"# Section {i}\n\n{prose}\n\n")

        # Generate code block content (avoid backticks to prevent nesting issues)
        code_content = draw(
            text(min_size=1, max_size=80, alphabet="abcdefghijklmnopqrstuvwxyz0123456789 -_./=\n")
        )
        # Ensure code content ends with newline
        if not code_content.endswith("\n"):
            code_content += "\n"
        blocks.append(code_content)
        parts.append(f"```bash\n{code_content}```\n\n")

    return "".join(parts), blocks


# ---------------------------------------------------------------------------
# Property 1: Parsing correctness for valid EMS payloads
# Feature: ems-fpolicy-e2e-verification, Property 1: Parsing correctness for valid EMS payloads
# ---------------------------------------------------------------------------


class TestProperty1ParsingCorrectness:
    """Property 1: For any valid EMS payload, parse_ems_event returns correct fields.

    **Validates: Requirements 3.2, 3.3, 3.4, 3.7**
    """

    @given(payload=valid_ems_payloads())
    @settings(max_examples=100)
    def test_event_name_equals_input_message_name(self, payload: dict[str, Any]) -> None:
        """event_name in output equals messageName in input."""
        result = parse_ems_event(payload)
        assert result["event_name"] == payload["messageName"]

    @given(payload=valid_ems_payloads())
    @settings(max_examples=100)
    def test_severity_equals_input_severity(self, payload: dict[str, Any]) -> None:
        """severity in output equals severity in input."""
        result = parse_ems_event(payload)
        assert result["severity"] == payload["severity"]

    @given(payload=valid_ems_payloads())
    @settings(max_examples=100)
    def test_source_node_equals_input_node(self, payload: dict[str, Any]) -> None:
        """source_node in output equals node in input."""
        result = parse_ems_event(payload)
        assert result["source_node"] == payload["node"]

    @given(payload=valid_ems_payloads())
    @settings(max_examples=100)
    def test_svm_equals_input_svm_name(self, payload: dict[str, Any]) -> None:
        """svm in output equals svmName in input."""
        result = parse_ems_event(payload)
        assert result["svm"] == payload["svmName"]

    @given(payload=valid_ems_payloads())
    @settings(max_examples=100)
    def test_message_length_at_most_2048(self, payload: dict[str, Any]) -> None:
        """message in output is at most 2048 characters."""
        result = parse_ems_event(payload)
        assert len(result["message"]) <= 2048

    @given(payload=valid_ems_payloads())
    @settings(max_examples=100)
    def test_raw_equals_original_input(self, payload: dict[str, Any]) -> None:
        """raw in output equals the original input payload."""
        result = parse_ems_event(payload)
        assert result["raw"] == payload


# ---------------------------------------------------------------------------
# Property 2: Invalid input rejection
# Feature: ems-fpolicy-e2e-verification, Property 2: Invalid input rejection
# ---------------------------------------------------------------------------


class TestProperty2InvalidInputRejection:
    """Property 2: For any invalid input, parse_ems_event raises EmsParseError.

    **Validates: Requirements 3.5**
    """

    @given(invalid_input=invalid_ems_inputs())
    @settings(max_examples=100)
    def test_invalid_input_raises_ems_parse_error(self, invalid_input: Any) -> None:
        """Invalid inputs always raise EmsParseError with non-empty message."""
        with_error = False
        try:
            parse_ems_event(invalid_input)
        except EmsParseError as e:
            with_error = True
            assert str(e) != "", "EmsParseError message must be non-empty"

        assert with_error, (
            f"Expected EmsParseError for input: {invalid_input!r}"
        )


# ---------------------------------------------------------------------------
# Property 3: Serialization round-trip
# Feature: ems-fpolicy-e2e-verification, Property 3: Serialization round-trip
# ---------------------------------------------------------------------------


class TestProperty3SerializationRoundTrip:
    """Property 3: parse → format → parse produces equal result.

    **Validates: Requirements 3.6, 8.5**
    """

    @given(payload=valid_ems_payloads())
    @settings(max_examples=100)
    def test_round_trip_preserves_normalized_dict(self, payload: dict[str, Any]) -> None:
        """parse_ems_event(format_ems_event(parse_ems_event(p))) == parse_ems_event(p)."""
        first_parse = parse_ems_event(payload)
        formatted = format_ems_event(first_parse)
        second_parse = parse_ems_event(formatted)

        assert first_parse == second_parse


# ---------------------------------------------------------------------------
# Property 4: Bilingual code block consistency
# Feature: ems-fpolicy-e2e-verification, Property 4: Bilingual code block consistency
# ---------------------------------------------------------------------------


class TestProperty4BilingualCodeBlockConsistency:
    """Property 4: Code blocks in paired Markdown docs are consistent.

    **Validates: Requirements 7.6**
    """

    @given(data=markdown_with_code_blocks())
    @settings(max_examples=50)
    def test_identical_code_blocks_return_no_differences(
        self, data: tuple[str, list[str]], tmp_path_factory: Any
    ) -> None:
        """Identical Markdown documents produce no differences."""
        content, _ = data
        # Use a unique temp dir for this test invocation
        import tempfile
        import os

        tmpdir = tempfile.mkdtemp()
        ja_path = os.path.join(tmpdir, "ja.md")
        en_path = os.path.join(tmpdir, "en.md")

        with open(ja_path, "w", encoding="utf-8") as f:
            f.write(content)
        with open(en_path, "w", encoding="utf-8") as f:
            f.write(content)

        differences = compare_code_blocks(ja_path, en_path)
        assert differences == [], f"Expected no differences, got: {differences}"

        # Cleanup
        os.unlink(ja_path)
        os.unlink(en_path)
        os.rmdir(tmpdir)

    @given(data=markdown_with_code_blocks())
    @settings(max_examples=50)
    def test_differing_code_blocks_are_detected(
        self, data: tuple[str, list[str]], tmp_path_factory: Any
    ) -> None:
        """Documents with different code blocks produce differences."""
        content, blocks = data
        if not blocks:
            return  # Skip if no blocks generated

        # Modify the first code block in the English version
        import tempfile
        import os

        tmpdir = tempfile.mkdtemp()
        ja_path = os.path.join(tmpdir, "ja.md")
        en_path = os.path.join(tmpdir, "en.md")

        with open(ja_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Replace the first code block content with something different
        modified_content = content.replace(
            f"```bash\n{blocks[0]}```",
            "```bash\nDIFFERENT_CONTENT_xyz123\n```",
            1,
        )

        with open(en_path, "w", encoding="utf-8") as f:
            f.write(modified_content)

        differences = compare_code_blocks(ja_path, en_path)
        assert len(differences) > 0, "Expected differences to be detected"

        # Cleanup
        os.unlink(ja_path)
        os.unlink(en_path)
        os.rmdir(tmpdir)
