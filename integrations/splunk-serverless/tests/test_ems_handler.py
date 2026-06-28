"""Unit tests for EMS Webhook handler.

Tests cover:
- Valid payload forwarding → 200 with status
- Missing x-api-key → 401
- Invalid x-api-key → 401
- Missing required fields → 400 with field names
- HEC failure after retries → 502
- Malformed JSON body → 400

Validates: Requirements 5.1, 5.3, 5.4, 5.7, 5.8
"""

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Set environment variables BEFORE importing ems_handler (module reads at load time)
os.environ.setdefault("SPLUNK_HEC_ENDPOINT", "https://splunk.example.com:8088")
os.environ.setdefault(
    "EMS_API_KEY_SECRET_ARN",
    "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ems-api-key",
)
os.environ.setdefault(
    "HEC_TOKEN_SECRET_ARN",
    "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk-hec-token",
)

# Add lambda directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))

import ems_handler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_caches() -> None:
    """Reset module-level caches between tests."""
    ems_handler._api_key_cache = None
    ems_handler._hec_token_cache = None


@pytest.fixture(autouse=True)
def ems_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set required environment variables and module-level constants for EMS handler tests."""
    monkeypatch.setenv("SPLUNK_HEC_ENDPOINT", "https://splunk.example.com:8088")
    monkeypatch.setenv(
        "EMS_API_KEY_SECRET_ARN",
        "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ems-api-key",
    )
    monkeypatch.setenv(
        "HEC_TOKEN_SECRET_ARN",
        "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk-hec-token",
    )
    # Patch module-level constants (read at import time)
    monkeypatch.setattr(ems_handler, "HEC_ENDPOINT", "https://splunk.example.com:8088")
    monkeypatch.setattr(
        ems_handler,
        "EMS_API_KEY_SECRET_ARN",
        "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ems-api-key",
    )
    monkeypatch.setattr(
        ems_handler,
        "HEC_TOKEN_SECRET_ARN",
        "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:splunk-hec-token",
    )


@pytest.fixture
def valid_api_key() -> str:
    """Valid API key for authentication."""
    return "test-valid-api-key-12345"


@pytest.fixture
def valid_hec_token() -> str:
    """Valid Splunk HEC token."""
    return "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


@pytest.fixture
def valid_ems_payload() -> dict[str, Any]:
    """Valid EMS event payload with all required fields."""
    return {
        "message-name": "arw.volume.state",
        "message-severity": "alert",
        "message-timestamp": "2026-01-15T12:05:00+09:00",
        "parameters": {
            "volume-name": "vol_data_01",
            "vserver-name": "svm-prod-01",
            "state": "attack-detected",
            "attack-probability": "high",
            "suspect-files-count": "42",
        },
    }


@pytest.fixture
def api_gateway_event(
    valid_api_key: str, valid_ems_payload: dict[str, Any]
) -> dict[str, Any]:
    """API Gateway HTTP API v2.0 event with valid headers and body."""
    return {
        "version": "2.0",
        "routeKey": "POST /ems",
        "rawPath": "/ems",
        "headers": {
            "content-type": "application/json",
            "x-api-key": valid_api_key,
        },
        "body": json.dumps(valid_ems_payload),
        "isBase64Encoded": False,
        "requestContext": {
            "http": {"method": "POST", "path": "/ems"},
            "requestId": "req-12345",
        },
    }


@pytest.fixture
def mock_secrets(valid_api_key: str, valid_hec_token: str) -> MagicMock:
    """Mock Secrets Manager client returning valid API key and HEC token."""
    with patch("ems_handler.secrets_client") as mock_client:
        def get_secret_value_side_effect(SecretId: str) -> dict[str, str]:
            if "ems-api-key" in SecretId:
                return {"SecretString": valid_api_key}
            if "splunk-hec-token" in SecretId:
                return {"SecretString": valid_hec_token}
            return {"SecretString": ""}

        mock_client.get_secret_value.side_effect = get_secret_value_side_effect
        yield mock_client


@pytest.fixture
def mock_http_success() -> MagicMock:
    """Mock urllib3 PoolManager returning successful HEC response."""
    with patch("ems_handler.http") as mock_http:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.data = json.dumps({"text": "Success", "code": 0}).encode("utf-8")
        mock_http.request.return_value = mock_response
        yield mock_http


@pytest.fixture
def mock_http_failure() -> MagicMock:
    """Mock urllib3 PoolManager returning 503 on all attempts."""
    with patch("ems_handler.http") as mock_http:
        mock_response = MagicMock()
        mock_response.status = 503
        mock_response.data = json.dumps(
            {"text": "Server Error", "code": 9}
        ).encode("utf-8")
        mock_http.request.return_value = mock_response
        yield mock_http


# ---------------------------------------------------------------------------
# Tests: Valid payload → 200 with forwarding status
# ---------------------------------------------------------------------------


class TestValidPayloadForwarding:
    """Tests for successful EMS event forwarding (Requirement 5.1)."""

    def test_valid_payload_returns_200(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
        mock_http_success: MagicMock,
    ) -> None:
        """Valid EMS payload returns HTTP 200 with success status."""
        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "success"
        assert "forwarded" in body["message"].lower() or "forward" in body["message"].lower()

    def test_valid_payload_includes_message_name(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
        mock_http_success: MagicMock,
    ) -> None:
        """Response body includes the message-name from the EMS event."""
        result = ems_handler.lambda_handler(api_gateway_event, None)

        body = json.loads(result["body"])
        assert body["message_name"] == "arw.volume.state"

    def test_valid_payload_sends_to_hec(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
        mock_http_success: MagicMock,
    ) -> None:
        """Valid payload triggers a POST request to Splunk HEC endpoint."""
        ems_handler.lambda_handler(api_gateway_event, None)

        mock_http_success.request.assert_called_once()
        call_args = mock_http_success.request.call_args
        assert call_args[0][0] == "POST"
        assert "/services/collector/event" in call_args[0][1]

    def test_hec_payload_has_ems_sourcetype(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
        mock_http_success: MagicMock,
    ) -> None:
        """HEC payload uses sourcetype fsxn:ontap:ems and index fsxn_ems."""
        ems_handler.lambda_handler(api_gateway_event, None)

        call_args = mock_http_success.request.call_args
        sent_body = json.loads(call_args[1]["body"])
        assert sent_body["sourcetype"] == "fsxn:ontap:ems"
        assert sent_body["index"] == "fsxn_ems"


# ---------------------------------------------------------------------------
# Tests: Missing x-api-key → 401
# ---------------------------------------------------------------------------


class TestMissingApiKey:
    """Tests for missing x-api-key header (Requirement 5.3, 5.4)."""

    def test_missing_api_key_returns_401(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
    ) -> None:
        """Request without x-api-key header returns HTTP 401."""
        del api_gateway_event["headers"]["x-api-key"]

        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert "unauthorized" in body["error"].lower() or "api key" in body["error"].lower()

    def test_empty_api_key_returns_401(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
    ) -> None:
        """Request with empty x-api-key header returns HTTP 401."""
        api_gateway_event["headers"]["x-api-key"] = ""

        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 401

    def test_missing_api_key_does_not_forward(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
        mock_http_success: MagicMock,
    ) -> None:
        """Request without x-api-key does NOT forward to Splunk HEC."""
        del api_gateway_event["headers"]["x-api-key"]

        ems_handler.lambda_handler(api_gateway_event, None)

        mock_http_success.request.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Invalid x-api-key → 401
# ---------------------------------------------------------------------------


class TestInvalidApiKey:
    """Tests for invalid x-api-key header (Requirement 5.3, 5.4)."""

    def test_invalid_api_key_returns_401(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
    ) -> None:
        """Request with wrong x-api-key returns HTTP 401."""
        api_gateway_event["headers"]["x-api-key"] = "wrong-key-value"

        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert "unauthorized" in body["error"].lower() or "api key" in body["error"].lower()

    def test_invalid_api_key_does_not_forward(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
        mock_http_success: MagicMock,
    ) -> None:
        """Request with wrong x-api-key does NOT forward to Splunk HEC."""
        api_gateway_event["headers"]["x-api-key"] = "wrong-key-value"

        ems_handler.lambda_handler(api_gateway_event, None)

        mock_http_success.request.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Missing required fields → 400 with field names
# ---------------------------------------------------------------------------


class TestMissingRequiredFields:
    """Tests for missing required EMS fields (Requirement 5.7)."""

    def test_missing_message_name_returns_400(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
    ) -> None:
        """Payload missing message-name returns HTTP 400."""
        payload = json.loads(api_gateway_event["body"])
        del payload["message-name"]
        api_gateway_event["body"] = json.dumps(payload)

        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "message-name" in body["error"]

    def test_missing_message_severity_returns_400(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
    ) -> None:
        """Payload missing message-severity returns HTTP 400."""
        payload = json.loads(api_gateway_event["body"])
        del payload["message-severity"]
        api_gateway_event["body"] = json.dumps(payload)

        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "message-severity" in body["error"]

    def test_missing_message_timestamp_returns_400(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
    ) -> None:
        """Payload missing message-timestamp returns HTTP 400."""
        payload = json.loads(api_gateway_event["body"])
        del payload["message-timestamp"]
        api_gateway_event["body"] = json.dumps(payload)

        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "message-timestamp" in body["error"]

    def test_missing_multiple_fields_lists_all(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
    ) -> None:
        """Payload missing multiple fields lists all missing field names."""
        payload = json.loads(api_gateway_event["body"])
        del payload["message-name"]
        del payload["message-severity"]
        api_gateway_event["body"] = json.dumps(payload)

        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "message-name" in body["error"]
        assert "message-severity" in body["error"]

    def test_missing_fields_response_includes_field_list(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
    ) -> None:
        """Response body includes missing_fields array."""
        payload = json.loads(api_gateway_event["body"])
        del payload["message-name"]
        del payload["message-timestamp"]
        api_gateway_event["body"] = json.dumps(payload)

        result = ems_handler.lambda_handler(api_gateway_event, None)

        body = json.loads(result["body"])
        assert "missing_fields" in body
        assert "message-name" in body["missing_fields"]
        assert "message-timestamp" in body["missing_fields"]


# ---------------------------------------------------------------------------
# Tests: HEC failure after retries → 502
# ---------------------------------------------------------------------------


class TestHecFailureAfterRetries:
    """Tests for HEC failure after retry exhaustion (Requirement 5.8)."""

    @patch("ems_handler.time.sleep")
    def test_hec_503_after_retries_returns_502(
        self,
        mock_sleep: MagicMock,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
        mock_http_failure: MagicMock,
    ) -> None:
        """HEC returning 503 on all retries results in HTTP 502."""
        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 502
        body = json.loads(result["body"])
        assert "error" in body

    @patch("ems_handler.time.sleep")
    def test_hec_failure_retries_three_times(
        self,
        mock_sleep: MagicMock,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
        mock_http_failure: MagicMock,
    ) -> None:
        """HEC failure triggers exactly 3 retry attempts."""
        ems_handler.lambda_handler(api_gateway_event, None)

        assert mock_http_failure.request.call_count == 3

    @patch("ems_handler.time.sleep")
    def test_hec_failure_uses_exponential_backoff(
        self,
        mock_sleep: MagicMock,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
        mock_http_failure: MagicMock,
    ) -> None:
        """Retry uses exponential backoff (2s, 4s delays)."""
        ems_handler.lambda_handler(api_gateway_event, None)

        # 3 attempts means 2 sleeps (between attempt 1→2 and 2→3)
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(sleep_calls) == 2
        assert sleep_calls[0] == 2  # BASE_DELAY_SECONDS * 2^0
        assert sleep_calls[1] == 4  # BASE_DELAY_SECONDS * 2^1


# ---------------------------------------------------------------------------
# Tests: Malformed JSON body → 400
# ---------------------------------------------------------------------------


class TestMalformedJsonBody:
    """Tests for malformed JSON request body (Requirement 5.7)."""

    def test_invalid_json_returns_400(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
    ) -> None:
        """Non-JSON body returns HTTP 400."""
        api_gateway_event["body"] = "not valid json {{"

        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "malformed" in body["error"].lower() or "json" in body["error"].lower()

    def test_empty_body_returns_400(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
    ) -> None:
        """Empty body returns HTTP 400."""
        api_gateway_event["body"] = ""

        result = ems_handler.lambda_handler(api_gateway_event, None)

        assert result["statusCode"] == 400

    def test_malformed_json_does_not_forward(
        self,
        api_gateway_event: dict[str, Any],
        mock_secrets: MagicMock,
        mock_http_success: MagicMock,
    ) -> None:
        """Malformed JSON body does NOT forward to Splunk HEC."""
        api_gateway_event["body"] = "{invalid"

        ems_handler.lambda_handler(api_gateway_event, None)

        mock_http_success.request.assert_not_called()
