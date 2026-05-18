"""Unit tests for EMS Parser parse_ems_event() and format_ems_event().

Tests cover:
- Normal parsing for all 7 event types (loaded from test_data/)
- Error handling (empty string, invalid JSON, missing fields)
- Edge cases (message truncation, unknown event type, extra fields)
- Round-trip serialization (parse → format → parse)
"""

import json

import pytest

from ems_parser import EmsParseError, format_ems_event, parse_ems_event

from .conftest import load_test_data


# ---------------------------------------------------------------------------
# Normal parsing tests — one per event type
# ---------------------------------------------------------------------------


class TestParseArwVolumeState:
    """Test parsing of arw.volume.state event."""

    def test_parse_arw_volume_state(self) -> None:
        payload = load_test_data("arw_volume_state.json")
        result = parse_ems_event(payload)

        assert result["event_name"] == "arw.volume.state"
        assert result["severity"] == "alert"
        assert result["timestamp"] == "2024-01-15T10:30:00+09:00"
        assert result["source_node"] == "fsxn-node-01"
        assert result["svm"] == "svm-prod-01"
        assert result["message"] == "Anti-ransomware: Volume vol_data state changed to enabled"
        assert result["parameters"]["volume_name"] == "vol_data"
        assert result["parameters"]["state"] == "enabled"
        assert result["raw"] == payload


class TestParseArwVserverState:
    """Test parsing of arw.vserver.state event."""

    def test_parse_arw_vserver_state(self) -> None:
        payload = load_test_data("arw_vserver_state.json")
        result = parse_ems_event(payload)

        assert result["event_name"] == "arw.vserver.state"
        assert result["severity"] == "alert"
        assert result["timestamp"] == "2024-01-15T11:00:00+09:00"
        assert result["source_node"] == "fsxn-node-01"
        assert result["svm"] == "svm-prod-01"
        assert result["message"] == "Anti-ransomware: Vserver svm-prod-01 state changed to enabled"
        assert result["parameters"]["vserver_name"] == "svm-prod-01"
        assert result["parameters"]["state"] == "enabled"
        assert result["raw"] == payload


class TestParseQuotaSoftlimit:
    """Test parsing of wafl.quota.softlimit.exceeded event."""

    def test_parse_quota_softlimit(self) -> None:
        payload = load_test_data("wafl_quota_softlimit.json")
        result = parse_ems_event(payload)

        assert result["event_name"] == "wafl.quota.softlimit.exceeded"
        assert result["severity"] == "warning"
        assert result["timestamp"] == "2024-01-15T14:00:00+09:00"
        assert result["source_node"] == "fsxn-node-01"
        assert result["svm"] == "svm-prod-01"
        assert "Quota soft limit exceeded" in result["message"]
        assert result["parameters"]["volume_name"] == "vol_data"
        assert result["parameters"]["qtree"] == "qtree1"
        assert result["parameters"]["quota_target"] == "user1"
        assert result["parameters"]["used_bytes"] == 62914560
        assert result["parameters"]["limit_bytes"] == 52428800
        assert result["raw"] == payload


class TestParseQuotaHardlimit:
    """Test parsing of wafl.quota.hardlimit.exceeded event."""

    def test_parse_quota_hardlimit(self) -> None:
        payload = load_test_data("wafl_quota_hardlimit.json")
        result = parse_ems_event(payload)

        assert result["event_name"] == "wafl.quota.hardlimit.exceeded"
        assert result["severity"] == "error"
        assert result["timestamp"] == "2024-01-15T14:30:00+09:00"
        assert result["source_node"] == "fsxn-node-02"
        assert result["svm"] == "svm-prod-01"
        assert "Quota hard limit exceeded" in result["message"]
        assert result["parameters"]["volume_name"] == "vol_data"
        assert result["parameters"]["qtree"] == "qtree2"
        assert result["parameters"]["quota_target"] == "user2"
        assert result["parameters"]["used_bytes"] == 104857600
        assert result["parameters"]["limit_bytes"] == 104857600
        assert result["raw"] == payload


class TestParseSmsVolFull:
    """Test parsing of sms.vol.full event."""

    def test_parse_sms_vol_full(self) -> None:
        payload = load_test_data("sms_vol_full.json")
        result = parse_ems_event(payload)

        assert result["event_name"] == "sms.vol.full"
        assert result["severity"] == "error"
        assert result["timestamp"] == "2024-01-15T16:00:00+09:00"
        assert result["source_node"] == "fsxn-node-01"
        assert result["svm"] == "svm-prod-01"
        assert "vol_backup" in result["message"]
        assert result["parameters"]["volume_name"] == "vol_backup"
        assert result["parameters"]["used_percent"] == 98
        assert result["raw"] == payload


class TestParseCfFsmTakeover:
    """Test parsing of cf.fsm.takeoverStarted event."""

    def test_parse_cf_fsm_takeover(self) -> None:
        payload = load_test_data("cf_fsm_takeover.json")
        result = parse_ems_event(payload)

        assert result["event_name"] == "cf.fsm.takeoverStarted"
        assert result["severity"] == "alert"
        assert result["timestamp"] == "2024-01-15T18:00:00+09:00"
        assert result["source_node"] == "fsxn-node-01"
        assert result["svm"] == "svm-prod-01"
        assert "Takeover" in result["message"]
        assert result["parameters"]["partner_node"] == "fsxn-node-02"
        assert result["parameters"]["reason"] == "hardware failure detected"
        assert result["raw"] == payload


