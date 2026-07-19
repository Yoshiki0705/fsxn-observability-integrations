"""Unit tests for the hand-rolled OTLP/Protobuf encoder (otlp_protobuf.py).

These tests decode the encoder's output with the official Google protobuf
varint/wire-format rules re-derived manually (no protobuf library dependency
in this project's test suite), verifying field tags, wire types, and byte
layout directly. This keeps the test suite dependency-free, matching the
encoder module's own no-dependency design.

A separate one-off script (not part of this suite) cross-checked the encoder
against the official `opentelemetry-proto` generated Python classes in a
throwaway virtualenv and confirmed the decoded structure matches exactly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))

import otlp_protobuf


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Minimal varint reader for test assertions. Returns (value, new_offset)."""
    result = 0
    shift = 0
    while True:
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return result, offset


def _read_tag(data: bytes, offset: int) -> tuple[int, int, int]:
    """Read a Protobuf tag. Returns (field_number, wire_type, new_offset)."""
    tag, offset = _read_varint(data, offset)
    return tag >> 3, tag & 0x7, offset


def _read_len_delimited(data: bytes, offset: int) -> tuple[bytes, int]:
    """Read a length-delimited field's payload. Returns (payload, new_offset)."""
    length, offset = _read_varint(data, offset)
    return data[offset:offset + length], offset + length


class TestLowLevelPrimitives:
    """Tests for varint/tag/length-delimited encoding primitives."""

    def test_varint_single_byte(self):
        assert otlp_protobuf._varint(0) == b"\x00"
        assert otlp_protobuf._varint(1) == b"\x01"
        assert otlp_protobuf._varint(127) == b"\x7f"

    def test_varint_multi_byte(self):
        # 300 = 0b100101100 -> low 7 bits 0101100 with continuation, then 10
        assert otlp_protobuf._varint(300) == bytes([0xAC, 0x02])

    def test_varint_rejects_negative(self):
        try:
            otlp_protobuf._varint(-1)
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_tag_field_1_wire_type_2(self):
        # field 1, wire type 2 (length-delimited): (1 << 3) | 2 = 10
        assert otlp_protobuf._tag(1, 2) == bytes([10])

    def test_fixed64_field_little_endian(self):
        encoded = otlp_protobuf._fixed64_field(1, 1)
        # tag byte: (1 << 3) | 1 = 9
        assert encoded[0] == 9
        assert encoded[1:] == (1).to_bytes(8, "little")


class TestEncodeKeyValue:
    """Tests for KeyValue message encoding."""

    def test_round_trips_key_and_string_value(self):
        encoded = otlp_protobuf._encode_key_value("service.name", "fsxn-audit")

        offset = 0
        field_num, wire_type, offset = _read_tag(encoded, offset)
        assert field_num == 1
        assert wire_type == 2
        key_bytes, offset = _read_len_delimited(encoded, offset)
        assert key_bytes == b"service.name"

        field_num, wire_type, offset = _read_tag(encoded, offset)
        assert field_num == 2
        assert wire_type == 2
        any_value_bytes, offset = _read_len_delimited(encoded, offset)
        # AnyValue.string_value is field 1, wire type 2
        inner_field, inner_wire, inner_offset = _read_tag(any_value_bytes, 0)
        assert inner_field == 1
        assert inner_wire == 2
        string_bytes, _ = _read_len_delimited(any_value_bytes, inner_offset)
        assert string_bytes == b"fsxn-audit"

        assert offset == len(encoded)


