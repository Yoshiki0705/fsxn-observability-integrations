"""Property-based tests for Splunk Serverless integration.

Uses Hypothesis to verify universal correctness properties across
generated inputs. Each property test runs a minimum of 100 iterations.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from hypothesis import given, settings, assume
from hypothesis import strategies as st

sys.modules.pop("handler", None)
import handler


# UUID pattern used by the handler for HEC token validation
_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


# Feature: splunk-serverless-e2e-verification, Property 1: HEC Token Format Validation
# **Validates: Requirements 1.4, 1.5**


class TestHecTokenFormatValidation:
    """Property 1: HEC Token Format Validation.

    For any string value, the HEC token validator SHALL accept it if and only if
    it matches the UUID pattern (8-4-4-4-12 hexadecimal characters separated by
    hyphens). For any string that does not match this pattern, the validator SHALL
    reject it and the Lambda SHALL NOT attempt to send requests to Splunk HEC.
    """

    @given(token=st.uuids())
    @settings(max_examples=100)
    def test_valid_uuid_tokens_are_accepted(self, token):
        """Valid UUID strings should be accepted and cached by get_hec_token.

        **Validates: Requirements 1.4**
        """
        token_str = str(token)

        # Reset cache before each test
        handler._hec_token_cache = None

        with patch("handler.secrets_client") as mock_secrets:
            mock_secrets.get_secret_value.return_value = {
                "SecretString": token_str,
            }

            result = handler.get_hec_token()
            assert result == token_str
            # Token should be cached
            assert handler._hec_token_cache == token_str

    @given(token=st.text())
    @settings(max_examples=100)
    def test_invalid_strings_raise_value_error(self, token):
        """Non-UUID strings should raise ValueError and no HEC request is made.

        **Validates: Requirements 1.5**
        """
        # Filter out strings that happen to match UUID pattern
        assume(not _UUID_PATTERN.match(token.strip()))

        # Reset cache before each test
        handler._hec_token_cache = None

        with (
            patch("handler.secrets_client") as mock_secrets,
            patch("handler.http") as mock_http,
        ):
            mock_secrets.get_secret_value.return_value = {
                "SecretString": token,
            }

            import pytest
            with pytest.raises(ValueError):
                handler.get_hec_token()

            # No HEC request should be attempted
            mock_http.request.assert_not_called()

    @given(
        base=st.uuids(),
        mutation=st.sampled_from([
            "remove_hyphen",
            "add_char",
            "truncate",
            "replace_hex_with_non_hex",
            "add_prefix",
            "add_suffix",
        ]),
    )
    @settings(max_examples=100)
    def test_near_miss_uuids_are_rejected(self, base, mutation):
        """Near-miss UUIDs (slightly malformed) should raise ValueError.

        **Validates: Requirements 1.5**
        """
        token_str = str(base)

        # Apply mutation to create a near-miss UUID
        if mutation == "remove_hyphen":
            # Remove one hyphen
            idx = token_str.index("-")
            token_str = token_str[:idx] + token_str[idx + 1:]
        elif mutation == "add_char":
            # Add an extra character at the end
            token_str = token_str + "f"
        elif mutation == "truncate":
            # Remove last character
            token_str = token_str[:-1]
        elif mutation == "replace_hex_with_non_hex":
            # Replace first hex char with 'g' (non-hex)
            token_str = "g" + token_str[1:]
        elif mutation == "add_prefix":
            # Add non-whitespace prefix
            token_str = "x" + token_str
        elif mutation == "add_suffix":
            # Add non-whitespace suffix
            token_str = token_str + "x"

        # Ensure the mutated token doesn't accidentally match UUID pattern
        assume(not _UUID_PATTERN.match(token_str.strip()))

        # Reset cache before each test
        handler._hec_token_cache = None

        with (
            patch("handler.secrets_client") as mock_secrets,
            patch("handler.http") as mock_http,
        ):
            mock_secrets.get_secret_value.return_value = {
                "SecretString": token_str,
            }

            import pytest
            with pytest.raises(ValueError):
                handler.get_hec_token()

            # No HEC request should be attempted for invalid tokens
            mock_http.request.assert_not_called()


# Feature: splunk-serverless-e2e-verification, Property 5: Graceful Record Skipping
# **Validates: Requirements 2.6**


def _make_s3_record(bucket: str, key: str) -> dict[str, Any]:
    """Create an S3 event record structure."""
    return {
        "eventVersion": "2.1",
        "eventSource": "aws:s3",
        "awsRegion": "ap-northeast-1",
        "eventName": "ObjectCreated:Put",
        "s3": {
            "bucket": {"name": bucket, "arn": f"arn:aws:s3:::{bucket}"},
            "object": {"key": key, "size": 1024},
        },
    }


def _make_audit_log_bytes(num_entries: int) -> bytes:
    """Create NDJSON audit log bytes with the given number of entries."""
    logs = []
    for i in range(num_entries):
        logs.append(json.dumps({
            "timestamp": f"2026-01-15T12:00:{i:02d}Z",
            "EventID": "4663",
            "SVMName": "svm-prod-01",
            "UserName": f"user{i}@corp.local",
            "ClientIP": f"10.0.1.{50 + i}",
            "Operation": "ReadData",
            "ObjectName": f"/vol/data/file{i}.txt",
            "Result": "Success",
        }))
    return "\n".join(logs).encode("utf-8")


# Strategy: generate a list of S3 records (2-5 items), each marked as valid or invalid.
# Uses a composite strategy to ensure unique keys per record.
@st.composite
def _record_strategy(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a list of 2-5 S3 records with unique keys."""
    num_records = draw(st.integers(min_value=2, max_value=5))
    records = []
    for i in range(num_records):
        valid = draw(st.booleans())
        num_logs = draw(st.integers(min_value=1, max_value=5))
        # Use index-based unique keys to avoid duplicate key collisions
        key = f"audit/svm-prod-01/2026/01/15/audit_log_{i:03d}.json"
        records.append({"valid": valid, "key": key, "num_logs": num_logs})
    return records


