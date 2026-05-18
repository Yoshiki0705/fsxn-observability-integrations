"""Unit tests for EMS Lambda handler (ems_handler.py).

Tests cover:
- Valid single/array EMS event parsing and shipping
- Empty/invalid body error handling
- ARP ransomware event formatting
- Quota exceeded event formatting
- Batch splitting when events exceed 1000 items
- API key retrieval from Secrets Manager
- Datadog API retry logic (429, 500)
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add lambda directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))


@pytest.fixture(autouse=True)
def ems_env_vars(monkeypatch):
    """Set required environment variables for EMS handler tests."""
    monkeypatch.setenv("DATADOG_SITE", "datadoghq.com")
    monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:dd-api-key")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DD_ENV", "test")
    monkeypatch.setenv("ENABLE_GZIP", "false")


@pytest.fixture
def reset_ems_handler():
    """Reset module-level cache and reimport ems_handler for test isolation."""
    # Remove cached module to pick up fresh env vars
    if "ems_handler" in sys.modules:
        del sys.modules["ems_handler"]
    import ems_handler
    ems_handler._api_key_cache = None
    return ems_handler


@pytest.fixture
def sample_ems_event():
    """Sample single EMS event as received from ONTAP webhook."""
    return {
        "messageName": "wafl.vol.full",
        "severity": "alert",
        "node": "fsxn-node-01",
        "svmName": "svm-prod-01",
        "time": "2026-01-15T12:00:00Z",
        "message": "Volume vol1 is full",
        "parameters": {
            "volume_name": "vol1",
            "percent_full": "95",
        },
    }


@pytest.fixture
def sample_arw_event():
    """Sample ARP ransomware detection event (arw.volume.state)."""
    return {
        "messageName": "arw.volume.state",
        "severity": "alert",
        "node": "fsxn-node-01",
        "svmName": "svm-prod-01",
        "time": "2026-01-15T14:30:00Z",
        "message": "Anti-ransomware: Volume vol_data state changed to attack-detected",
        "parameters": {
            "volume_name": "vol_data",
            "state": "attack-detected",
            "suspect_files": "15",
        },
    }


@pytest.fixture
def sample_quota_event():
    """Sample quota exceeded event (wafl.quota.softlimit.exceeded)."""
    return {
        "messageName": "wafl.quota.softlimit.exceeded",
        "severity": "warning",
        "node": "fsxn-node-01",
        "svmName": "svm-prod-01",
        "time": "2026-01-15T15:00:00Z",
        "message": "Soft quota limit exceeded on volume vol_data",
        "parameters": {
            "volume_name": "vol_data",
            "quota_target": "user1",
            "used_bytes": "62914560",
            "limit_bytes": "52428800",
        },
    }


@pytest.fixture
def apigw_event_single(sample_ems_event):
    """API Gateway proxy event with a single EMS event in body."""
    return {
        "body": json.dumps(sample_ems_event),
        "requestContext": {"requestId": "test-request-123"},
    }


@pytest.fixture
def apigw_event_array(sample_ems_event, sample_arw_event):
    """API Gateway proxy event with an array of EMS events in body."""
    return {
        "body": json.dumps([sample_ems_event, sample_arw_event]),
        "requestContext": {"requestId": "test-request-456"},
    }


class TestExtractEmsEvents:
    """Tests for _extract_ems_events function."""

    def test_single_event_object(self, reset_ems_handler, sample_ems_event):
        handler = reset_ems_handler
        event = {"body": json.dumps(sample_ems_event), "requestContext": {}}
        result = handler._extract_ems_events(event)
        assert len(result) == 1
        assert result[0]["messageName"] == "wafl.vol.full"

    def test_array_of_events(self, reset_ems_handler, sample_ems_event, sample_arw_event):
        handler = reset_ems_handler
        event = {"body": json.dumps([sample_ems_event, sample_arw_event]), "requestContext": {}}
        result = handler._extract_ems_events(event)
        assert len(result) == 2
        assert result[0]["messageName"] == "wafl.vol.full"
        assert result[1]["messageName"] == "arw.volume.state"

    def test_missing_body_raises_value_error(self, reset_ems_handler):
        handler = reset_ems_handler
        event = {"requestContext": {}}
        with pytest.raises(ValueError, match="body is missing"):
            handler._extract_ems_events(event)

    def test_empty_body_raises_value_error(self, reset_ems_handler):
        handler = reset_ems_handler
        event = {"body": "", "requestContext": {}}
        with pytest.raises(ValueError, match="body is empty"):
            handler._extract_ems_events(event)

    def test_whitespace_body_raises_value_error(self, reset_ems_handler):
        handler = reset_ems_handler
        event = {"body": "   ", "requestContext": {}}
        with pytest.raises(ValueError, match="body is empty"):
            handler._extract_ems_events(event)

    def test_invalid_json_raises_json_decode_error(self, reset_ems_handler):
        handler = reset_ems_handler
        event = {"body": "not valid json{{{", "requestContext": {}}
        with pytest.raises(json.JSONDecodeError):
            handler._extract_ems_events(event)

    def test_body_as_dict_direct_invocation(self, reset_ems_handler, sample_ems_event):
        """When body is already a dict (direct Lambda invocation)."""
        handler = reset_ems_handler
        event = {"body": sample_ems_event, "requestContext": {}}
        result = handler._extract_ems_events(event)
        assert len(result) == 1


class TestFormatForDatadog:
    """Tests for _format_for_datadog function."""

    def test_basic_ems_event_formatting(self, reset_ems_handler, sample_ems_event):
        handler = reset_ems_handler
        events = [sample_ems_event]
        result = handler._format_for_datadog(events)

        assert len(result) == 1
        dd_log = result[0]
        assert dd_log["ddsource"] == "fsxn-ems"
        assert dd_log["service"] == "fsxn-ontap"
        assert dd_log["hostname"] == "fsxn-node-01"
        assert dd_log["message"] == "Volume vol1 is full"
        assert dd_log["date"] == "2026-01-15T12:00:00Z"
        assert "source:fsxn-ems" in dd_log["ddtags"]
        assert "service:fsxn-ontap" in dd_log["ddtags"]

    def test_arw_event_attributes(self, reset_ems_handler, sample_arw_event):
        """ARP ransomware event should have correct attributes in Datadog format."""
        handler = reset_ems_handler
        result = handler._format_for_datadog([sample_arw_event])

        assert len(result) == 1
        dd_log = result[0]
        attrs = dd_log["attributes"]
        assert attrs["event_name"] == "arw.volume.state"
        assert attrs["severity"] == "alert"
        assert attrs["source_node"] == "fsxn-node-01"
        assert attrs["svm"] == "svm-prod-01"
        assert attrs["parameters"]["volume_name"] == "vol_data"
        assert attrs["parameters"]["state"] == "attack-detected"

    def test_quota_event_attributes(self, reset_ems_handler, sample_quota_event):
        """Quota exceeded event should have correct attributes in Datadog format."""
        handler = reset_ems_handler
        result = handler._format_for_datadog([sample_quota_event])

        assert len(result) == 1
        dd_log = result[0]
        attrs = dd_log["attributes"]
        assert attrs["event_name"] == "wafl.quota.softlimit.exceeded"
        assert attrs["severity"] == "warning"
        assert attrs["svm"] == "svm-prod-01"
        assert attrs["parameters"]["volume_name"] == "vol_data"
        assert attrs["parameters"]["quota_target"] == "user1"
        assert attrs["parameters"]["used_bytes"] == "62914560"
        assert attrs["parameters"]["limit_bytes"] == "52428800"

    def test_multiple_events(self, reset_ems_handler, sample_ems_event, sample_arw_event):
        handler = reset_ems_handler
        result = handler._format_for_datadog([sample_ems_event, sample_arw_event])
        assert len(result) == 2

    def test_empty_events_list(self, reset_ems_handler):
        handler = reset_ems_handler
        result = handler._format_for_datadog([])
        assert len(result) == 0

    def test_event_without_message_uses_json_dump(self, reset_ems_handler):
        handler = reset_ems_handler
        event = {"messageName": "test.event", "severity": "info", "node": "node1"}
        result = handler._format_for_datadog([event])
        # When message is empty/missing, should use JSON dump
        dd_log = result[0]
        assert dd_log["message"]  # Should not be empty

    def test_ddtags_contains_env(self, reset_ems_handler, sample_ems_event):
        handler = reset_ems_handler
        result = handler._format_for_datadog([sample_ems_event])
        assert "env:test" in result[0]["ddtags"]


class TestBatchSplitting:
    """Tests for _create_batches function with EMS events."""

    def test_single_batch_under_limit(self, reset_ems_handler):
        handler = reset_ems_handler
        logs = [{"message": f"ems event {i}"} for i in range(10)]
        batches = handler._create_batches(logs)
        assert len(batches) == 1
        assert len(batches[0]) == 10

    def test_batch_split_at_1000_items(self, reset_ems_handler):
        """Events exceeding 1000 items should be split into multiple batches."""
        handler = reset_ems_handler
        logs = [{"message": f"ems event {i}", "index": i} for i in range(1500)]
        batches = handler._create_batches(logs)
        assert len(batches) == 2
        assert len(batches[0]) == 1000
        assert len(batches[1]) == 500

    def test_batch_split_at_exact_1000(self, reset_ems_handler):
        handler = reset_ems_handler
        logs = [{"message": f"ems event {i}"} for i in range(1000)]
        batches = handler._create_batches(logs)
        assert len(batches) == 1
        assert len(batches[0]) == 1000

    def test_batch_split_at_1001(self, reset_ems_handler):
        handler = reset_ems_handler
        logs = [{"message": f"ems event {i}"} for i in range(1001)]
        batches = handler._create_batches(logs)
        assert len(batches) == 2
        assert len(batches[0]) == 1000
        assert len(batches[1]) == 1

    def test_empty_input(self, reset_ems_handler):
        handler = reset_ems_handler
        batches = handler._create_batches([])
        assert len(batches) == 0


class TestGetApiKey:
    """Tests for API key retrieval from Secrets Manager."""

    def test_json_format_api_key(self, reset_ems_handler):
        handler = reset_ems_handler
        with patch.object(handler.secrets_client, "get_secret_value") as mock_get:
            mock_get.return_value = {
                "SecretString": json.dumps({"api_key": "dd-test-key-abc123"})
            }
            key = handler.get_api_key()
            assert key == "dd-test-key-abc123"

    def test_json_format_dd_api_key(self, reset_ems_handler):
        handler = reset_ems_handler
        with patch.object(handler.secrets_client, "get_secret_value") as mock_get:
            mock_get.return_value = {
                "SecretString": json.dumps({"DD_API_KEY": "dd-test-key-xyz789"})
            }
            key = handler.get_api_key()
            assert key == "dd-test-key-xyz789"

    def test_plain_string_format(self, reset_ems_handler):
        handler = reset_ems_handler
        with patch.object(handler.secrets_client, "get_secret_value") as mock_get:
            mock_get.return_value = {
                "SecretString": "plain-api-key-12345"
            }
            key = handler.get_api_key()
            assert key == "plain-api-key-12345"

    def test_api_key_caching(self, reset_ems_handler):
        handler = reset_ems_handler
        with patch.object(handler.secrets_client, "get_secret_value") as mock_get:
            mock_get.return_value = {
                "SecretString": json.dumps({"api_key": "cached-key"})
            }
            handler.get_api_key()
            handler.get_api_key()
            # Should only call Secrets Manager once due to caching
            mock_get.assert_called_once()


class TestSendBatchRetry:
    """Tests for _send_batch retry logic."""

    def test_retry_on_429_rate_limit(self, reset_ems_handler):
        handler = reset_ems_handler
        mock_rate_limit = MagicMock()
        mock_rate_limit.status = 429
        mock_rate_limit.headers = {"Retry-After": "1"}

        mock_success = MagicMock()
        mock_success.status = 202

        with patch.object(handler.http, "request", side_effect=[mock_rate_limit, mock_success]):
            with patch("ems_handler.time.sleep") as mock_sleep:
                result = handler._send_batch([{"message": "test"}], "key")

        assert result is True
        mock_sleep.assert_called_once_with(1)

    def test_retry_on_500_server_error(self, reset_ems_handler):
        handler = reset_ems_handler
        mock_error = MagicMock()
        mock_error.status = 500
        mock_error.data = b"Internal Server Error"

        mock_success = MagicMock()
        mock_success.status = 202

        with patch.object(handler.http, "request", side_effect=[mock_error, mock_success]):
            with patch("ems_handler.time.sleep") as mock_sleep:
                result = handler._send_batch([{"message": "test"}], "key")

        assert result is True
        # Exponential backoff: 2^(0+1) = 2 seconds
        mock_sleep.assert_called_once_with(2)

    def test_retry_on_503_with_backoff(self, reset_ems_handler):
        handler = reset_ems_handler
        mock_error = MagicMock()
        mock_error.status = 503
        mock_error.data = b"Service Unavailable"

        mock_success = MagicMock()
        mock_success.status = 200

        with patch.object(handler.http, "request", side_effect=[mock_error, mock_error, mock_success]):
            with patch("ems_handler.time.sleep") as mock_sleep:
                result = handler._send_batch([{"message": "test"}], "key")

        assert result is True
        # Two retries: 2^1=2, 2^2=4
        assert mock_sleep.call_count == 2

    def test_max_retries_exhausted(self, reset_ems_handler):
        handler = reset_ems_handler
        mock_error = MagicMock()
        mock_error.status = 500
        mock_error.data = b"Error"

        with patch.object(handler.http, "request", return_value=mock_error):
            with patch("ems_handler.time.sleep"):
                result = handler._send_batch([{"message": "test"}], "key")

        assert result is False

    def test_no_retry_on_client_error(self, reset_ems_handler):
        handler = reset_ems_handler
        mock_error = MagicMock()
        mock_error.status = 403
        mock_error.data = b"Forbidden"

        with patch.object(handler.http, "request", return_value=mock_error) as mock_request:
            result = handler._send_batch([{"message": "test"}], "key")

        assert result is False
        mock_request.assert_called_once()

    def test_successful_send(self, reset_ems_handler):
        handler = reset_ems_handler
        mock_response = MagicMock()
        mock_response.status = 202

        with patch.object(handler.http, "request", return_value=mock_response):
            result = handler._send_batch([{"message": "test"}], "key")

        assert result is True


class TestLambdaHandler:
    """Integration tests for the full EMS Lambda handler."""

    def test_valid_single_event_success(self, reset_ems_handler, apigw_event_single):
        handler = reset_ems_handler
        mock_response = MagicMock()
        mock_response.status = 202

        with patch.object(handler.secrets_client, "get_secret_value") as mock_secrets:
            mock_secrets.return_value = {"SecretString": json.dumps({"api_key": "test-key"})}
            with patch.object(handler.http, "request", return_value=mock_response):
                result = handler.lambda_handler(apigw_event_single, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["total_events"] == 1
        assert body["shipped"] == 1

    def test_valid_array_of_events_success(self, reset_ems_handler, apigw_event_array):
        handler = reset_ems_handler
        mock_response = MagicMock()
        mock_response.status = 202

        with patch.object(handler.secrets_client, "get_secret_value") as mock_secrets:
            mock_secrets.return_value = {"SecretString": json.dumps({"api_key": "test-key"})}
            with patch.object(handler.http, "request", return_value=mock_response):
                result = handler.lambda_handler(apigw_event_array, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["total_events"] == 2
        assert body["shipped"] == 2

    def test_empty_body_returns_400(self, reset_ems_handler):
        handler = reset_ems_handler
        event = {"body": "", "requestContext": {"requestId": "test-req"}}
        result = handler.lambda_handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "error" in body

    def test_missing_body_returns_400(self, reset_ems_handler):
        handler = reset_ems_handler
        event = {"requestContext": {"requestId": "test-req"}}
        result = handler.lambda_handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "error" in body

    def test_invalid_json_body_returns_400(self, reset_ems_handler):
        handler = reset_ems_handler
        event = {"body": "not{valid}json", "requestContext": {"requestId": "test-req"}}
        result = handler.lambda_handler(event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "error" in body

    def test_api_key_retrieval_failure_returns_500(self, reset_ems_handler, apigw_event_single):
        handler = reset_ems_handler
        with patch.object(handler.secrets_client, "get_secret_value") as mock_secrets:
            mock_secrets.side_effect = Exception("Access denied")
            result = handler.lambda_handler(apigw_event_single, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body
        assert "API key" in body["error"]

    def test_partial_shipping_failure_returns_207(self, reset_ems_handler, apigw_event_array):
        """When some events fail to ship, handler returns 207."""
        handler = reset_ems_handler
        mock_success = MagicMock()
        mock_success.status = 202

        mock_failure = MagicMock()
        mock_failure.status = 403
        mock_failure.data = b"Forbidden"

        # First batch succeeds, but we simulate failure by making _send_batch
        # return False for the overall shipping
        with patch.object(handler.secrets_client, "get_secret_value") as mock_secrets:
            mock_secrets.return_value = {"SecretString": json.dumps({"api_key": "test-key"})}
            with patch.object(handler, "_ship_to_datadog", return_value=1):
                result = handler.lambda_handler(apigw_event_array, None)

        # 1 shipped out of 2 total → 207
        assert result["statusCode"] == 207
