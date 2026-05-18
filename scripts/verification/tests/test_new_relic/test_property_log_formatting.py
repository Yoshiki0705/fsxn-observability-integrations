"""Property-based test for log attribute formatting completeness.

# Feature: new-relic-e2e-verification, Property 6: Log attribute formatting completeness

Validates: Requirements 2.3
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st


def _import_format_function():
    """Import _format_for_new_relic from the Lambda handler module.

    The handler module uses Python 3.10+ type syntax (str | None) and has
    module-level side effects (boto3 client creation, env var reads).
    We patch environment variables and mock boto3/urllib3 to allow import
    on Python 3.9.
    """
    lambda_dir = str(
        Path(__file__).resolve().parents[4]
        / "integrations"
        / "new-relic"
        / "lambda"
    )
    if lambda_dir not in sys.path:
        sys.path.insert(0, lambda_dir)

    # Set required environment variables before importing handler
    env_patches = {
        "API_KEY_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
        "S3_ACCESS_POINT_ARN": "arn:aws:s3:us-east-1:123456789012:accesspoint/test",
        "NEW_RELIC_REGION": "US",
    }
    for key, value in env_patches.items():
        os.environ.setdefault(key, value)

    # On Python < 3.10, the handler's `str | None` annotation fails at runtime.
    # We read the source, prepend `from __future__ import annotations`, and exec it.
    handler_path = Path(lambda_dir) / "handler.py"
    source = handler_path.read_text(encoding="utf-8")

    # Create a module namespace with required dependencies available
    module = types.ModuleType("_nr_handler")
    module.__file__ = str(handler_path)

    # Prepend future annotations to defer type evaluation
    patched_source = "from __future__ import annotations\n" + source

    # Compile and exec in the module's namespace
    code = compile(patched_source, str(handler_path), "exec")
    exec(code, module.__dict__)  # noqa: S102

    return module._format_for_new_relic


_format_for_new_relic = _import_format_function()


# ---------------------------------------------------------------------------
# Hypothesis strategy for FSxN audit log entries
# ---------------------------------------------------------------------------

# Strategy for optional string fields (may or may not be present)
_optional_text = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            blacklist_characters="\x00\n\r",
        ),
        min_size=0,
        max_size=50,
    ),
)

# Strategy for generating a random FSxN audit log entry
_fsxn_audit_log_entry_strategy = st.fixed_dictionaries(
    {},
    optional={
        "EventID": _optional_text,
        "SVMName": _optional_text,
        "UserName": _optional_text,
        "ClientIP": _optional_text,
        "Operation": _optional_text,
        "ObjectName": _optional_text,
        "Result": _optional_text,
    },
).map(lambda d: {k: v for k, v in d.items() if v is not None})


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    log_entries=st.lists(
        _fsxn_audit_log_entry_strategy,
        min_size=1,
        max_size=10,
    ),
    source_key=st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P"),
            blacklist_characters="\x00\n\r",
        ),
        min_size=1,
        max_size=50,
    ),
)
def test_log_attribute_formatting_completeness(
    log_entries: list[dict[str, Any]], source_key: str
) -> None:
    """Property 6: Log attribute formatting completeness.

    For any valid FSxN audit log entry (a JSON object with any combination of
    EventID, SVMName, UserName, ClientIP, Operation, ObjectName, Result fields),
    the _format_for_new_relic function SHALL produce an output where:
    - attributes.source equals "fsxn-ontap"
    - attributes.service equals "ontap-audit"
    - All mandatory attribute keys (source, service, event_type, svm, user,
      operation, result) are present in the attributes dict.

    **Validates: Requirements 2.3**
    """
    result = _format_for_new_relic(log_entries, source_key)

    # Output should have the same number of entries as input
    assert len(result) == len(log_entries)

    # Mandatory attribute keys that must always be present
    mandatory_keys = {"source", "service", "event_type", "svm", "user", "operation", "result"}

    for i, entry in enumerate(result):
        # Each entry must have 'attributes' dict
        assert "attributes" in entry, f"Entry {i} missing 'attributes' key"
        attrs = entry["attributes"]

        # source must always be "fsxn-ontap"
        assert attrs["source"] == "fsxn-ontap", (
            f"Entry {i}: attributes.source = {attrs['source']!r}, expected 'fsxn-ontap'"
        )

        # service must always be "ontap-audit"
        assert attrs["service"] == "ontap-audit", (
            f"Entry {i}: attributes.service = {attrs['service']!r}, expected 'ontap-audit'"
        )

        # All mandatory keys must be present
        for key in mandatory_keys:
            assert key in attrs, (
                f"Entry {i}: mandatory attribute key '{key}' missing from attributes"
            )