@settings(max_examples=100)
@given(records=_record_strategy())
def test_graceful_record_skipping(records: list[dict[str, Any]]) -> None:
    """Property 5: Graceful Record Skipping.

    For any S3 event containing multiple records where one or more records
    reference non-existent S3 objects, the Lambda shipper SHALL skip the
    invalid records and continue processing the remaining valid records.
    The final response SHALL include error details for skipped records and
    success counts for processed records.
    """
    # Reset HEC token cache before each test
    handler._hec_token_cache = None

    # Build the multi-record S3 event
    event = {
        "Records": [
            _make_s3_record("fsxn-audit-logs-bucket", r["key"])
            for r in records
        ]
    }

    # Count expected valid and invalid records
    valid_records = [r for r in records if r["valid"]]
    invalid_records = [r for r in records if not r["valid"]]
    expected_total_logs = sum(r["num_logs"] for r in valid_records)

    # Configure mocks
    with (
        patch("handler.secrets_client") as mock_secrets,
        patch("handler.s3_client") as mock_s3,
        patch("handler.http") as mock_http,
    ):
        # Mock Secrets Manager to return valid token
        mock_secrets.get_secret_value.return_value = {
            "SecretString": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        }

        # Configure S3 mock: valid records return audit log bytes,
        # invalid records raise ClientError with NoSuchKey
        def s3_get_object_side_effect(**kwargs: Any) -> dict[str, Any]:
            key = kwargs.get("Key", "")
            # Find the record matching this key
            for r in records:
                if r["key"] == key:
                    if r["valid"]:
                        mock_body = MagicMock()
                        mock_body.read.return_value = _make_audit_log_bytes(r["num_logs"])
                        return {"Body": mock_body}
                    else:
                        raise ClientError(
                            {
                                "Error": {
                                    "Code": "NoSuchKey",
                                    "Message": f"The specified key does not exist: {key}",
                                }
                            },
                            "GetObject",
                        )
            # Fallback: key not found in our records list (shouldn't happen)
            raise ClientError(
                {
                    "Error": {
                        "Code": "NoSuchKey",
                        "Message": f"Key not found: {key}",
                    }
                },
                "GetObject",
            )

        mock_s3.get_object.side_effect = s3_get_object_side_effect

        # Mock HEC calls to succeed
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = json.dumps({"text": "Success", "code": 0}).encode("utf-8")
        mock_http.request.return_value = mock_response

        # Call the handler
        result = handler.lambda_handler(event, None)

    # Assertions
    # 1. Response errors list length == number of invalid records
    assert len(result["body"]["errors"]) == len(invalid_records)

    # 2. Response total_logs counts only valid records' log entries
    assert result["body"]["total_logs"] == expected_total_logs

    # 3. statusCode is 207 if any invalid records, 200 if all valid
    if invalid_records:
        assert result["statusCode"] == 207
    else:
        assert result["statusCode"] == 200