class TestParseNetLinkdown:
    """Test parsing of net.linkDown event."""

    def test_parse_net_linkdown(self) -> None:
        payload = load_test_data("net_linkdown.json")
        result = parse_ems_event(payload)

        assert result["event_name"] == "net.linkDown"
        assert result["severity"] == "alert"
        assert result["timestamp"] == "2024-01-15T20:00:00+09:00"
        assert result["source_node"] == "fsxn-node-01"
        assert result["svm"] == "svm-prod-01"
        assert "link" in result["message"].lower()
        assert result["parameters"]["node"] == "fsxn-node-01"
        assert result["parameters"]["port"] == "e0a"
        assert result["parameters"]["reason"] == "cable unplugged"
        assert result["raw"] == payload


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test that invalid inputs raise EmsParseError."""

    def test_empty_string_raises_ems_parse_error(self) -> None:
        with pytest.raises(EmsParseError, match="payload is empty"):
            parse_ems_event("")

    def test_invalid_json_raises_ems_parse_error(self) -> None:
        with pytest.raises(EmsParseError, match="invalid JSON"):
            parse_ems_event("{not valid json at all!!!")

    def test_missing_message_name_raises_ems_parse_error(self) -> None:
        payload = {
            "time": "2024-01-15T10:30:00+09:00",
            "severity": "alert",
            "node": "fsxn-node-01",
            "svmName": "svm-prod-01",
            "message": "Some message",
            "parameters": {"key": "value"},
        }
        with pytest.raises(EmsParseError, match="missing required field: messageName"):
            parse_ems_event(payload)

    def test_missing_parameters_raises_ems_parse_error(self) -> None:
        payload = {
            "time": "2024-01-15T10:30:00+09:00",
            "messageName": "arw.volume.state",
            "severity": "alert",
            "node": "fsxn-node-01",
            "svmName": "svm-prod-01",
            "message": "Some message",
        }
        with pytest.raises(EmsParseError, match="missing required field: parameters"):
            parse_ems_event(payload)


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases: truncation, unknown events, extra fields."""

    def test_message_exceeding_2048_chars_is_truncated(self) -> None:
        long_message = "A" * 3000
        payload = {
            "time": "2024-01-15T10:30:00+09:00",
            "messageName": "arw.volume.state",
            "severity": "alert",
            "node": "fsxn-node-01",
            "svmName": "svm-prod-01",
            "message": long_message,
            "parameters": {"volume_name": "vol1", "state": "enabled"},
        }
        result = parse_ems_event(payload)

        assert len(result["message"]) == 2048
        assert result["message"] == "A" * 2048

    def test_unknown_event_type_passes_through(self) -> None:
        payload = {
            "time": "2024-01-15T10:30:00+09:00",
            "messageName": "custom.unknown.event",
            "severity": "informational",
            "node": "fsxn-node-01",
            "svmName": "svm-prod-01",
            "message": "Unknown event occurred",
            "parameters": {"custom_field": "custom_value", "count": 42},
        }
        result = parse_ems_event(payload)

        assert result["event_name"] == "custom.unknown.event"
        assert result["severity"] == "informational"
        assert result["parameters"]["custom_field"] == "custom_value"
        assert result["parameters"]["count"] == 42

    def test_extra_fields_preserved_in_raw(self) -> None:
        payload = {
            "time": "2024-01-15T10:30:00+09:00",
            "messageName": "arw.volume.state",
            "severity": "alert",
            "node": "fsxn-node-01",
            "svmName": "svm-prod-01",
            "message": "Anti-ransomware event",
            "parameters": {"volume_name": "vol1", "state": "enabled"},
            "extra_field_1": "extra_value_1",
            "extra_field_2": {"nested": True},
            "correlationId": "abc-123",
        }
        result = parse_ems_event(payload)

        assert result["raw"]["extra_field_1"] == "extra_value_1"
        assert result["raw"]["extra_field_2"] == {"nested": True}
        assert result["raw"]["correlationId"] == "abc-123"


# ---------------------------------------------------------------------------
# Round-trip test
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Test parse → format → parse produces equal dict."""

    def test_round_trip_preserves_normalized_dict(self) -> None:
        payload = load_test_data("arw_volume_state.json")

        first_parse = parse_ems_event(payload)
        formatted = format_ems_event(first_parse)
        second_parse = parse_ems_event(formatted)

        assert first_parse == second_parse

    def test_round_trip_with_quota_event(self) -> None:
        payload = load_test_data("wafl_quota_softlimit.json")

        first_parse = parse_ems_event(payload)
        formatted = format_ems_event(first_parse)
        second_parse = parse_ems_event(formatted)

        assert first_parse == second_parse

    def test_round_trip_with_json_string_input(self) -> None:
        payload = load_test_data("net_linkdown.json")
        json_string = json.dumps(payload)

        first_parse = parse_ems_event(json_string)
        formatted = format_ems_event(first_parse)
        second_parse = parse_ems_event(formatted)

        assert first_parse == second_parse
