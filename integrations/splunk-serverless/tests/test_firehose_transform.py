"""Unit tests for Firehose transformation Lambda handler.

Tests the firehose_transform.lambda_handler function which converts
FSx ONTAP audit log records from Firehose into Splunk HEC event JSON format.
"""

import base64
import json
from typing import Any

import pytest

from firehose_transform import lambda_handler


def _make_firehose_record(record_id: str, data: str) -> dict[str, str]:
    """Create a Firehose record with base64-encoded data.

    Args:
        record_id: Unique record identifier.
        data: Raw string data to base64-encode.

    Returns:
        Firehose record dict with recordId and base64-encoded data.
    """
    encoded = base64.b64encode(data.encode("utf-8")).decode("utf-8")
    return {"recordId": record_id, "data": encoded}


def _make_firehose_event(records: list[dict[str, str]]) -> dict[str, Any]:
    """Create a Firehose transformation event.

    Args:
        records: List of Firehose record dicts.

    Returns:
        Firehose transformation event dict.
    """
    return {"records": records}


class TestValidRecordTransformation:
    """Tests for valid audit log records producing Ok results."""

    def test_valid_record_returns_ok_result(self) -> None:
        """Valid audit log record should produce result 'Ok'."""
        audit_log = json.dumps({
            "timestamp": "2026-01-15T12:00:01Z",
            "EventID": "4663",
            "SVMName": "svm-prod-01",
            "UserName": "admin@corp.local",
            "ClientIP": "10.0.1.50",
            "Operation": "ReadData",
            "ObjectName": "/vol/data/reports/quarterly.xlsx",
            "Result": "Success",
        })
        record = _make_firehose_record("rec-001", audit_log)
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)

        assert len(response["records"]) == 1
        output = response["records"][0]
        assert output["recordId"] == "rec-001"
        assert output["result"] == "Ok"

    def test_valid_record_output_is_base64_hec_json(self) -> None:
        """Valid record output data should be base64-encoded HEC JSON."""
        audit_log = json.dumps({
            "timestamp": "2026-01-15T12:00:01Z",
            "EventID": "4663",
            "SVMName": "svm-prod-01",
            "UserName": "admin@corp.local",
            "ClientIP": "10.0.1.50",
            "Operation": "ReadData",
            "ObjectName": "/vol/data/reports/quarterly.xlsx",
            "Result": "Success",
        })
        record = _make_firehose_record("rec-001", audit_log)
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)
        output = response["records"][0]

        # Decode base64 output data
        decoded = base64.b64decode(output["data"]).decode("utf-8")
        hec_event = json.loads(decoded)

        # Verify HEC JSON structure
        assert "host" in hec_event
        assert "source" in hec_event
        assert "sourcetype" in hec_event
        assert "event" in hec_event

    def test_valid_record_hec_json_fields(self) -> None:
        """HEC JSON should contain correct field values."""
        audit_log = json.dumps({
            "timestamp": "2026-01-15T12:00:01Z",
            "EventID": "4663",
            "SVMName": "svm-prod-01",
            "UserName": "admin@corp.local",
            "ClientIP": "10.0.1.50",
            "Operation": "ReadData",
            "ObjectName": "/vol/data/reports/quarterly.xlsx",
            "Result": "Success",
        })
        record = _make_firehose_record("rec-001", audit_log)
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)
        output = response["records"][0]

        decoded = base64.b64decode(output["data"]).decode("utf-8")
        hec_event = json.loads(decoded)

        assert hec_event["host"] == "svm-prod-01"
        assert hec_event["source"] == "fsxn-observability"
        assert hec_event["sourcetype"] == "fsxn:ontap:audit"
        assert hec_event["time"] is not None

        # Verify event sub-object
        event_data = hec_event["event"]
        assert event_data["event_type"] == "4663"
        assert event_data["user"] == "admin@corp.local"
        assert event_data["client_ip"] == "10.0.1.50"
        assert event_data["operation"] == "ReadData"
        assert event_data["path"] == "/vol/data/reports/quarterly.xlsx"
        assert event_data["result"] == "Success"
        assert event_data["svm"] == "svm-prod-01"

    def test_valid_record_timestamp_conversion(self) -> None:
        """Timestamp should be converted to epoch seconds."""
        audit_log = json.dumps({
            "timestamp": "2026-01-15T12:00:00Z",
            "EventID": "4663",
            "SVMName": "svm-prod-01",
        })
        record = _make_firehose_record("rec-ts", audit_log)
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)
        output = response["records"][0]

        decoded = base64.b64decode(output["data"]).decode("utf-8")
        hec_event = json.loads(decoded)

        # Epoch for 2026-01-15T12:00:00Z
        assert isinstance(hec_event["time"], float)
        assert hec_event["time"] > 0