# Feature: splunk-serverless-e2e-verification, Property 4: Retry with Exponential Backoff
# Validates: Requirements 2.4
@settings(max_examples=100)
@given(
    status_code=st.one_of(
        st.just(429), st.integers(min_value=500, max_value=599)
    ),
)
def test_retry_with_exponential_backoff(status_code: int) -> None:
    """Property 4: For any HTTP 429 or 5xx response from Splunk HEC,
    the Lambda shipper retries with exponential backoff up to 3 total attempts.

    Asserts:
    - Exactly 3 HTTP requests are made
    - Exactly 2 sleep calls are made (between attempts)
    - Sleep delays are [2, 4] (base 2s, doubling per attempt)
    - Return value is False (all retries exhausted)
    """
    # Mock HTTP response to always return the generated status code
    mock_response = MagicMock()
    mock_response.status = status_code
    mock_response.data = json.dumps(
        {"text": "Error", "code": 9}
    ).encode("utf-8")

    sleep_delays: list[float] = []

    with (
        patch.object(handler.http, "request", return_value=mock_response) as mock_request,
        patch.object(handler.time, "sleep", side_effect=lambda d: sleep_delays.append(d)) as mock_sleep,
    ):
        payload = json.dumps({"event": "test"})
        token = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        result = handler._send_to_hec(payload, token)

    # Assert exactly 3 HTTP requests made
    assert mock_request.call_count == 3, (
        f"Expected 3 HTTP requests, got {mock_request.call_count}"
    )

    # Assert exactly 2 sleep calls (between attempts, not after final)
    assert mock_sleep.call_count == 2, (
        f"Expected 2 sleep calls, got {mock_sleep.call_count}"
    )

    # Assert sleep delays are [2, 4] (exponential backoff: 2*2^0=2, 2*2^1=4)
    assert sleep_delays == [2, 4], (
        f"Expected sleep delays [2, 4], got {sleep_delays}"
    )

    # Assert return value is False (all retries exhausted)
    assert result is False, "Expected False when all retries exhausted"


# --- Strategies for Property 3 ---

_audit_log_event_st = st.fixed_dictionaries(
    {
        "timestamp": st.from_regex(
            r"2026-01-[0-2][0-9]T[0-1][0-9]:[0-5][0-9]:[0-5][0-9]Z", fullmatch=True
        ),
        "EventID": st.sampled_from(["4663", "4656", "4658", "4660"]),
        "SVMName": st.from_regex(r"svm-[a-z]{3,8}-[0-9]{2}", fullmatch=True),
        "UserName": st.from_regex(r"[a-z]{3,10}@[a-z]{3,8}\.local", fullmatch=True),
        "ClientIP": st.ip_addresses(v=4).map(str),
        "Operation": st.sampled_from(
            ["ReadData", "WriteData", "Open", "Close", "Delete", "Rename"]
        ),
        "ObjectName": st.from_regex(
            r"/vol/[a-z]{3,8}/[a-z]{3,10}\.(txt|docx|xlsx|pdf)", fullmatch=True
        ),
        "Result": st.sampled_from(["Success", "Failure"]),
    }
)


