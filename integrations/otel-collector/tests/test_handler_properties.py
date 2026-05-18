"""Property-based tests for OTel Collector Lambda handler.

Uses Hypothesis to verify universal properties of the OTLP payload
construction and field mapping logic.
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Add lambda directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))

import handler


# ─── Strategies ────────────────────────────────────────────────────────────

# Strategy for generating random audit log records
audit_log_fields = st.fixed_dictionaries(
    {},
    optional={
        "Timestamp": st.one_of(
            st.datetimes(
                min_value=datetime(2020, 1, 1),
                max_value=datetime(2030, 12, 31),
                timezones=st.just(timezone.utc),
            ).map(lambda dt: dt.isoformat()),
            st.just(""),
            st.just(None),
        ),
        "EventID": st.one_of(st.text(min_size=1, max_size=10), st.just(""), st.just(None)),
        "SVMName": st.one_of(st.text(min_size=1, max_size=50), st.just(""), st.just(None)),
        "UserName": st.one_of(st.text(min_size=1, max_size=100), st.just(""), st.just(None)),
        "ClientIP": st.one_of(st.text(min_size=1, max_size=45), st.just(""), st.just(None)),
        "Operation": st.one_of(st.text(min_size=1, max_size=50), st.just(""), st.just(None)),
        "ObjectName": st.one_of(st.text(min_size=1, max_size=200), st.just(""), st.just(None)),
        "Result": st.one_of(st.text(min_size=1, max_size=100), st.just(""), st.just(None)),
    },
)

audit_log_list = st.lists(audit_log_fields, min_size=1, max_size=50)


# ─── Property 1: OTLP payload structural completeness ─────────────────────
# Feature: otel-collector-e2e-verification, Property 1: OTLP payload structural completeness


class TestProperty1OtlpStructuralCompleteness:
    """Property 1: OTLP payload structural completeness.

    For any list of valid FSx ONTAP audit log records (1 or more),
    building the OTLP payload SHALL produce a JSON structure where:
    (a) resourceLogs is a non-empty array,
    (b) each resourceLogs entry contains resource.attributes with keys
        service.name, cloud.provider, and cloud.platform,
    (c) each resourceLogs entry contains scopeLogs with at least one
        logRecords array,
    (d) each logRecord contains timeUnixNano (non-empty string),
        severityText (either "INFO" or "WARN"), and body (with stringValue key).

    **Validates: Requirements 2.2**
    """

    @given(logs=audit_log_list)
    @settings(max_examples=100)
    def test_otlp_payload_structural_completeness(self, logs):
        """OTLP payload has correct nested structure for any valid input."""
        payload = handler.build_otlp_payload(logs, "fsxn-audit", "test/key.json")

        # (a) resourceLogs is a non-empty array
        assert "resourceLogs" in payload
        assert isinstance(payload["resourceLogs"], list)
        assert len(payload["resourceLogs"]) > 0

        for resource_log in payload["resourceLogs"]:
            # (b) resource.attributes contains required keys
            assert "resource" in resource_log
            assert "attributes" in resource_log["resource"]
            attr_keys = {
                a["key"] for a in resource_log["resource"]["attributes"]
            }
            assert "service.name" in attr_keys
            assert "cloud.provider" in attr_keys
            assert "cloud.platform" in attr_keys

            # (c) scopeLogs contains logRecords
            assert "scopeLogs" in resource_log
            assert len(resource_log["scopeLogs"]) > 0
            for scope_log in resource_log["scopeLogs"]:
                assert "logRecords" in scope_log
                assert isinstance(scope_log["logRecords"], list)

                # (d) each logRecord has required fields
                for log_record in scope_log["logRecords"]:
                    assert "timeUnixNano" in log_record
                    assert isinstance(log_record["timeUnixNano"], str)
                    assert len(log_record["timeUnixNano"]) > 0

                    assert "severityText" in log_record
                    assert log_record["severityText"] in ("INFO", "WARN")

                    assert "body" in log_record
                    assert "stringValue" in log_record["body"]


# ─── Property 2: Field mapping correctness ─────────────────────────────────
# Feature: otel-collector-e2e-verification, Property 2: Field mapping correctness


class TestProperty2FieldMappingCorrectness:
    """Property 2: Field mapping correctness.

    For any FSx ONTAP audit log record where a mapped field is present
    and non-empty, the corresponding OTLP attribute SHALL appear with
    the same string value. For absent/empty fields, the attribute SHALL
    NOT appear.

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.12**
    """

    @given(log=audit_log_fields)
    @settings(max_examples=100)
    def test_field_mapping_correctness(self, log):
        """Mapped fields appear correctly; absent/empty fields are omitted."""
        log_record = handler.map_log_record(log)

        # Build lookup of output attributes
        attr_map = {
            a["key"]: a["value"]["stringValue"]
            for a in log_record["attributes"]
        }

        for source_field, otlp_key in handler.FIELD_MAPPING.items():
            value = log.get(source_field)
            if value is not None and value != "":
                # Present non-empty → attribute exists with same value
                assert otlp_key in attr_map, (
                    f"Expected {otlp_key} for {source_field}={value!r}"
                )
                assert attr_map[otlp_key] == str(value)
            else:
                # Absent or empty → attribute NOT in output
                assert otlp_key not in attr_map, (
                    f"Expected {otlp_key} to be absent for {source_field}={value!r}"
                )


# ─── Property 3: Severity determination ────────────────────────────────────
# Feature: otel-collector-e2e-verification, Property 3: Severity determination from Result field


class TestProperty3SeverityDetermination:
    """Property 3: Severity determination from Result field.

    For any string containing "fail", "denied", or "error" (case-insensitive),
    determine_severity SHALL return (13, "WARN"). For any string NOT containing
    those substrings, it SHALL return (9, "INFO").

    **Validates: Requirements 4.8, 4.9**
    """

    @given(
        base_text=st.text(min_size=0, max_size=50),
        keyword=st.sampled_from(["fail", "denied", "error"]),
        position=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_severity_warn_when_keyword_present(self, base_text, keyword, position):
        """Result containing warn keywords → (13, WARN)."""
        # Insert keyword at a position in the text
        pos = min(position, len(base_text))
        result_str = base_text[:pos] + keyword + base_text[pos:]

        severity_num, severity_text = handler.determine_severity(result_str)
        assert severity_num == 13
        assert severity_text == "WARN"

    @given(result_str=st.text(min_size=0, max_size=100))
    @settings(max_examples=100)
    def test_severity_info_when_no_keyword(self, result_str):
        """Result without warn keywords → (9, INFO)."""
        lower = result_str.lower()
        assume("fail" not in lower and "denied" not in lower and "error" not in lower)

        severity_num, severity_text = handler.determine_severity(result_str)
        assert severity_num == 9
        assert severity_text == "INFO"

    def test_severity_none_input(self):
        """None input → (9, INFO)."""
        assert handler.determine_severity(None) == (9, "INFO")

    def test_severity_empty_input(self):
        """Empty string → (9, INFO)."""
        assert handler.determine_severity("") == (9, "INFO")


# ─── Property 4: Timestamp conversion round-trip ───────────────────────────
# Feature: otel-collector-e2e-verification, Property 4: Timestamp conversion round-trip


class TestProperty4TimestampConversion:
    """Property 4: Timestamp conversion round-trip.

    For any valid ISO 8601 timestamp with timezone, converting to Unix
    nanoseconds and back SHALL equal the original to within 1 microsecond.

    **Validates: Requirements 4.10**
    """

    @given(
        dt=st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    @settings(max_examples=100)
    def test_timestamp_round_trip(self, dt):
        """ISO 8601 → Unix nano → datetime equals original within 1μs."""
        iso_str = dt.isoformat()
        nano_str = handler.timestamp_to_unix_nano(iso_str)

        # Convert back
        nano_int = int(nano_str)
        recovered_ts = nano_int / 1_000_000_000
        recovered_dt = datetime.fromtimestamp(recovered_ts, tz=timezone.utc)

        # Assert equality within 1 microsecond
        diff = abs((recovered_dt - dt).total_seconds())
        assert diff < 0.000001, f"Diff {diff}s exceeds 1μs: {dt} vs {recovered_dt}"

    @given(
        dt=st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31),
            timezones=st.timezones(),
        )
    )
    @settings(max_examples=100)
    def test_timestamp_with_various_timezones(self, dt):
        """Timestamps with various timezone offsets convert correctly."""
        iso_str = dt.isoformat()
        nano_str = handler.timestamp_to_unix_nano(iso_str)

        # Convert back to UTC
        nano_int = int(nano_str)
        recovered_ts = nano_int / 1_000_000_000
        recovered_dt = datetime.fromtimestamp(recovered_ts, tz=timezone.utc)

        # Compare in UTC
        original_utc = dt.astimezone(timezone.utc)
        diff = abs((recovered_dt - original_utc).total_seconds())
        assert diff < 0.000001, f"Diff {diff}s exceeds 1μs"


# ─── Property 5: Successful delivery response correctness ─────────────────
# Feature: otel-collector-e2e-verification, Property 5: Successful delivery response correctness


class TestProperty5DeliveryResponse:
    """Property 5: Successful delivery response correctness.

    For any list of N audit log records where the OTLP endpoint returns
    HTTP 200, the Lambda handler SHALL return statusCode 200 with
    total_shipped == total_logs == N.

    **Validates: Requirements 2.3**
    """

    @given(logs=st.lists(audit_log_fields, min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_successful_delivery_response(self, logs):
        """All logs shipped successfully → statusCode 200, counts match."""
        json_data = "\n".join(json.dumps(log) for log in logs)

        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": "audit/test.json"},
                    }
                }
            ]
        }

        # Mock S3 to return our logs
        mock_body = MagicMock()
        mock_body.read.return_value = json_data.encode("utf-8")

        # Mock HTTP to return 200
        mock_response = MagicMock()
        mock_response.status = 200

        with patch("handler.s3_client") as mock_s3, \
             patch("handler.http") as mock_http, \
             patch("handler.secrets_client") as mock_secrets, \
             patch.dict("os.environ", {"API_KEY_SECRET_ARN": ""}):
            # Clear API key cache
            handler._api_key_cache = None
            handler.API_KEY_SECRET_ARN = ""

            mock_s3.get_object.return_value = {"Body": mock_body}
            mock_http.request.return_value = mock_response

            result = handler.lambda_handler(event, None)

            # Restore
            handler.API_KEY_SECRET_ARN = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:otel-auth"

        assert result["statusCode"] == 200
        assert result["body"]["total_logs"] == len(logs)
        assert result["body"]["total_shipped"] == len(logs)
        assert result["body"]["errors"] == []