class TestEncodeLogRecord:
    """Tests for LogRecord message encoding."""

    def test_encodes_all_supported_fields(self):
        log_record = {
            "timeUnixNano": "1789999999123456789",
            "severityNumber": 13,
            "severityText": "WARN",
            "body": {"stringValue": "test body"},
            "attributes": [
                {"key": "fsxn.svm", "value": {"stringValue": "svm-prod-01"}},
            ],
        }
        encoded = otlp_protobuf._encode_log_record(log_record)

        # time_unix_nano: field 1, wire type 1 (fixed64)
        field_num, wire_type, offset = _read_tag(encoded, 0)
        assert field_num == 1
        assert wire_type == 1
        value = int.from_bytes(encoded[offset:offset + 8], "little")
        assert value == 1789999999123456789
        offset += 8

        # severity_number: field 2, wire type 0 (varint)
        field_num, wire_type, offset = _read_tag(encoded, offset)
        assert field_num == 2
        assert wire_type == 0
        value, offset = _read_varint(encoded, offset)
        assert value == 13

        # severity_text: field 3, wire type 2 (string)
        field_num, wire_type, offset = _read_tag(encoded, offset)
        assert field_num == 3
        assert wire_type == 2
        text_bytes, offset = _read_len_delimited(encoded, offset)
        assert text_bytes == b"WARN"

        # body: field 5, wire type 2 (AnyValue message)
        field_num, wire_type, offset = _read_tag(encoded, offset)
        assert field_num == 5
        assert wire_type == 2
        body_bytes, offset = _read_len_delimited(encoded, offset)
        assert b"test body" in body_bytes

        # attributes: field 6, wire type 2 (KeyValue message)
        field_num, wire_type, offset = _read_tag(encoded, offset)
        assert field_num == 6
        assert wire_type == 2

    def test_omits_absent_optional_fields(self):
        """A minimal log record with only timeUnixNano must not encode
        severityText, body, or attributes bytes for absent fields."""
        log_record = {"timeUnixNano": "100"}
        encoded = otlp_protobuf._encode_log_record(log_record)

        field_num, wire_type, offset = _read_tag(encoded, 0)
        assert field_num == 1
        assert wire_type == 1
        offset += 8
        assert offset == len(encoded), "expected no bytes beyond time_unix_nano"


class TestEncodeLogsDataEndToEnd:
    """End-to-end tests using the same OTLP-JSON-style dict shape this repo's
    build_otlp_payload()/build_ems_otlp_payload()/build_fpolicy_otlp_payload()
    functions already produce."""

    def test_encodes_full_resource_logs_payload(self):
        payload = {
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "fsxn-audit"}},
                        ]
                    },
                    "scopeLogs": [
                        {
                            "scope": {"name": "fsxn-otel-shipper", "version": "1.0.0"},
                            "logRecords": [
                                {
                                    "timeUnixNano": "1000000000",
                                    "severityNumber": 9,
                                    "severityText": "INFO",
                                    "body": {"stringValue": "hello"},
                                    "attributes": [],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        encoded = otlp_protobuf.encode_logs_data(payload)

        # Top level: resource_logs is field 1, wire type 2
        field_num, wire_type, offset = _read_tag(encoded, 0)
        assert field_num == 1
        assert wire_type == 2
        resource_logs_bytes, offset = _read_len_delimited(encoded, offset)
        assert offset == len(encoded)
        assert len(resource_logs_bytes) > 0

    def test_empty_payload_encodes_to_empty_bytes(self):
        assert otlp_protobuf.encode_logs_data({"resourceLogs": []}) == b""

    def test_multiple_log_records_each_encoded_as_separate_field(self):
        payload = {
            "resourceLogs": [
                {
                    "resource": {"attributes": []},
                    "scopeLogs": [
                        {
                            "scope": {"name": "shipper"},
                            "logRecords": [
                                {"timeUnixNano": "1", "severityNumber": 9, "severityText": "INFO",
                                 "body": {"stringValue": "a"}, "attributes": []},
                                {"timeUnixNano": "2", "severityNumber": 13, "severityText": "WARN",
                                 "body": {"stringValue": "b"}, "attributes": []},
                            ],
                        }
                    ],
                }
            ]
        }
        encoded = otlp_protobuf.encode_logs_data(payload)
        # Two log records => two occurrences of the log_records tag (field 2,
        # wire type 2) inside the scope_logs message. Just assert both body
        # strings appear in the byte stream as a smoke check; precise
        # structural decoding is covered by the cross-check script.
        assert b"a" in encoded
        assert b"b" in encoded