# Feature: splunk-serverless-e2e-verification, Property 3: Response Count Accuracy
# **Validates: Requirements 2.3**


@settings(max_examples=100)
@given(logs=st.lists(_audit_log_event_st, min_size=1, max_size=20))
def test_response_count_accuracy(logs: list[dict[str, Any]]) -> None:
    """Property 3: Response Count Accuracy.

    For any set of S3 event records processed by the Lambda shipper where
    all HEC calls succeed, the response SHALL contain statusCode 200 and
    the total_shipped count SHALL equal the total_logs count, which SHALL
    equal the total number of parsed log events across all processed S3 objects.

    **Validates: Requirements 2.3**
    """
    # Reset token cache before each test
    handler._hec_token_cache = None

    # Build NDJSON bytes from generated logs
    ndjson_bytes = "\n".join(json.dumps(log) for log in logs).encode("utf-8")

    # Construct S3 event with a single record
    s3_event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "fsxn-audit-logs-bucket"},
                    "object": {"key": "audit/svm-test/2026/01/15/audit.json"},
                }
            }
        ]
    }

    with (
        patch("handler.secrets_client") as mock_secrets,
        patch("handler.s3_client") as mock_s3,
        patch("handler.http") as mock_http,
    ):
        # Mock secrets to return valid HEC token
        mock_secrets.get_secret_value.return_value = {
            "SecretString": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        }

        # Mock S3 to return generated logs as NDJSON bytes
        mock_body = MagicMock()
        mock_body.read.return_value = ndjson_bytes
        mock_s3.get_object.return_value = {"Body": mock_body}

        # Mock HEC to always succeed (simulating all success)
        mock_http.request.return_value = MagicMock(
            status=200, data=b'{"text":"Success","code":0}'
        )

        result = handler.lambda_handler(s3_event, None)

    # All HEC calls succeed -> statusCode 200
    assert result["statusCode"] == 200

    # Count accuracy: total_shipped == total_logs == len(logs)
    expected_count = len(logs)
    assert result["body"]["total_logs"] == expected_count
    assert result["body"]["total_shipped"] == expected_count
    assert result["body"]["errors"] == []


# Feature: splunk-serverless-e2e-verification, Property 7: EMS Event Formatting and Forwarding
# **Validates: Requirements 5.1, 5.2**

sys.modules.pop("ems_handler", None)
import ems_handler

# --- Strategies for Property 7 ---

_ems_severity_st = st.sampled_from(["alert", "warning", "notice", "info"])

_ems_timestamp_st = st.from_regex(
    r"2026-01-[0-2][0-9]T[0-1][0-9]:[0-5][0-9]:[0-5][0-9]\+09:00", fullmatch=True
)

_ems_parameters_st = st.dictionaries(
    keys=st.from_regex(r"[a-z][a-z0-9\-]{2,15}", fullmatch=True),
    values=st.text(min_size=1, max_size=50),
    min_size=0,
    max_size=5,
)

_ems_payload_st = st.fixed_dictionaries(
    {
        "message-name": st.from_regex(r"[a-z]{3,10}\.[a-z]{3,10}\.[a-z]{3,10}", fullmatch=True),
        "message-severity": _ems_severity_st,
        "message-timestamp": _ems_timestamp_st,
        "parameters": _ems_parameters_st,
    }
)