class TestInvalidRecordFormat:
    """Tests for invalid record formats producing ProcessingFailed."""

    def test_non_json_data_returns_processing_failed(self) -> None:
        """Non-JSON data should result in ProcessingFailed."""
        record = _make_firehose_record("rec-bad-001", "this is not json")
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)

        output = response["records"][0]
        assert output["recordId"] == "rec-bad-001"
        assert output["result"] == "ProcessingFailed"

    def test_json_array_returns_processing_failed(self) -> None:
        """JSON array (not object) should result in ProcessingFailed."""
        record = _make_firehose_record("rec-bad-002", json.dumps([1, 2, 3]))
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)

        output = response["records"][0]
        assert output["recordId"] == "rec-bad-002"
        assert output["result"] == "ProcessingFailed"

    def test_json_string_returns_processing_failed(self) -> None:
        """JSON string (not object) should result in ProcessingFailed."""
        record = _make_firehose_record("rec-bad-003", json.dumps("just a string"))
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)

        output = response["records"][0]
        assert output["recordId"] == "rec-bad-003"
        assert output["result"] == "ProcessingFailed"

    def test_processing_failed_preserves_original_data(self) -> None:
        """ProcessingFailed records should preserve original base64 data."""
        raw_data = "this is not json"
        encoded_data = base64.b64encode(raw_data.encode("utf-8")).decode("utf-8")
        record = {"recordId": "rec-preserve", "data": encoded_data}
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)

        output = response["records"][0]
        assert output["result"] == "ProcessingFailed"
        assert output["data"] == encoded_data


class TestJsonParseError:
    """Tests for JSON parse errors producing ProcessingFailed."""

    def test_malformed_json_returns_processing_failed(self) -> None:
        """Malformed JSON should result in ProcessingFailed."""
        record = _make_firehose_record("rec-parse-001", '{"key": "value",}')
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)

        output = response["records"][0]
        assert output["recordId"] == "rec-parse-001"
        assert output["result"] == "ProcessingFailed"

    def test_truncated_json_returns_processing_failed(self) -> None:
        """Truncated JSON should result in ProcessingFailed."""
        record = _make_firehose_record("rec-parse-002", '{"EventID": "4663", "SVMName":')
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)

        output = response["records"][0]
        assert output["recordId"] == "rec-parse-002"
        assert output["result"] == "ProcessingFailed"

    def test_empty_string_returns_processing_failed(self) -> None:
        """Empty string should result in ProcessingFailed."""
        record = _make_firehose_record("rec-parse-003", "")
        event = _make_firehose_event([record])

        response = lambda_handler(event, None)

        output = response["records"][0]
        assert output["recordId"] == "rec-parse-003"
        assert output["result"] == "ProcessingFailed"


class TestMultipleRecordsMixed:
    """Tests for multiple records with mixed valid/invalid data."""

    def test_mixed_records_processed_independently(self) -> None:
        """Each record should be processed independently; valid ones succeed."""
        valid_log = json.dumps({
            "timestamp": "2026-01-15T12:00:01Z",
            "EventID": "4663",
            "SVMName": "svm-prod-01",
            "UserName": "admin@corp.local",
            "Operation": "ReadData",
            "ObjectName": "/vol/data/file.txt",
            "Result": "Success",
        })
        records = [
            _make_firehose_record("rec-valid-1", valid_log),
            _make_firehose_record("rec-invalid-1", "not json"),
            _make_firehose_record("rec-valid-2", valid_log),
            _make_firehose_record("rec-invalid-2", '{"broken":'),
        ]
        event = _make_firehose_event(records)

        response = lambda_handler(event, None)

        assert len(response["records"]) == 4

        # Valid records
        assert response["records"][0]["recordId"] == "rec-valid-1"
        assert response["records"][0]["result"] == "Ok"
        assert response["records"][2]["recordId"] == "rec-valid-2"
        assert response["records"][2]["result"] == "Ok"

        # Invalid records
        assert response["records"][1]["recordId"] == "rec-invalid-1"
        assert response["records"][1]["result"] == "ProcessingFailed"
        assert response["records"][3]["recordId"] == "rec-invalid-2"
        assert response["records"][3]["result"] == "ProcessingFailed"

    def test_all_valid_records_return_ok(self) -> None:
        """All valid records should return Ok."""
        logs = [
            json.dumps({
                "timestamp": "2026-01-15T12:00:01Z",
                "EventID": "4663",
                "SVMName": "svm-prod-01",
                "Operation": "ReadData",
            }),
            json.dumps({
                "timestamp": "2026-01-15T12:00:02Z",
                "EventID": "4656",
                "SVMName": "svm-prod-02",
                "Operation": "Open",
            }),
        ]
        records = [
            _make_firehose_record(f"rec-{i}", log)
            for i, log in enumerate(logs)
        ]
        event = _make_firehose_event(records)

        response = lambda_handler(event, None)

        assert all(r["result"] == "Ok" for r in response["records"])

    def test_all_invalid_records_return_processing_failed(self) -> None:
        """All invalid records should return ProcessingFailed."""
        records = [
            _make_firehose_record("rec-0", "bad data 1"),
            _make_firehose_record("rec-1", "bad data 2"),
            _make_firehose_record("rec-2", "{incomplete"),
        ]
        event = _make_firehose_event(records)

        response = lambda_handler(event, None)

        assert all(r["result"] == "ProcessingFailed" for r in response["records"])

    def test_empty_records_list(self) -> None:
        """Empty records list should return empty output."""
        event = _make_firehose_event([])

        response = lambda_handler(event, None)

        assert response["records"] == []