@settings(max_examples=100)
@given(payload=_ems_payload_st)
def test_ems_event_formatting_and_forwarding(payload: dict[str, Any]) -> None:
    """Property 7: EMS Event Formatting and Forwarding.

    For any valid EMS event payload containing the required fields
    (message-name, message-severity, message-timestamp), the EMS webhook
    handler SHALL format the event as a Splunk HEC JSON object with
    sourcetype set to "fsxn:ontap:ems", index set to "fsxn_ems", source
    set to "fsxn-ems", and the event body containing all original EMS fields.

    **Validates: Requirements 5.1, 5.2**
    """
    # Call _format_ems_for_splunk directly
    result = ems_handler._format_ems_for_splunk(payload)

    # Assert Splunk HEC metadata fields
    assert result["sourcetype"] == "fsxn:ontap:ems", (
        f"Expected sourcetype 'fsxn:ontap:ems', got '{result['sourcetype']}'"
    )
    assert result["index"] == "fsxn_ems", (
        f"Expected index 'fsxn_ems', got '{result['index']}'"
    )
    assert result["source"] == "fsxn-ems", (
        f"Expected source 'fsxn-ems', got '{result['source']}'"
    )

    # Assert event body contains all original EMS fields
    event = result["event"]
    assert event["message-name"] == payload["message-name"], (
        f"message-name mismatch: expected '{payload['message-name']}', got '{event['message-name']}'"
    )
    assert event["message-severity"] == payload["message-severity"], (
        f"message-severity mismatch: expected '{payload['message-severity']}', got '{event['message-severity']}'"
    )
    assert event["message-timestamp"] == payload["message-timestamp"], (
        f"message-timestamp mismatch: expected '{payload['message-timestamp']}', got '{event['message-timestamp']}'"
    )
    assert event["parameters"] == payload["parameters"], (
        f"parameters mismatch: expected {payload['parameters']}, got {event['parameters']}"
    )


# Feature: splunk-serverless-e2e-verification, Property 8: API Key Authentication
# **Validates: Requirements 5.3, 5.4**


@settings(max_examples=100)
@given(api_key=st.text(min_size=1, max_size=50))
def test_api_key_authentication_invalid_key(api_key: str) -> None:
    """Property 8: API Key Authentication — invalid key path.

    For any incoming request where the x-api-key header value does not match
    the stored secret, the handler SHALL return HTTP 401 and SHALL NOT forward
    the payload to Splunk HEC.

    **Validates: Requirements 5.3, 5.4**
    """
    # Fixed expected key that the mock will return from Secrets Manager
    expected_key = "correct-api-key-for-testing-xyz"

    # Ensure the generated key differs from the expected key
    assume(api_key != expected_key)

    # Reset caches before each test
    ems_handler._api_key_cache = None
    ems_handler._hec_token_cache = None

    # Build a valid EMS payload body so only the API key varies
    valid_body = json.dumps({
        "message-name": "arw.volume.state",
        "message-severity": "alert",
        "message-timestamp": "2026-01-15T12:05:00+09:00",
        "parameters": {"volume-name": "vol1", "vserver-name": "svm-prod-01"},
    })

    # Build API Gateway HTTP API event with the generated (invalid) API key
    event = {
        "version": "2.0",
        "routeKey": "POST /ems",
        "rawPath": "/ems",
        "headers": {
            "content-type": "application/json",
            "x-api-key": api_key,
        },
        "body": valid_body,
        "isBase64Encoded": False,
        "requestContext": {
            "http": {"method": "POST", "path": "/ems"},
            "requestId": "req-test",
        },
    }

    with (
        patch.object(ems_handler, "secrets_client") as mock_secrets,
        patch.object(ems_handler, "http") as mock_http,
    ):
        # Mock Secrets Manager: _get_api_key returns the expected key
        mock_secrets.get_secret_value.return_value = {
            "SecretString": expected_key,
        }

        result = ems_handler.lambda_handler(event, None)

    # Assert 401 returned for invalid API key
    assert result["statusCode"] == 401, (
        f"Expected 401 for invalid key '{api_key}', got {result['statusCode']}"
    )

    # Assert no HEC call was made
    mock_http.request.assert_not_called()


@settings(max_examples=100)
@given(api_key=st.text(min_size=1, max_size=50))
def test_api_key_authentication_valid_key(api_key: str) -> None:
    """Property 8: API Key Authentication — valid key path.

    For any request with a valid x-api-key header (matching the stored secret),
    the handler SHALL proceed with payload processing (returns 200 or 502
    depending on HEC mock).

    **Validates: Requirements 5.3, 5.4**
    """
    # The expected key IS the generated key (valid case)
    expected_key = api_key

    # Reset caches before each test
    ems_handler._api_key_cache = None
    ems_handler._hec_token_cache = None

    # Build a valid EMS payload body
    valid_body = json.dumps({
        "message-name": "arw.volume.state",
        "message-severity": "alert",
        "message-timestamp": "2026-01-15T12:05:00+09:00",
        "parameters": {"volume-name": "vol1", "vserver-name": "svm-prod-01"},
    })

    # Build API Gateway HTTP API event with the valid API key
    event = {
        "version": "2.0",
        "routeKey": "POST /ems",
        "rawPath": "/ems",
        "headers": {
            "content-type": "application/json",
            "x-api-key": api_key,
        },
        "body": valid_body,
        "isBase64Encoded": False,
        "requestContext": {
            "http": {"method": "POST", "path": "/ems"},
            "requestId": "req-test",
        },
    }

    with (
        patch.object(ems_handler, "secrets_client") as mock_secrets,
        patch.object(ems_handler, "http") as mock_http,
    ):
        # Mock Secrets Manager: both API key and HEC token
        def get_secret_side_effect(**kwargs):
            """Return appropriate secret based on SecretId."""
            secret_id = kwargs.get("SecretId", "")
            if "api-key" in secret_id.lower() or secret_id == ems_handler.EMS_API_KEY_SECRET_ARN:
                return {"SecretString": expected_key}
            # HEC token
            return {"SecretString": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}

        mock_secrets.get_secret_value.side_effect = get_secret_side_effect

        # Mock HEC to succeed
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = json.dumps({"text": "Success", "code": 0}).encode("utf-8")
        mock_http.request.return_value = mock_response

        result = ems_handler.lambda_handler(event, None)

    # Assert processing proceeded (not 401)
    assert result["statusCode"] != 401, (
        f"Expected non-401 for valid key, got {result['statusCode']}"
    )
    # Valid key should result in 200 (success) or 502 (HEC failure)
    assert result["statusCode"] in (200, 502), (
        f"Expected 200 or 502 for valid key, got {result['statusCode']}"
    )

    # Assert HEC call was made (processing proceeded past auth)
    mock_http.request.assert_called()


@settings(max_examples=100)
@given(data=st.data())
def test_api_key_authentication_missing_header(data: st.DataObject) -> None:
    """Property 8: API Key Authentication — missing header path.

    For any request where the x-api-key header is missing entirely,
    the handler SHALL return HTTP 401 and SHALL NOT forward the payload
    to Splunk HEC.

    **Validates: Requirements 5.3, 5.4**
    """
    # Generate a random expected key (doesn't matter since header is missing)
    expected_key = data.draw(st.text(min_size=1, max_size=50))

    # Reset caches before each test
    ems_handler._api_key_cache = None
    ems_handler._hec_token_cache = None

    # Build a valid EMS payload body
    valid_body = json.dumps({
        "message-name": "arw.volume.state",
        "message-severity": "alert",
        "message-timestamp": "2026-01-15T12:05:00+09:00",
        "parameters": {"volume-name": "vol1", "vserver-name": "svm-prod-01"},
    })

    # Build API Gateway HTTP API event WITHOUT x-api-key header
    event = {
        "version": "2.0",
        "routeKey": "POST /ems",
        "rawPath": "/ems",
        "headers": {
            "content-type": "application/json",
            # No x-api-key header
        },
        "body": valid_body,
        "isBase64Encoded": False,
        "requestContext": {
            "http": {"method": "POST", "path": "/ems"},
            "requestId": "req-test",
        },
    }

    with (
        patch.object(ems_handler, "secrets_client") as mock_secrets,
        patch.object(ems_handler, "http") as mock_http,
    ):
        # Mock Secrets Manager
        mock_secrets.get_secret_value.return_value = {
            "SecretString": expected_key,
        }

        result = ems_handler.lambda_handler(event, None)

    # Assert 401 returned for missing API key
    assert result["statusCode"] == 401, (
        f"Expected 401 for missing x-api-key header, got {result['statusCode']}"
    )

    # Assert no HEC call was made
    mock_http.request.assert_not_called()


# Feature: splunk-serverless-e2e-verification, Property 9: EMS Payload Validation
# **Validates: Requirements 5.7**


# Strategy: generate a subset of required fields to remove (at least 1)
_required_ems_fields = ["message-name", "message-severity", "message-timestamp"]

_fields_to_remove_st = st.sets(
    st.sampled_from(["message-name", "message-severity", "message-timestamp"]),
    min_size=1,
)


@settings(max_examples=100)
@given(
    fields_to_remove=_fields_to_remove_st,
    message_name=st.from_regex(r"[a-z]{3,10}\.[a-z]{3,10}\.[a-z]{3,10}", fullmatch=True),
    message_severity=_ems_severity_st,
    message_timestamp=_ems_timestamp_st,
    parameters=_ems_parameters_st,
)
def test_ems_payload_validation_direct(
    fields_to_remove: set[str],
    message_name: str,
    message_severity: str,
    message_timestamp: str,
    parameters: dict[str, Any],
) -> None:
    """Property 9: EMS Payload Validation (direct validation function).

    For any EMS event payload missing one or more of the required fields
    (message-name, message-severity, message-timestamp), the EMS webhook
    handler SHALL return the exact set of missing required field names.

    **Validates: Requirements 5.7**
    """
    # Build a complete payload
    payload: dict[str, Any] = {
        "message-name": message_name,
        "message-severity": message_severity,
        "message-timestamp": message_timestamp,
        "parameters": parameters,
    }

    # Remove the selected subset of required fields
    for field in fields_to_remove:
        del payload[field]

    # Call _validate_ems_payload directly
    missing_fields = ems_handler._validate_ems_payload(payload)

    # Assert the returned list of missing fields exactly matches the removed subset
    assert set(missing_fields) == fields_to_remove, (
        f"Expected missing fields {fields_to_remove}, got {set(missing_fields)}"
    )


@settings(max_examples=100)
@given(
    fields_to_remove=_fields_to_remove_st,
    message_name=st.from_regex(r"[a-z]{3,10}\.[a-z]{3,10}\.[a-z]{3,10}", fullmatch=True),
    message_severity=_ems_severity_st,
    message_timestamp=_ems_timestamp_st,
    parameters=_ems_parameters_st,
)
def test_ems_payload_validation_via_lambda_handler(
    fields_to_remove: set[str],
    message_name: str,
    message_severity: str,
    message_timestamp: str,
    parameters: dict[str, Any],
) -> None:
    """Property 9: EMS Payload Validation (via lambda_handler).

    For any EMS event payload missing one or more of the required fields,
    the EMS webhook handler SHALL return HTTP 400 with a JSON body containing
    missing_fields that lists exactly the set of missing required field names.

    **Validates: Requirements 5.7**
    """
    # Build a complete payload
    payload: dict[str, Any] = {
        "message-name": message_name,
        "message-severity": message_severity,
        "message-timestamp": message_timestamp,
        "parameters": parameters,
    }

    # Remove the selected subset of required fields
    for field in fields_to_remove:
        del payload[field]

    # Build API Gateway HTTP API event
    api_event = {
        "version": "2.0",
        "routeKey": "POST /ems",
        "rawPath": "/ems",
        "headers": {
            "content-type": "application/json",
            "x-api-key": "valid-test-key-12345",
        },
        "body": json.dumps(payload),
        "isBase64Encoded": False,
    }

    # Reset EMS handler caches
    ems_handler._api_key_cache = None

    with patch.object(ems_handler, "secrets_client") as mock_secrets:
        # Mock API key validation to pass
        mock_secrets.get_secret_value.return_value = {
            "SecretString": "valid-test-key-12345",
        }

        result = ems_handler.lambda_handler(api_event, None)

    # Assert HTTP 400 response
    assert result["statusCode"] == 400, (
        f"Expected statusCode 400, got {result['statusCode']}"
    )

    # Parse response body
    body = json.loads(result["body"])

    # Assert missing_fields matches the removed subset
    assert set(body["missing_fields"]) == fields_to_remove, (
        f"Expected missing_fields {fields_to_remove}, got {set(body['missing_fields'])}"
    )
